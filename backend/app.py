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
os.makedirs(LOGS_DIR, exist_ok=True)

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


@app.route('/api/pods/grouped', methods=['GET'])
def get_pods_grouped():
    """
    按命名空间分组获取Pods
    Query参数:
      - pattern: 通配符模式，多个用逗号分隔
    """
    try:
        pattern_str = request.args.get('pattern', '')
        patterns = [p.strip() for p in pattern_str.split(',') if p.strip()] if pattern_str else None

        grouped_pods = kubectl.get_pods_by_namespace_group(patterns)

        return jsonify({
            'success': True,
            'data': grouped_pods,
            'namespace_count': len(grouped_pods)
        })
    except Exception as e:
        logger.error(f"获取分组pods失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/deployments', methods=['GET'])
def get_deployments():
    """
    获取指定namespace的所有deployments和statefulsets
    Query参数:
      - namespace: 命名空间 (必需)
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


@app.route('/api/deployment/pods', methods=['GET'])
def get_deployment_pods():
    """
    获取Deployment/StatefulSet的所有Pods
    Query参数:
      - namespace: 命名空间
      - deployment: deployment或statefulset名称
    """
    try:
        namespace = request.args.get('namespace')
        deployment = request.args.get('deployment')

        if not namespace or not deployment:
            return jsonify({
                'success': False,
                'error': 'namespace和deployment参数必需'
            }), 400

        pod_names = kubectl.get_deployment_pods(namespace, deployment)

        return jsonify({
            'success': True,
            'data': pod_names,
            'count': len(pod_names)
        })
    except Exception as e:
        logger.error(f"获取deployment pods失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/logs/error-context', methods=['POST'])
def get_error_context():
    """
    获取错误日志的上下文
    Body参数:
    {
      "namespace": "erp-prod",
      "pod": "pod-name",  // 可选，如果提供deployment则忽略
      "deployment": "deployment-name",  // 可选，查询整个部署单元
      "error_keywords": ["error", "exception"],
      "context_lines": 50,
      "type": "all"
    }
    """
    try:
        data = request.get_json()

        namespace = data.get('namespace')
        if not namespace:
            return jsonify({
                'success': False,
                'error': 'namespace参数必需'
            }), 400

        error_keywords = data.get('error_keywords', ['error', 'exception', 'fatal'])
        context_lines = min(int(data.get('context_lines', 50)), 200)  # 最大200行上下文
        log_type = data.get('type', 'all')

        # 获取Pod列表
        pods = []
        deployment = data.get('deployment')
        if deployment:
            # 查询整个部署单元
            pods = kubectl.get_deployment_pods(namespace, deployment)
            if not pods:
                return jsonify({
                    'success': False,
                    'error': f'未找到deployment: {deployment}'
                }), 404
        else:
            # 单个Pod
            pod = data.get('pod')
            if not pod:
                return jsonify({
                    'success': False,
                    'error': 'pod或deployment参数至少需要一个'
                }), 400
            pods = [pod]

        # 查询每个Pod的错误上下文
        results = []
        for pod_name in pods:
            error_context = kubectl.get_error_context(
                namespace, pod_name, error_keywords, context_lines, log_type
            )

            # 统计错误数
            console_error_count = len(error_context['console_errors'])
            file_error_count = sum(len(errors) for errors in error_context['file_errors'].values())
            total_error_count = console_error_count + file_error_count

            if total_error_count > 0:
                results.append({
                    'namespace': namespace,
                    'pod': pod_name,
                    'console_error_count': console_error_count,
                    'file_error_count': file_error_count,
                    'total_error_count': total_error_count,
                    'error_context': error_context
                })

        return jsonify({
            'success': True,
            'data': results,
            'total_pods': len(pods),
            'pods_with_errors': len(results)
        })
    except Exception as e:
        logger.error(f"获取错误上下文失败: {str(e)}", exc_info=True)
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


@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not Found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal Server Error'}), 500


if __name__ == '__main__':
    # 开发模式
    app.run(host='0.0.0.0', port=5000, debug=True)
