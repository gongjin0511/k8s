"""
K8s日志查询系统 - Flask API服务
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from kubectl_helper import KubectlHelper
import os
import json
import logging
from datetime import datetime
import zipfile
import io
from typing import Dict, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)  # 允许跨域请求

# 初始化kubectl helper
kubectl = KubectlHelper(timeout=300)

# 配置
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
KUBECONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'kubeconfigs')
FILES_DIR = os.path.join(os.path.dirname(__file__), '..', 'files')
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(KUBECONFIG_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

# 限制配置
MAX_TAIL_LINES = 10000
MAX_BATCH_PODS = 100
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024  # 100MB


@app.route('/')
def index():
    """主页面"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/health')
def health_check():
    """健康检查"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/namespaces', methods=['GET'])
def get_namespaces():
    """
    获取namespace列表
    Query参数:
      - pattern: 通配符模式，多个用逗号分隔，如 erp-*,cnnc-*
    """
    try:
        pattern_str = request.args.get('pattern', '')
        patterns = [p.strip() for p in pattern_str.split(',') if p.strip()] if pattern_str else None

        namespaces = kubectl.get_namespaces(patterns)

        return jsonify({
            'success': True,
            'data': namespaces,
            'count': len(namespaces)
        })
    except Exception as e:
        logger.error(f"获取namespace失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pods', methods=['GET'])
def get_pods():
    """
    获取pod列表
    Query参数:
      - namespace: namespace名称 (必需)
      - status: 状态过滤，默认Running
    """
    try:
        namespace = request.args.get('namespace')
        if not namespace:
            return jsonify({
                'success': False,
                'error': 'namespace参数必需'
            }), 400

        status = request.args.get('status', 'Running')
        pods = kubectl.get_pods(namespace, status_filter=status)

        return jsonify({
            'success': True,
            'data': pods,
            'count': len(pods)
        })
    except Exception as e:
        logger.error(f"获取pods失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/logs/query', methods=['POST'])
def query_logs():
    """
    查询单个Pod日志
    Body参数:
    {
      "namespace": "erp-prod",
      "pod": "pod-name",
      "type": "all",  // console | file | all
      "tail": 2000,
      "keywords": ["HikariPool", "timeout"]
    }
    """
    try:
        data = request.get_json()

        # 验证必需参数
        namespace = data.get('namespace')
        pod = data.get('pod')
        if not namespace or not pod:
            return jsonify({
                'success': False,
                'error': 'namespace和pod参数必需'
            }), 400

        # 可选参数
        log_type = data.get('type', 'all')
        tail = min(int(data.get('tail', 2000)), MAX_TAIL_LINES)
        keywords = data.get('keywords', [])

        # 查询日志
        logs = kubectl.get_all_logs(namespace, pod, tail, keywords, log_type)

        # 统计匹配数
        console_matches = len(logs['console_log'])
        file_matches = sum(len(lines) for lines in logs['file_logs'].values())

        return jsonify({
            'success': True,
            'data': {
                'namespace': namespace,
                'pod': pod,
                'console_matches': console_matches,
                'file_matches': file_matches,
                'total_matches': console_matches + file_matches,
                'logs': logs
            }
        })
    except Exception as e:
        logger.error(f"查询日志失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/logs/batch-query', methods=['POST'])
def batch_query_logs():
    """
    批量查询日志
    Body参数:
    {
      "namespaces": ["erp-*", "cnnc-*"],
      "keywords": ["HikariPool", "timeout"],
      "tail": 2000,
      "type": "all",
      "max_pods": 100
    }
    """
    try:
        data = request.get_json()

        # 验证参数
        namespace_patterns = data.get('namespaces', [])
        if not namespace_patterns:
            return jsonify({
                'success': False,
                'error': 'namespaces参数必需'
            }), 400

        keywords = data.get('keywords', [])
        tail = min(int(data.get('tail', 2000)), MAX_TAIL_LINES)
        log_type = data.get('type', 'all')
        max_pods = min(int(data.get('max_pods', 100)), MAX_BATCH_PODS)

        # 批量查询
        results = kubectl.batch_query_logs(
            namespace_patterns=namespace_patterns,
            keywords=keywords,
            tail=tail,
            log_type=log_type,
            max_pods=max_pods
        )

        # 统计
        total_pods = sum(1 for _ in results)
        matched_pods = sum(1 for r in results if r['total_matches'] > 0)

        return jsonify({
            'success': True,
            'data': results,
            'total_pods': total_pods,
            'matched_pods': matched_pods
        })
    except Exception as e:
        logger.error(f"批量查询失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/logs/download', methods=['POST'])
def download_logs():
    """
    下载日志
    Body参数:
    {
      "namespace": "erp-prod",
      "pods": ["pod-1", "pod-2"],
      "type": "all",
      "keywords": ["error"],
      "format": "zip"  // txt | zip
    }
    """
    try:
        data = request.get_json()

        namespace = data.get('namespace')
        pods = data.get('pods', [])
        if not namespace or not pods:
            return jsonify({
                'success': False,
                'error': 'namespace和pods参数必需'
            }), 400

        log_type = data.get('type', 'all')
        keywords = data.get('keywords', [])
        download_format = data.get('format', 'zip')
        tail = min(int(data.get('tail', 2000)), MAX_TAIL_LINES)

        # 创建ZIP文件
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for pod in pods:
                # 查询日志
                logs = kubectl.get_all_logs(namespace, pod, tail, keywords, log_type)

                # 添加console日志
                if logs['console_log']:
                    console_content = '\n'.join(logs['console_log'])
                    zip_file.writestr(f"{namespace}-{pod}/console.log", console_content)

                # 添加文件日志
                for filepath, lines in logs['file_logs'].items():
                    if lines:
                        file_content = '\n'.join(lines)
                        # 使用相对路径作为文件名
                        filename = filepath.replace('/applog/', '').replace('/', '_')
                        zip_file.writestr(f"{namespace}-{pod}/{filename}", file_content)

        zip_buffer.seek(0)

        # 检查文件大小
        if zip_buffer.getbuffer().nbytes > MAX_DOWNLOAD_SIZE:
            return jsonify({
                'success': False,
                'error': f'下载文件过大，超过{MAX_DOWNLOAD_SIZE / 1024 / 1024}MB限制'
            }), 400

        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'logs-{timestamp}.zip'
        )
    except Exception as e:
        logger.error(f"下载日志失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['POST'])
def get_stats():
    """
    统计分析
    Body参数:
    {
      "namespaces": ["erp-*", "cnnc-*"],
      "keywords": ["error", "timeout"]
    }
    """
    try:
        data = request.get_json()

        namespace_patterns = data.get('namespaces', [])
        keywords = data.get('keywords', [])
        tail = min(int(data.get('tail', 2000)), MAX_TAIL_LINES)

        # 批量查询
        results = kubectl.batch_query_logs(
            namespace_patterns=namespace_patterns,
            keywords=keywords,
            tail=tail,
            log_type='all',
            max_pods=MAX_BATCH_PODS
        )

        # 统计分析
        total_pods = len(results)
        matched_pods = sum(1 for r in results if r['total_matches'] > 0)
        total_matches = sum(r['total_matches'] for r in results)

        # 按namespace分组统计
        by_namespace = {}
        for r in results:
            ns = r['namespace']
            by_namespace[ns] = by_namespace.get(ns, 0) + r['total_matches']

        # Top pods
        top_pods = sorted(results, key=lambda x: x['total_matches'], reverse=True)[:10]
        top_pods_data = [
            {
                'namespace': r['namespace'],
                'pod': r['pod'],
                'count': r['total_matches']
            }
            for r in top_pods if r['total_matches'] > 0
        ]

        return jsonify({
            'success': True,
            'data': {
                'total_pods': total_pods,
                'matched_pods': matched_pods,
                'total_matches': total_matches,
                'by_namespace': by_namespace,
                'top_pods': top_pods_data
            }
        })
    except Exception as e:
        logger.error(f"统计分析失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/kubeconfig/upload', methods=['POST'])
def upload_kubeconfig():
    """
    上传kubeconfig文件
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '没有上传文件'
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '文件名为空'
            }), 400

        # 保存文件
        filename = 'kubeconfig'
        filepath = os.path.join(KUBECONFIG_DIR, filename)
        file.save(filepath)

        # 重新初始化kubectl helper
        global kubectl
        kubectl = KubectlHelper(timeout=300, kubeconfig=filepath)

        logger.info(f"kubeconfig已上传: {filepath}")
        return jsonify({
            'success': True,
            'message': 'kubeconfig上传成功'
        })
    except Exception as e:
        logger.error(f"上传kubeconfig失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/kubeconfig/status', methods=['GET'])
def get_kubeconfig_status():
    """
    获取kubeconfig状态
    """
    try:
        kubeconfig_path = os.path.join(KUBECONFIG_DIR, 'kubeconfig')
        exists = os.path.exists(kubeconfig_path)

        return jsonify({
            'success': True,
            'data': {
                'configured': exists,
                'path': kubeconfig_path if exists else None
            }
        })
    except Exception as e:
        logger.error(f"获取kubeconfig状态失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/deployments', methods=['GET'])
def get_deployments():
    """
    获取deployment列表
    Query参数:
      - namespace: namespace名称 (必需)
    """
    try:
        namespace = request.args.get('namespace')
        if not namespace:
            return jsonify({
                'success': False,
                'error': 'namespace参数必需'
            }), 400

        deployments = kubectl.get_deployments(namespace)

        return jsonify({
            'success': True,
            'data': deployments,
            'count': len(deployments)
        })
    except Exception as e:
        logger.error(f"获取deployments失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/deployments/pods', methods=['GET'])
def get_deployment_pods():
    """
    获取deployment的所有pod
    Query参数:
      - namespace: namespace名称 (必需)
      - deployment: deployment名称 (必需)
    """
    try:
        namespace = request.args.get('namespace')
        deployment = request.args.get('deployment')

        if not namespace or not deployment:
            return jsonify({
                'success': False,
                'error': 'namespace和deployment参数必需'
            }), 400

        pods = kubectl.get_pods_by_deployment(namespace, deployment)

        return jsonify({
            'success': True,
            'data': pods,
            'count': len(pods)
        })
    except Exception as e:
        logger.error(f"获取deployment pods失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/deployments/logs', methods=['POST'])
def query_deployment_logs():
    """
    查询deployment所有pod的日志
    Body参数:
    {
      "namespace": "erp-prod",
      "deployment": "app-server",
      "type": "all",
      "tail": 2000,
      "keywords": ["error"]
    }
    """
    try:
        data = request.get_json()

        namespace = data.get('namespace')
        deployment = data.get('deployment')
        if not namespace or not deployment:
            return jsonify({
                'success': False,
                'error': 'namespace和deployment参数必需'
            }), 400

        log_type = data.get('type', 'all')
        tail = min(int(data.get('tail', 2000)), MAX_TAIL_LINES)
        keywords = data.get('keywords', [])

        # 获取deployment的所有pod
        pods = kubectl.get_pods_by_deployment(namespace, deployment)

        # 查询每个pod的日志
        results = []
        for pod_info in pods:
            pod = pod_info['name']
            logs = kubectl.get_all_logs(namespace, pod, tail, keywords, log_type)

            console_matches = len(logs['console_log'])
            file_matches = sum(len(lines) for lines in logs['file_logs'].values())

            results.append({
                'pod': pod,
                'status': pod_info['status'],
                'ready': pod_info['ready'],
                'console_matches': console_matches,
                'file_matches': file_matches,
                'total_matches': console_matches + file_matches,
                'logs': logs
            })

        total_matches = sum(r['total_matches'] for r in results)

        return jsonify({
            'success': True,
            'data': {
                'namespace': namespace,
                'deployment': deployment,
                'pods': results,
                'total_pods': len(results),
                'total_matches': total_matches
            }
        })
    except Exception as e:
        logger.error(f"查询deployment日志失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pods/files', methods=['GET'])
def list_pod_files():
    """
    列出Pod中的文件
    Query参数:
      - namespace: namespace名称
      - pod: pod名称
      - path: 目录路径，默认/applog
    """
    try:
        namespace = request.args.get('namespace')
        pod = request.args.get('pod')
        path = request.args.get('path', '/applog')

        if not namespace or not pod:
            return jsonify({
                'success': False,
                'error': 'namespace和pod参数必需'
            }), 400

        # 查找文件
        files = kubectl.find_history_log_files(namespace, pod, path, '*.log')

        return jsonify({
            'success': True,
            'data': files,
            'count': len(files)
        })
    except Exception as e:
        logger.error(f"列出pod文件失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pods/copy', methods=['POST'])
def copy_pod_file():
    """
    从Pod复制文件
    Body参数:
    {
      "namespace": "erp-prod",
      "pod": "pod-name",
      "file_path": "/applog/root.log"
    }
    """
    try:
        data = request.get_json()

        namespace = data.get('namespace')
        pod = data.get('pod')
        file_path = data.get('file_path')

        if not namespace or not pod or not file_path:
            return jsonify({
                'success': False,
                'error': 'namespace、pod和file_path参数必需'
            }), 400

        # 生成本地文件名
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = os.path.basename(file_path)
        dest_path = os.path.join(FILES_DIR, f"{namespace}-{pod}-{filename}-{timestamp}")

        # 复制文件
        success = kubectl.copy_file_from_pod(namespace, pod, file_path, dest_path)

        if success:
            # 返回文件供下载
            return send_file(
                dest_path,
                as_attachment=True,
                download_name=f"{namespace}-{pod}-{filename}"
            )
        else:
            return jsonify({
                'success': False,
                'error': '文件复制失败'
            }), 500
    except Exception as e:
        logger.error(f"复制pod文件失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pods/details', methods=['GET'])
def get_pod_details():
    """
    获取Pod详细信息
    Query参数:
      - namespace: namespace名称
      - pod: pod名称
    """
    try:
        namespace = request.args.get('namespace')
        pod = request.args.get('pod')

        if not namespace or not pod:
            return jsonify({
                'success': False,
                'error': 'namespace和pod参数必需'
            }), 400

        details = kubectl.get_pod_details(namespace, pod)

        if details:
            return jsonify({
                'success': True,
                'data': details
            })
        else:
            return jsonify({
                'success': False,
                'error': '获取pod详情失败'
            }), 500
    except Exception as e:
        logger.error(f"获取pod详情失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/logs/history', methods=['POST'])
def query_history_logs():
    """
    查询历史日志文件
    Body参数:
    {
      "namespace": "erp-prod",
      "pod": "pod-name",
      "log_dir": "/applog",
      "tail": 1000,
      "keywords": ["error"]
    }
    """
    try:
        data = request.get_json()

        namespace = data.get('namespace')
        pod = data.get('pod')
        if not namespace or not pod:
            return jsonify({
                'success': False,
                'error': 'namespace和pod参数必需'
            }), 400

        log_dir = data.get('log_dir', '/applog')
        tail = min(int(data.get('tail', 1000)), MAX_TAIL_LINES)
        keywords = data.get('keywords', [])

        # 查找所有日志文件
        log_files = kubectl.find_history_log_files(namespace, pod, log_dir, '*.log')

        # 查询每个文件的日志
        results = {}
        for filepath in log_files:
            file_lines, file_total = kubectl.get_file_log(
                namespace, pod, filepath, tail, keywords
            )
            if file_lines:
                results[filepath] = {
                    'lines': file_lines,
                    'total': file_total,
                    'matched': len(file_lines)
                }

        total_matches = sum(r['matched'] for r in results.values())

        return jsonify({
            'success': True,
            'data': {
                'namespace': namespace,
                'pod': pod,
                'files': results,
                'total_files': len(results),
                'total_matches': total_matches
            }
        })
    except Exception as e:
        logger.error(f"查询历史日志失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not Found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal Server Error'}), 500


if __name__ == '__main__':
    # 开发模式
    app.run(host='0.0.0.0', port=5000, debug=True)
