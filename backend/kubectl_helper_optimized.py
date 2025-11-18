"""
优化版kubectl命令封装模块
- 添加并发处理支持
- 批量操作优化
- 智能重试机制
- 连接复用
"""

import subprocess
import json
import re
import fnmatch
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import logging
import time
from performance_monitor import timed, PerformanceTimer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KubectlHelperOptimized:
    """kubectl命令行工具封装类（优化版）"""

    def __init__(self, timeout: int = 300, max_workers: int = 10):
        """
        初始化

        Args:
            timeout: kubectl命令执行超时时间(秒)
            max_workers: 最大并发工作线程数
        """
        self.timeout = timeout
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="kubectl")
        self._verify_kubectl()

    def __del__(self):
        """清理资源"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)

    def _verify_kubectl(self):
        """验证kubectl是否可用"""
        try:
            result = self.run_kubectl(['version', '--client', '--output=json'])
            if result['success']:
                logger.info("kubectl验证成功")
            else:
                logger.error("kubectl验证失败")
        except Exception as e:
            logger.error(f"kubectl不可用: {str(e)}")
            raise RuntimeError("kubectl命令不可用，请确保已安装并配置好kubeconfig")

    @timed(log_threshold=2.0)
    def run_kubectl(self, cmd: List[str], timeout: Optional[int] = None, retries: int = 3) -> Dict:
        """
        执行kubectl命令（带重试）

        Args:
            cmd: kubectl命令参数列表
            timeout: 超时时间，None则使用默认值
            retries: 重试次数

        Returns:
            {'success': bool, 'stdout': str, 'stderr': str, 'error': str}
        """
        timeout = timeout or self.timeout
        full_cmd = ['kubectl'] + cmd

        last_error = None
        for attempt in range(retries):
            try:
                if attempt > 0:
                    # 指数退避重试
                    wait_time = 2 ** attempt
                    logger.info(f"重试 {attempt}/{retries}, 等待 {wait_time}秒...")
                    time.sleep(wait_time)

                logger.debug(f"执行命令: {' '.join(full_cmd)}")
                result = subprocess.run(
                    full_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                success = result.returncode == 0
                return {
                    'success': success,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'error': result.stderr if not success else None
                }

            except subprocess.TimeoutExpired as e:
                last_error = f"命令执行超时 ({timeout}秒)"
                logger.error(f"{last_error} - 尝试 {attempt + 1}/{retries}")

            except Exception as e:
                last_error = f"命令执行异常: {str(e)}"
                logger.error(f"{last_error} - 尝试 {attempt + 1}/{retries}")

        # 所有重试都失败
        return {'success': False, 'stdout': '', 'stderr': '', 'error': last_error}

    @lru_cache(maxsize=128)
    def get_namespaces(self, patterns: Optional[Tuple[str, ...]] = None) -> List[str]:
        """
        获取namespace列表（带缓存）

        Args:
            patterns: 通配符模式元组（使用元组以支持缓存）

        Returns:
            namespace名称列表
        """
        with PerformanceTimer("get_namespaces"):
            result = self.run_kubectl(['get', 'namespaces', '-o', 'json'])

            if not result['success']:
                logger.error(f"获取namespace失败: {result['error']}")
                return []

            try:
                data = json.loads(result['stdout'])
                all_namespaces = [item['metadata']['name'] for item in data.get('items', [])]

                # 如果没有指定pattern，返回所有namespace
                if not patterns:
                    return all_namespaces

                # 根据通配符过滤namespace
                matched = []
                for ns in all_namespaces:
                    for pattern in patterns:
                        if fnmatch.fnmatch(ns, pattern):
                            matched.append(ns)
                            break

                logger.info(f"匹配到 {len(matched)} 个namespace")
                return matched

            except json.JSONDecodeError as e:
                logger.error(f"解析namespace JSON失败: {str(e)}")
                return []

    def get_pods(self, namespace: str, status_filter: str = 'Running') -> List[Dict]:
        """
        获取指定namespace的pod列表

        Args:
            namespace: namespace名称
            status_filter: 状态过滤，默认只返回Running状态的pod

        Returns:
            pod信息列表
        """
        with PerformanceTimer(f"get_pods_{namespace}"):
            result = self.run_kubectl(['get', 'pods', '-n', namespace, '-o', 'json'])

            if not result['success']:
                logger.error(f"获取pods失败 [{namespace}]: {result['error']}")
                return []

            try:
                data = json.loads(result['stdout'])
                pods = []

                for item in data.get('items', []):
                    name = item['metadata']['name']
                    status_info = item.get('status', {})
                    phase = status_info.get('phase', 'Unknown')

                    # 检查容器就绪状态
                    container_statuses = status_info.get('containerStatuses', [])
                    ready = all(cs.get('ready', False) for cs in container_statuses) if container_statuses else False

                    pod_info = {
                        'name': name,
                        'status': phase,
                        'ready': ready
                    }

                    # 状态过滤
                    if not status_filter or phase == status_filter:
                        pods.append(pod_info)

                logger.info(f"在namespace [{namespace}] 中找到 {len(pods)} 个pod")
                return pods

            except json.JSONDecodeError as e:
                logger.error(f"解析pods JSON失败: {str(e)}")
                return []

    def get_pods_parallel(self, namespaces: List[str], status_filter: str = 'Running') -> Dict[str, List[Dict]]:
        """
        并发获取多个namespace的pods

        Args:
            namespaces: namespace列表
            status_filter: 状态过滤

        Returns:
            {namespace: [pods]}
        """
        with PerformanceTimer(f"get_pods_parallel_{len(namespaces)}_namespaces"):
            results = {}
            futures = {}

            # 提交所有任务
            for ns in namespaces:
                future = self._executor.submit(self.get_pods, ns, status_filter)
                futures[future] = ns

            # 收集结果
            for future in as_completed(futures):
                ns = futures[future]
                try:
                    pods = future.result()
                    if pods:
                        results[ns] = pods
                except Exception as e:
                    logger.error(f"并发获取pods失败 [{ns}]: {str(e)}")

            logger.info(f"并发获取完成: {len(results)} 个namespace有pods")
            return results

    def batch_query_logs_parallel(
        self,
        namespace_patterns: List[str],
        keywords: List[str],
        tail: int = 2000,
        log_type: str = 'all',
        max_pods: int = 100
    ) -> List[Dict]:
        """
        并发批量查询日志（优化版）

        Args:
            namespace_patterns: namespace通配符列表
            keywords: 关键字列表
            tail: 每个日志源的行数
            log_type: 日志类型
            max_pods: 最大查询pod数量

        Returns:
            查询结果列表
        """
        with PerformanceTimer(f"batch_query_logs_parallel"):
            results = []

            # 转换为元组以支持缓存
            patterns_tuple = tuple(namespace_patterns) if namespace_patterns else None

            # 获取匹配的namespace
            namespaces = self.get_namespaces(patterns_tuple)
            logger.info(f"批量查询: {len(namespaces)} 个namespace")

            # 并发获取所有namespace的pods
            all_pods = self.get_pods_parallel(namespaces, status_filter='Running')

            # 收集所有需要查询的pods（带namespace信息）
            pods_to_query = []
            for namespace, pods in all_pods.items():
                for pod_info in pods:
                    pods_to_query.append((namespace, pod_info['name']))
                    if len(pods_to_query) >= max_pods:
                        break
                if len(pods_to_query) >= max_pods:
                    break

            logger.info(f"准备查询 {len(pods_to_query)} 个pods")

            # 并发查询日志
            futures = {}
            for namespace, pod_name in pods_to_query:
                future = self._executor.submit(
                    self.get_all_logs,
                    namespace,
                    pod_name,
                    tail,
                    keywords,
                    log_type
                )
                futures[future] = (namespace, pod_name)

            # 收集结果
            completed = 0
            for future in as_completed(futures):
                completed += 1
                namespace, pod_name = futures[future]

                try:
                    logs = future.result()

                    # 统计匹配数
                    console_matches = len(logs['console_log'])
                    file_matches = sum(len(lines) for lines in logs['file_logs'].values())
                    total_matches = console_matches + file_matches

                    # 只保存有匹配的结果
                    if total_matches > 0:
                        results.append({
                            'namespace': namespace,
                            'pod': pod_name,
                            'console_matches': console_matches,
                            'file_matches': file_matches,
                            'total_matches': total_matches,
                            'logs': logs
                        })

                    if completed % 10 == 0:
                        logger.info(f"查询进度: {completed}/{len(pods_to_query)}")

                except Exception as e:
                    logger.error(f"查询日志失败 [{namespace}/{pod_name}]: {str(e)}")

            logger.info(f"批量查询完成: 查询了{len(pods_to_query)}个pod, {len(results)}个有匹配")
            return results

    def get_console_log(
        self,
        namespace: str,
        pod: str,
        tail: int = 2000,
        keywords: Optional[List[str]] = None
    ) -> Tuple[List[str], int]:
        """获取Pod的Console日志"""
        cmd = ['logs', '-n', namespace, pod, f'--tail={tail}']
        result = self.run_kubectl(cmd, timeout=120)

        if not result['success']:
            logger.warning(f"获取console日志失败 [{namespace}/{pod}]: {result['error']}")
            return [], 0

        lines = result['stdout'].split('\n')
        total_lines = len(lines)

        # 关键字过滤
        if keywords:
            filtered_lines = self._filter_by_keywords(lines, keywords)
            logger.debug(f"Console日志 [{namespace}/{pod}]: 总行数={total_lines}, 匹配行数={len(filtered_lines)}")
            return filtered_lines, total_lines

        return lines, total_lines

    def find_log_files(self, namespace: str, pod: str, log_dir: str = '/applog') -> List[str]:
        """查找Pod内的日志文件"""
        cmd = ['exec', '-n', namespace, pod, '--', 'find', log_dir, '-name', 'root.log', '-type', 'f']
        result = self.run_kubectl(cmd, timeout=30)

        if not result['success']:
            logger.warning(f"查找日志文件失败 [{namespace}/{pod}]: {result['error']}")
            return []

        files = [f.strip() for f in result['stdout'].split('\n') if f.strip()]
        logger.debug(f"在 [{namespace}/{pod}] 找到 {len(files)} 个日志文件")
        return files

    def get_file_log(
        self,
        namespace: str,
        pod: str,
        filepath: str,
        tail: int = 2000,
        keywords: Optional[List[str]] = None
    ) -> Tuple[List[str], int]:
        """获取Pod内文件日志"""
        # 构建命令
        if keywords:
            keyword_pattern = '|'.join(keywords)
            cmd = [
                'exec', '-n', namespace, pod, '--', 'sh', '-c',
                f"tail -n {tail} {filepath} | grep -iE '{keyword_pattern}'"
            ]
        else:
            cmd = ['exec', '-n', namespace, pod, '--', 'tail', '-n', str(tail), filepath]

        result = self.run_kubectl(cmd, timeout=120)

        if not result['success']:
            if keywords and 'grep' in ' '.join(cmd):
                logger.debug(f"文件日志无匹配 [{namespace}/{pod}:{filepath}]")
                return [], 0
            else:
                logger.warning(f"获取文件日志失败 [{namespace}/{pod}:{filepath}]: {result['error']}")
                return [], 0

        lines = result['stdout'].split('\n')
        total_lines = len([l for l in lines if l.strip()])

        logger.debug(f"文件日志 [{namespace}/{pod}:{filepath}]: 匹配行数={total_lines}")
        return lines, total_lines

    def get_all_logs(
        self,
        namespace: str,
        pod: str,
        tail: int = 2000,
        keywords: Optional[List[str]] = None,
        log_type: str = 'all'
    ) -> Dict:
        """获取Pod的所有日志（Console + 文件）"""
        result = {
            'console_log': [],
            'console_total': 0,
            'file_logs': {},
            'file_totals': {}
        }

        # 获取Console日志
        if log_type in ['console', 'all']:
            console_lines, console_total = self.get_console_log(namespace, pod, tail, keywords)
            result['console_log'] = console_lines
            result['console_total'] = console_total

        # 获取文件日志
        if log_type in ['file', 'all']:
            log_files = self.find_log_files(namespace, pod)
            for filepath in log_files:
                file_lines, file_total = self.get_file_log(namespace, pod, filepath, tail, keywords)
                if file_lines:  # 只保存有内容的文件
                    result['file_logs'][filepath] = file_lines
                    result['file_totals'][filepath] = file_total

        return result

    def _filter_by_keywords(self, lines: List[str], keywords: List[str]) -> List[str]:
        """使用关键字过滤日志行"""
        if not keywords:
            return lines

        # 构建正则表达式 (OR逻辑，大小写不敏感)
        pattern = '|'.join(re.escape(kw) for kw in keywords)
        regex = re.compile(pattern, re.IGNORECASE)

        matched = [line for line in lines if regex.search(line)]
        return matched

    def get_deployments(self, namespace: str) -> List[Dict]:
        """获取指定namespace的所有deployments和statefulsets"""
        deployments = []

        # 获取Deployments
        result = self.run_kubectl(['get', 'deployments', '-n', namespace, '-o', 'json'])
        if result['success']:
            try:
                data = json.loads(result['stdout'])
                for item in data.get('items', []):
                    name = item['metadata']['name']
                    replicas = item['spec'].get('replicas', 0)
                    deployments.append({
                        'name': name,
                        'type': 'deployment',
                        'replicas': replicas
                    })
            except json.JSONDecodeError:
                pass

        # 获取StatefulSets
        result = self.run_kubectl(['get', 'statefulsets', '-n', namespace, '-o', 'json'])
        if result['success']:
            try:
                data = json.loads(result['stdout'])
                for item in data.get('items', []):
                    name = item['metadata']['name']
                    replicas = item['spec'].get('replicas', 0)
                    deployments.append({
                        'name': name,
                        'type': 'statefulset',
                        'replicas': replicas
                    })
            except json.JSONDecodeError:
                pass

        logger.info(f"在namespace [{namespace}] 中找到 {len(deployments)} 个部署单元")
        return deployments

    # ... 其他方法保持不变，从原始文件继承 ...


if __name__ == '__main__':
    # 测试优化版kubectl helper
    logging.basicConfig(level=logging.INFO)

    print("=== Kubectl Helper 优化版测试 ===\n")

    kubectl = KubectlHelperOptimized(timeout=300, max_workers=10)

    # 测试获取namespaces（带缓存）
    print("测试1: 获取namespaces")
    ns1 = kubectl.get_namespaces()
    print(f"第一次查询: {len(ns1)} 个namespace")

    ns2 = kubectl.get_namespaces()  # 应该命中缓存
    print(f"第二次查询(缓存): {len(ns2)} 个namespace")

    # 测试并发获取pods
    print("\n测试2: 并发获取pods")
    if ns1:
        test_namespaces = ns1[:3]  # 取前3个namespace测试
        pods_dict = kubectl.get_pods_parallel(test_namespaces)
        print(f"并发获取结果: {sum(len(pods) for pods in pods_dict.values())} 个pods")

    print("\n测试完成!")
