"""
工具模块 - 提供限流、重试、验证等通用功能
"""

import time
import functools
import logging
import re
from typing import Callable, Any, Optional
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ==================== API 限流 ====================

class RateLimiter:
    """令牌桶算法实现的API限流器"""

    def __init__(self, rate: int = 60, burst: int = 10):
        """
        初始化限流器

        Args:
            rate: 每分钟允许的请求数
            burst: 突发流量允许的最大请求数
        """
        self.rate = rate  # 每分钟请求数
        self.burst = burst  # 突发容量
        self.tokens = burst  # 当前令牌数
        self.last_update = time.time()
        self.lock = Lock()

        # 统计信息
        self.total_requests = 0
        self.blocked_requests = 0

        # 每个IP的限流
        self.ip_buckets = defaultdict(lambda: {'tokens': burst, 'last_update': time.time()})

    def _refill(self, bucket: dict):
        """补充令牌"""
        now = time.time()
        elapsed = now - bucket['last_update']

        # 每秒补充 rate/60 个令牌
        tokens_to_add = elapsed * (self.rate / 60)
        bucket['tokens'] = min(self.burst, bucket['tokens'] + tokens_to_add)
        bucket['last_update'] = now

    def allow(self, identifier: str = 'global') -> bool:
        """
        检查是否允许请求

        Args:
            identifier: 标识符（如IP地址），用于独立限流

        Returns:
            是否允许请求
        """
        with self.lock:
            self.total_requests += 1

            bucket = self.ip_buckets[identifier]
            self._refill(bucket)

            if bucket['tokens'] >= 1:
                bucket['tokens'] -= 1
                return True
            else:
                self.blocked_requests += 1
                logger.warning(f"限流触发: {identifier}")
                return False

    def get_stats(self) -> dict:
        """获取限流统计"""
        return {
            'rate': self.rate,
            'burst': self.burst,
            'total_requests': self.total_requests,
            'blocked_requests': self.blocked_requests,
            'block_rate': round(self.blocked_requests / self.total_requests * 100, 2) if self.total_requests > 0 else 0
        }


# 全局限流器实例
rate_limiter = None


def init_rate_limiter(rate: int = 60, burst: int = 10):
    """初始化全局限流器"""
    global rate_limiter
    rate_limiter = RateLimiter(rate=rate, burst=burst)
    logger.info(f"API限流器已初始化: {rate}请求/分钟, 突发={burst}")


