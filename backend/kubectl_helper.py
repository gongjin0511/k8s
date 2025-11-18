"""
kubectl命令封装模块
提供K8s资源查询和日志获取功能
"""

import subprocess
import json
import re
import fnmatch
from typing import List, Dict, Optional, Tuple
import logging
from cache_manager import cached

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KubectlHelper:
    """kubectl命令行工具封装类"""

    def __init__(self, timeout: int = 300):
        """
        初始化
        :param timeout: kubectl命令执行超时时间(秒)
        """
        self.timeout = timeout
        self._verify_kubectl()

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

    def run_kubectl(self, cmd: List[str], timeout: Optional[int] = None) -> Dict:
        """
        执行kubectl命令
        :param cmd: kubectl命令参数列表
        :param timeout: 超时时间，None则使用默认值
        :return: {'success': bool, 'stdout': str, 'stderr': str, 'error': str}
        """
        timeout = timeout or self.timeout
        full_cmd = ['kubectl'] + cmd

        try:
            logger.info(f"执行命令: {' '.join(full_cmd)}")
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
        except subprocess.TimeoutExpired:
            error_msg = f"命令执行超时 ({timeout}秒)"
            logger.error(error_msg)
            return {'success': False, 'stdout': '', 'stderr': '', 'error': error_msg}
        except Exception as e:
            error_msg = f"命令执行异常: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'stdout': '', 'stderr': '', 'error': error_msg}

    def get_namespaces(self, patterns: Optional[List[str]] = None) -> List[str]:
        """
        获取namespace列表
        :param patterns: 通配符模式列表，如 ['erp-*', 'cnnc-*']
        :return: namespace名称列表
        """
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
        :param namespace: namespace名称
        :param status_filter: 状态过滤，默认只返回Running状态的pod
        :return: pod信息列表 [{'name': str, 'status': str, 'ready': bool}]
        """
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

    def get_console_log(
        self,
        namespace: str,
        pod: str,
        tail: int = 2000,
        keywords: Optional[List[str]] = None
    ) -> Tuple[List[str], int]:
        """
        获取Pod的Console日志
        :param namespace: namespace名称
        :param pod: pod名称
        :param tail: 获取最后N行
        :param keywords: 关键字列表，用于过滤日志
        :return: (日志行列表, 总行数)
        """
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
            logger.info(f"Console日志 [{namespace}/{pod}]: 总行数={total_lines}, 匹配行数={len(filtered_lines)}")
            return filtered_lines, total_lines

        return lines, total_lines

    def find_log_files(self, namespace: str, pod: str, log_dir: str = '/applog') -> List[str]:
        """
        查找Pod内的日志文件
        :param namespace: namespace名称
        :param pod: pod名称
        :param log_dir: 日志目录路径
        :return: 日志文件路径列表
        """
        # 查找root.log文件
        cmd = ['exec', '-n', namespace, pod, '--', 'find', log_dir, '-name', 'root.log', '-type', 'f']
        result = self.run_kubectl(cmd, timeout=30)

        if not result['success']:
            logger.warning(f"查找日志文件失败 [{namespace}/{pod}]: {result['error']}")
            return []

        files = [f.strip() for f in result['stdout'].split('\n') if f.strip()]
        logger.info(f"在 [{namespace}/{pod}] 找到 {len(files)} 个日志文件")
        return files

    def get_file_log(
        self,
        namespace: str,
        pod: str,
        filepath: str,
        tail: int = 2000,
        keywords: Optional[List[str]] = None
    ) -> Tuple[List[str], int]:
        """
        获取Pod内文件日志
        :param namespace: namespace名称
        :param pod: pod名称
        :param filepath: 文件路径
        :param tail: 获取最后N行
        :param keywords: 关键字列表
        :return: (日志行列表, 总行数)
        """
        # 构建命令
        if keywords:
            # 使用grep过滤
            keyword_pattern = '|'.join(keywords)
            cmd = [
                'exec', '-n', namespace, pod, '--', 'sh', '-c',
                f"tail -n {tail} {filepath} | grep -iE '{keyword_pattern}'"
            ]
        else:
            cmd = ['exec', '-n', namespace, pod, '--', 'tail', '-n', str(tail), filepath]

        result = self.run_kubectl(cmd, timeout=120)

        if not result['success']:
            # grep没有匹配时也会返回非0退出码，但这不算错误
            if keywords and 'grep' in ' '.join(cmd):
                logger.info(f"文件日志无匹配 [{namespace}/{pod}:{filepath}]")
                return [], 0
            else:
                logger.warning(f"获取文件日志失败 [{namespace}/{pod}:{filepath}]: {result['error']}")
                return [], 0

        lines = result['stdout'].split('\n')
        total_lines = len([l for l in lines if l.strip()])

        logger.info(f"文件日志 [{namespace}/{pod}:{filepath}]: 匹配行数={total_lines}")
        return lines, total_lines

    def get_all_logs(
        self,
        namespace: str,
        pod: str,
        tail: int = 2000,
        keywords: Optional[List[str]] = None,
        log_type: str = 'all'
    ) -> Dict:
        """
        获取Pod的所有日志（Console + 文件）
        :param namespace: namespace名称
        :param pod: pod名称
        :param tail: 每个日志源获取的行数
        :param keywords: 关键字过滤列表
        :param log_type: 日志类型 'console' | 'file' | 'all'
        :return: {
            'console_log': [lines],
            'console_total': int,
            'file_logs': {filepath: [lines]},
            'file_totals': {filepath: int}
        }
        """
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
        """
        使用关键字过滤日志行
        :param lines: 日志行列表
        :param keywords: 关键字列表
        :return: 匹配的日志行
        """
        if not keywords:
            return lines

        # 构建正则表达式 (OR逻辑，大小写不敏感)
        pattern = '|'.join(re.escape(kw) for kw in keywords)
        regex = re.compile(pattern, re.IGNORECASE)

        matched = [line for line in lines if regex.search(line)]
        return matched

    def get_pods_by_namespace_group(self, patterns: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
        """
        按命名空间分组获取所有Pods
        :param patterns: 通配符模式列表
        :return: {namespace: [pods]}
        """
        namespaces = self.get_namespaces(patterns)
        grouped_pods = {}

        for namespace in namespaces:
            pods = self.get_pods(namespace, status_filter='Running')
            if pods:
                grouped_pods[namespace] = pods

        logger.info(f"按命名空间分组获取Pods: {len(grouped_pods)}个命名空间")
        return grouped_pods

    def get_deployments(self, namespace: str) -> List[Dict]:
        """
        获取指定namespace的所有deployments和statefulsets
        :param namespace: namespace名称
        :return: 部署单元列表 [{'name': str, 'type': str, 'replicas': int}]
        """
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

    def get_deployment_pods(self, namespace: str, deployment: str) -> List[str]:
        """
        获取Deployment/StatefulSet的所有Pod
        :param namespace: namespace名称
        :param deployment: deployment或statefulset名称
        :return: pod名称列表
        """
        # 先尝试作为deployment
        result = self.run_kubectl(['get', 'deployment', deployment, '-n', namespace, '-o', 'json'])

        if not result['success']:
            # 再尝试作为statefulset
            result = self.run_kubectl(['get', 'statefulset', deployment, '-n', namespace, '-o', 'json'])

        if not result['success']:
            logger.warning(f"未找到deployment/statefulset: {namespace}/{deployment}")
            return []

        try:
            data = json.loads(result['stdout'])
            # 获取selector labels
            selector_labels = data.get('spec', {}).get('selector', {}).get('matchLabels', {})

            if not selector_labels:
                logger.warning(f"无法获取selector labels: {namespace}/{deployment}")
                return []

            # 构建label selector
            label_selector = ','.join([f"{k}={v}" for k, v in selector_labels.items()])

            # 获取匹配的pods
            result = self.run_kubectl(['get', 'pods', '-n', namespace, '-l', label_selector, '-o', 'json'])

            if not result['success']:
                return []

            data = json.loads(result['stdout'])
            pod_names = [item['metadata']['name'] for item in data.get('items', [])]

            logger.info(f"找到 {len(pod_names)} 个pods for {namespace}/{deployment}")
            return pod_names

        except json.JSONDecodeError as e:
            logger.error(f"解析JSON失败: {str(e)}")
            return []

    def get_error_context(
        self,
        namespace: str,
        pod: str,
        error_keywords: List[str],
        context_lines: int = 50,
        log_type: str = 'all'
    ) -> Dict:
        """
        获取错误日志的上下文
        :param namespace: namespace名称
        :param pod: pod名称
        :param error_keywords: 错误关键字列表
        :param context_lines: 上下文行数
        :param log_type: 日志类型
        :return: 包含错误及上下文的日志
        """
        result = {
            'console_errors': [],
            'file_errors': {}
        }

        # Console日志错误上下文
        if log_type in ['console', 'all']:
            console_errors = self._get_console_error_context(namespace, pod, error_keywords, context_lines)
            result['console_errors'] = console_errors

        # 文件日志错误上下文
        if log_type in ['file', 'all']:
            log_files = self.find_log_files(namespace, pod)
            for filepath in log_files:
                file_errors = self._get_file_error_context(namespace, pod, filepath, error_keywords, context_lines)
                if file_errors:
                    result['file_errors'][filepath] = file_errors

        return result

    def _get_console_error_context(
        self,
        namespace: str,
        pod: str,
        error_keywords: List[str],
        context_lines: int
    ) -> List[Dict]:
        """
        获取Console日志中错误的上下文
        :return: [{'error_line': str, 'line_number': int, 'context': [lines]}]
        """
        # 获取最近5000行日志（确保能找到最新错误）
        cmd = ['logs', '-n', namespace, pod, '--tail=5000']
        result = self.run_kubectl(cmd, timeout=120)

        if not result['success']:
            logger.warning(f"获取console日志失败: {namespace}/{pod}")
            return []

        lines = result['stdout'].split('\n')
        return self._extract_error_contexts(lines, error_keywords, context_lines)

    def _get_file_error_context(
        self,
        namespace: str,
        pod: str,
        filepath: str,
        error_keywords: List[str],
        context_lines: int
    ) -> List[Dict]:
        """
        获取文件日志中错误的上下文
        """
        # 获取最近5000行
        cmd = ['exec', '-n', namespace, pod, '--', 'tail', '-n', '5000', filepath]
        result = self.run_kubectl(cmd, timeout=120)

        if not result['success']:
            logger.warning(f"获取文件日志失败: {namespace}/{pod}:{filepath}")
            return []

        lines = result['stdout'].split('\n')
        return self._extract_error_contexts(lines, error_keywords, context_lines)

    def _extract_error_contexts(
        self,
        lines: List[str],
        error_keywords: List[str],
        context_lines: int
    ) -> List[Dict]:
        """
        从日志行中提取错误及其上下文
        :return: [{'error_line': str, 'line_number': int, 'before': [...], 'after': [...]}]
        """
        # 构建正则表达式
        pattern = '|'.join(re.escape(kw) for kw in error_keywords)
        regex = re.compile(pattern, re.IGNORECASE)

        error_contexts = []

        for i, line in enumerate(lines):
            if regex.search(line):
                # 找到错误行，提取上下文
                before_start = max(0, i - context_lines)
                after_end = min(len(lines), i + context_lines + 1)

                error_contexts.append({
                    'error_line': line,
                    'line_number': i + 1,
                    'before': lines[before_start:i],
                    'after': lines[i+1:after_end]
                })

        logger.info(f"找到 {len(error_contexts)} 个错误上下文")
        return error_contexts

    def batch_query_logs(
        self,
        namespace_patterns: List[str],
        keywords: List[str],
        tail: int = 2000,
        log_type: str = 'all',
        max_pods: int = 100
    ) -> List[Dict]:
        """
        批量查询日志
        :param namespace_patterns: namespace通配符列表
        :param keywords: 关键字列表
        :param tail: 每个日志源的行数
        :param log_type: 日志类型
        :param max_pods: 最大查询pod数量
        :return: 查询结果列表
        """
        results = []

        # 获取匹配的namespace
        namespaces = self.get_namespaces(namespace_patterns)
        logger.info(f"批量查询: {len(namespaces)} 个namespace")

        pod_count = 0
        for namespace in namespaces:
            if pod_count >= max_pods:
                logger.warning(f"达到最大pod数限制 ({max_pods})，停止查询")
                break

            # 获取Running状态的pod
            pods = self.get_pods(namespace, status_filter='Running')

            for pod_info in pods:
                if pod_count >= max_pods:
                    break

                pod_name = pod_info['name']
                pod_count += 1

                logger.info(f"查询进度: {pod_count}/{max_pods} - {namespace}/{pod_name}")

                # 获取日志
                logs = self.get_all_logs(namespace, pod_name, tail, keywords, log_type)

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

        logger.info(f"批量查询完成: 查询了{pod_count}个pod, {len(results)}个有匹配")
        return results

    def exec_command(self, namespace: str, pod: str, command: str, container: Optional[str] = None) -> Dict:
        """
        在Pod中执行命令

        :param namespace: 命名空间
        :param pod: Pod名称
        :param command: 要执行的命令
        :param container: 容器名称（可选）
        :return: 命令执行结果
        """
        cmd = ['exec', pod, '-n', namespace]

        if container:
            cmd.extend(['-c', container])

        cmd.extend(['--', 'sh', '-c', command])

        result = self.run_kubectl(cmd, timeout=60)

        if not result['success']:
            logger.error(f"执行命令失败 ({namespace}/{pod}): {command}")
            logger.error(f"错误: {result['error']}")

        return result

    def list_log_files(self, namespace: str, pod: str, log_path: str = '/applog/') -> List[Dict]:
        """
        列出Pod中的日志文件

        :param namespace: 命名空间
        :param pod: Pod名称
        :param log_path: 日志目录路径
        :return: 文件列表
        """
        # 使用 ls -lh 列出文件详情
        cmd = f'ls -lh {log_path} 2>/dev/null || echo "DIRECTORY_NOT_FOUND"'
        result = self.exec_command(namespace, pod, cmd)

        if not result['success']:
            logger.error(f"列出日志文件失败: {namespace}/{pod}")
            return []

        output = result['stdout'].strip()

        if 'DIRECTORY_NOT_FOUND' in output or not output:
            logger.warning(f"目录不存在: {namespace}/{pod}/{log_path}")
            return []

        # 解析 ls -lh 输出
        files = []
        lines = output.split('\n')

        for line in lines:
            # 跳过total行和空行
            if line.startswith('total') or not line.strip():
                continue

            # 解析ls -lh输出格式
            # -rw-r--r-- 1 root root 45M Jan 18 10:30 root.log
            match = re.match(
                r'([d-])([rwx-]{9})\s+\d+\s+\w+\s+\w+\s+(\S+)\s+(\w+\s+\d+\s+[\d:]+)\s+(.+)',
                line
            )

            if match:
                is_dir_flag, permissions, size, date_str, name = match.groups()

                # 构建完整路径
                full_path = f"{log_path.rstrip('/')}/{name}" if log_path != name else name

                files.append({
                    'name': name,
                    'path': full_path,
                    'size_human': size,
                    'size_bytes': self._parse_size(size),
                    'date': date_str,
                    'is_directory': is_dir_flag == 'd',
                    'permissions': permissions
                })

        logger.info(f"列出 {len(files)} 个文件/目录: {namespace}/{pod}/{log_path}")
        return files

    def _parse_size(self, size_str: str) -> int:
        """
        解析人类可读的文件大小为字节数

        :param size_str: 如 "45M", "1.2G", "500K"
        :return: 字节数
        """
        size_str = size_str.strip()

        # 单位映射
        units = {
            'B': 1,
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }

        # 提取数字和单位
        match = re.match(r'([\d.]+)([BKMGT])?', size_str, re.IGNORECASE)
        if not match:
            return 0

        number, unit = match.groups()
        number = float(number)
        unit = (unit or 'B').upper()

        return int(number * units.get(unit, 1))

    def get_file_content(self, namespace: str, pod: str, file_path: str,
                        offset: int = 0, limit: int = 1000) -> Dict:
        """
        获取日志文件内容（分页）

        :param namespace: 命名空间
        :param pod: Pod名称
        :param file_path: 文件路径
        :param offset: 起始行号（从0开始）
        :param limit: 返回行数
        :return: {'content': List[str], 'total_lines': int}
        """
        # 先获取总行数
        wc_cmd = f"wc -l < {file_path} 2>/dev/null || echo 0"
        wc_result = self.exec_command(namespace, pod, wc_cmd)

        if not wc_result['success']:
            logger.error(f"获取文件行数失败: {file_path}")
            return {'content': [], 'total_lines': 0}

        total_lines = int(wc_result['stdout'].strip() or '0')

        # 使用 sed 读取指定行范围
        start = offset + 1  # sed行号从1开始
        end = offset + limit

        sed_cmd = f"sed -n '{start},{end}p' {file_path} 2>/dev/null || echo 'FILE_NOT_FOUND'"
        sed_result = self.exec_command(namespace, pod, sed_cmd)

        if not sed_result['success'] or 'FILE_NOT_FOUND' in sed_result['stdout']:
            logger.error(f"读取文件内容失败: {file_path}")
            return {'content': [], 'total_lines': 0}

        content = sed_result['stdout'].split('\n')

        # 移除最后的空行
        if content and content[-1] == '':
            content = content[:-1]

        logger.info(f"读取文件: {file_path} (行 {start}-{end}/{total_lines})")

        return {
            'content': content,
            'total_lines': total_lines,
            'offset': offset,
            'limit': limit,
            'has_more': end < total_lines
        }

    def tail_file(self, namespace: str, pod: str, file_path: str, lines: int = 100) -> List[str]:
        """
        获取文件末尾内容（类似tail命令）

        :param namespace: 命名空间
        :param pod: Pod名称
        :param file_path: 文件路径
        :param lines: 返回行数
        :return: 文件末尾内容
        """
        cmd = f"tail -n {lines} {file_path} 2>/dev/null || echo 'FILE_NOT_FOUND'"
        result = self.exec_command(namespace, pod, cmd)

        if not result['success'] or 'FILE_NOT_FOUND' in result['stdout']:
            logger.error(f"tail文件失败: {file_path}")
            return []

        content = result['stdout'].strip().split('\n')

        logger.info(f"Tail文件: {file_path} (最后 {len(content)} 行)")
        return content

    def search_in_file(self, namespace: str, pod: str, file_path: str,
                      pattern: str, max_results: int = 100) -> List[Dict]:
        """
        在文件中搜索关键词

        :param namespace: 命名空间
        :param pod: Pod名称
        :param file_path: 文件路径
        :param pattern: 搜索模式（支持正则）
        :param max_results: 最大结果数
        :return: 匹配结果列表
        """
        # 使用 grep -n 搜索，显示行号
        # -i: 忽略大小写, -n: 显示行号, -m: 最大匹配数
        cmd = f"grep -in -m {max_results} '{pattern}' {file_path} 2>/dev/null || echo 'NO_MATCHES'"
        result = self.exec_command(namespace, pod, cmd)

        if not result['success'] or 'NO_MATCHES' in result['stdout']:
            logger.info(f"未找到匹配: {pattern} in {file_path}")
            return []

        matches = []
        lines = result['stdout'].strip().split('\n')

        for line in lines:
            # 格式: 行号:内容
            match = re.match(r'(\d+):(.+)', line)
            if match:
                line_num, content = match.groups()
                matches.append({
                    'line_number': int(line_num),
                    'content': content.strip()
                })

        logger.info(f"找到 {len(matches)} 处匹配: {pattern} in {file_path}")
        return matches