def rate_limit(identifier_func: Optional[Callable] = None):
    """
    API限流装饰器

    Args:
        identifier_func: 生成限流标识符的函数（默认使用IP地址）

    Example:
        @rate_limit()
        def my_api_endpoint():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if rate_limiter is None:
                return func(*args, **kwargs)

            # 获取标识符
            identifier = 'global'
            if identifier_func:
                identifier = identifier_func(*args, **kwargs)
            else:
                # 尝试从Flask request获取IP
                try:
                    from flask import request
                    identifier = request.remote_addr
                except:
                    pass

            # 检查限流
            if not rate_limiter.allow(identifier):
                from flask import jsonify
                return jsonify({
                    'success': False,
                    'error': '请求过于频繁，请稍后再试'
                }), 429

            return func(*args, **kwargs)

        return wrapper
    return decorator


# ==================== 重试机制 ====================

def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    重试装饰器

    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍增系数
        exceptions: 需要重试的异常类型

    Example:
        @retry(max_attempts=3, delay=1.0)
        def unstable_function():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay

            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} 失败 (重试{max_attempts}次后): {str(e)}")
                        raise

                    logger.warning(f"{func.__name__} 失败 (尝试 {attempt}/{max_attempts}): {str(e)}. "
                                 f"等待 {current_delay}秒后重试...")

                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1

        return wrapper
    return decorator


# ==================== 输入验证 ====================

class ValidationError(Exception):
    """验证错误"""
    pass


def validate_namespace(namespace: str) -> str:
    """
    验证namespace名称

    Args:
        namespace: namespace名称

    Returns:
        验证通过的namespace

    Raises:
        ValidationError: 验证失败
    """
    if not namespace:
        raise ValidationError("namespace不能为空")

    # Kubernetes命名规则: 小写字母、数字、连字符，以字母开头和结尾
    if not re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', namespace):
        raise ValidationError(f"namespace格式无效: {namespace}")

    if len(namespace) > 63:
        raise ValidationError(f"namespace长度不能超过63个字符: {namespace}")

    return namespace


def validate_pod_name(pod_name: str) -> str:
    """
    验证Pod名称

    Args:
        pod_name: Pod名称

    Returns:
        验证通过的Pod名称

    Raises:
        ValidationError: 验证失败
    """
    if not pod_name:
        raise ValidationError("Pod名称不能为空")

    # Kubernetes命名规则
    if not re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$', pod_name):
        raise ValidationError(f"Pod名称格式无效: {pod_name}")

    if len(pod_name) > 253:
        raise ValidationError(f"Pod名称长度不能超过253个字符: {pod_name}")

    return pod_name


def validate_file_path(file_path: str, allowed_dirs: list = None) -> str:
    """
    验证文件路径（防止路径遍历攻击）

    Args:
        file_path: 文件路径
        allowed_dirs: 允许的目录列表（默认 ['/applog']）

    Returns:
        验证通过的文件路径

    Raises:
        ValidationError: 验证失败
    """
    if not file_path:
        raise ValidationError("文件路径不能为空")

    if allowed_dirs is None:
        allowed_dirs = ['/applog']

    # 规范化路径
    normalized = file_path.replace('..', '').replace('//', '/')

    # 检查是否在允许的目录下
    if not any(normalized.startswith(allowed_dir) for allowed_dir in allowed_dirs):
        raise ValidationError(f"文件路径必须在以下目录下: {', '.join(allowed_dirs)}")

    # 检查危险字符
    dangerous_chars = ['|', ';', '&', '`', '$', '(', ')', '<', '>']
    if any(char in file_path for char in dangerous_chars):
        raise ValidationError(f"文件路径包含非法字符: {file_path}")

    return normalized


def validate_keywords(keywords: list, max_count: int = 20) -> list:
    """
    验证关键字列表

    Args:
        keywords: 关键字列表
        max_count: 最大关键字数量

    Returns:
        验证通过的关键字列表

    Raises:
        ValidationError: 验证失败
    """
    if not keywords:
        return []

    if not isinstance(keywords, list):
        raise ValidationError("关键字必须是列表类型")

    if len(keywords) > max_count:
        raise ValidationError(f"关键字数量不能超过{max_count}个")

    # 清理和验证每个关键字
    validated = []
    for keyword in keywords:
        if not isinstance(keyword, str):
            continue

        keyword = keyword.strip()
        if not keyword:
            continue

        if len(keyword) > 100:
            raise ValidationError(f"单个关键字长度不能超过100个字符: {keyword}")

        validated.append(keyword)

    return validated


def validate_tail_lines(lines: int, max_lines: int = 10000) -> int:
    """
    验证tail行数

    Args:
        lines: 请求的行数
        max_lines: 最大允许行数

    Returns:
        验证通过的行数

    Raises:
        ValidationError: 验证失败
    """
    try:
        lines = int(lines)
    except (TypeError, ValueError):
        raise ValidationError(f"行数必须是整数: {lines}")

    if lines < 1:
        raise ValidationError("行数必须大于0")

    if lines > max_lines:
        raise ValidationError(f"行数不能超过{max_lines}")

    return lines


# ==================== 性能监控 ====================

def timing(func):
    """
    性能计时装饰器

    Example:
        @timing
        def slow_function():
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.time() - start_time
            logger.info(f"{func.__name__} 执行时间: {elapsed:.3f}秒")

    return wrapper


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics = defaultdict(list)
        self.lock = Lock()

    def record(self, name: str, duration: float):
        """记录执行时间"""
        with self.lock:
            self.metrics[name].append({
                'duration': duration,
                'timestamp': datetime.now()
            })

            # 只保留最近100条记录
            if len(self.metrics[name]) > 100:
                self.metrics[name] = self.metrics[name][-100:]

    def get_stats(self, name: str = None) -> dict:
        """获取性能统计"""
        with self.lock:
            if name:
                records = self.metrics.get(name, [])
                if not records:
                    return {}

                durations = [r['duration'] for r in records]
                return {
                    'count': len(durations),
                    'avg': round(sum(durations) / len(durations), 3),
                    'min': round(min(durations), 3),
                    'max': round(max(durations), 3)
                }
            else:
                # 返回所有指标
                return {
                    metric_name: self.get_stats(metric_name)
                    for metric_name in self.metrics.keys()
                }


# 全局性能监控器
perf_monitor = PerformanceMonitor()


def monitor_performance(metric_name: str = None):
    """
    性能监控装饰器

    Args:
        metric_name: 指标名称（默认使用函数名）

    Example:
        @monitor_performance('api_query')
        def query_api():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                name = metric_name or func.__name__
                perf_monitor.record(name, duration)

        return wrapper
    return decorator


# ==================== 安全工具 ====================

def sanitize_log_output(text: str, max_length: int = 100000) -> str:
    """
    清理日志输出，防止注入攻击

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        清理后的文本
    """
    if not text:
        return ""

    # 限制长度
    if len(text) > max_length:
        text = text[:max_length] + "\n... (内容已截断)"

    # 移除控制字符（保留换行和制表符）
    text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

    return text


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)

    # 测试限流
    print("测试限流:")
    init_rate_limiter(rate=10, burst=5)
    for i in range(10):
        allowed = rate_limiter.allow('test_client')
        print(f"  请求 {i+1}: {'允许' if allowed else '拒绝'}")
    print(f"  统计: {rate_limiter.get_stats()}\n")

    # 测试重试
    print("测试重试:")

    class Counter:
        def __init__(self):
            self.count = 0

    counter = Counter()

    @retry(max_attempts=3, delay=0.1, backoff=2.0)
    def failing_function():
        counter.count += 1
        if counter.count < 3:
            raise Exception(f"失败 {counter.count}")
        return "成功"

    try:
        result = failing_function()
        print(f"  结果: {result}\n")
    except Exception as e:
        print(f"  最终失败: {e}\n")

    # 测试验证
    print("测试输入验证:")
    try:
        validate_namespace("erp-prod")
        print("  ✓ namespace验证通过: erp-prod")
    except ValidationError as e:
        print(f"  ✗ namespace验证失败: {e}")

    try:
        validate_file_path("/applog/../../etc/passwd")
        print("  ✗ 文件路径验证应该失败但通过了")
    except ValidationError as e:
        print(f"  ✓ 文件路径验证正确拒绝: {e}")

    print("\n性能监控:")
    @monitor_performance('test_operation')
    def test_operation():
        time.sleep(0.05)

    for _ in range(5):
        test_operation()

    print(f"  统计: {perf_monitor.get_stats('test_operation')}")
