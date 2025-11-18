"""
性能监控模块
提供请求追踪、性能指标收集、慢查询检测
"""

import time
import functools
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from threading import Lock
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """请求指标"""
    endpoint: str
    method: str
    start_time: float
    end_time: float = 0.0
    duration: float = 0.0
    status_code: int = 0
    error: Optional[str] = None
    request_size: int = 0
    response_size: int = 0
    user_agent: str = ""
    remote_addr: str = ""

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'endpoint': self.endpoint,
            'method': self.method,
            'duration_ms': f"{self.duration * 1000:.2f}",
            'status_code': self.status_code,
            'error': self.error,
            'timestamp': datetime.fromtimestamp(self.start_time).isoformat(),
            'request_size': self.request_size,
            'response_size': self.response_size,
            'remote_addr': self.remote_addr
        }


@dataclass
class PerformanceStats:
    """性能统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    slow_requests: int = 0  # 慢请求数（>1秒）

    @property
    def avg_duration(self) -> float:
        """平均响应时间"""
        return self.total_duration / max(self.total_requests, 1)

    @property
    def success_rate(self) -> float:
        """成功率"""
        return (self.successful_requests / max(self.total_requests, 1)) * 100

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': f"{self.success_rate:.2f}%",
            'avg_duration_ms': f"{self.avg_duration * 1000:.2f}",
            'min_duration_ms': f"{self.min_duration * 1000:.2f}" if self.min_duration != float('inf') else "N/A",
            'max_duration_ms': f"{self.max_duration * 1000:.2f}",
            'slow_requests': self.slow_requests
        }


class PerformanceMonitor:
    """
    性能监控器
    - 追踪所有请求
    - 收集性能指标
    - 检测慢查询
    - 提供统计报告
    """

    def __init__(self, max_history: int = 1000, slow_threshold: float = 1.0):
        """
        初始化性能监控器

        Args:
            max_history: 最大历史记录数
            slow_threshold: 慢请求阈值（秒）
        """
        self.max_history = max_history
        self.slow_threshold = slow_threshold
        self._history = deque(maxlen=max_history)
        self._endpoint_stats = {}  # {endpoint: PerformanceStats}
        self._lock = Lock()
        self._start_time = datetime.now()

    def record_request(self, metrics: RequestMetrics):
        """记录请求指标"""
        with self._lock:
            # 添加到历史记录
            self._history.append(metrics)

            # 更新端点统计
            endpoint = f"{metrics.method} {metrics.endpoint}"
            if endpoint not in self._endpoint_stats:
                self._endpoint_stats[endpoint] = PerformanceStats()

            stats = self._endpoint_stats[endpoint]
            stats.total_requests += 1
            stats.total_duration += metrics.duration

            if metrics.duration < stats.min_duration:
                stats.min_duration = metrics.duration
            if metrics.duration > stats.max_duration:
                stats.max_duration = metrics.duration

            if metrics.error:
                stats.failed_requests += 1
            else:
                stats.successful_requests += 1

            if metrics.duration > self.slow_threshold:
                stats.slow_requests += 1
                logger.warning(
                    f"慢请求检测: {endpoint} - {metrics.duration * 1000:.2f}ms "
                    f"(来自 {metrics.remote_addr})"
                )

    def get_recent_requests(self, limit: int = 100) -> List[Dict]:
        """获取最近的请求记录"""
        with self._lock:
            recent = list(self._history)[-limit:]
            return [m.to_dict() for m in recent]

    def get_slow_requests(self, limit: int = 50) -> List[Dict]:
        """获取慢请求"""
        with self._lock:
            slow = [
                m for m in self._history
                if m.duration > self.slow_threshold
            ]
            slow.sort(key=lambda x: x.duration, reverse=True)
            return [m.to_dict() for m in slow[:limit]]

    def get_endpoint_stats(self) -> Dict[str, Dict]:
        """获取各端点的统计信息"""
        with self._lock:
            return {
                endpoint: stats.to_dict()
                for endpoint, stats in self._endpoint_stats.items()
            }

    def get_top_endpoints(self, by: str = 'requests', limit: int = 10) -> List[Dict]:
        """
        获取Top端点

        Args:
            by: 排序依据 ('requests', 'duration', 'errors')
            limit: 返回数量
        """
        with self._lock:
            items = list(self._endpoint_stats.items())

            if by == 'requests':
                items.sort(key=lambda x: x[1].total_requests, reverse=True)
            elif by == 'duration':
                items.sort(key=lambda x: x[1].avg_duration, reverse=True)
            elif by == 'errors':
                items.sort(key=lambda x: x[1].failed_requests, reverse=True)

            return [
                {'endpoint': endpoint, **stats.to_dict()}
                for endpoint, stats in items[:limit]
            ]

    def get_overall_stats(self) -> Dict:
        """获取总体统计"""
        with self._lock:
            total_requests = sum(s.total_requests for s in self._endpoint_stats.values())
            total_successful = sum(s.successful_requests for s in self._endpoint_stats.values())
            total_failed = sum(s.failed_requests for s in self._endpoint_stats.values())
            total_duration = sum(s.total_duration for s in self._endpoint_stats.values())
            total_slow = sum(s.slow_requests for s in self._endpoint_stats.values())

            uptime = (datetime.now() - self._start_time).total_seconds()

            return {
                'uptime_seconds': int(uptime),
                'uptime_hours': f"{uptime / 3600:.2f}",
                'total_requests': total_requests,
                'successful_requests': total_successful,
                'failed_requests': total_failed,
                'success_rate': f"{(total_successful / max(total_requests, 1)) * 100:.2f}%",
                'avg_duration_ms': f"{(total_duration / max(total_requests, 1)) * 1000:.2f}",
                'slow_requests': total_slow,
                'slow_request_rate': f"{(total_slow / max(total_requests, 1)) * 100:.2f}%",
                'requests_per_second': f"{total_requests / max(uptime, 1):.2f}",
                'total_endpoints': len(self._endpoint_stats),
                'history_size': len(self._history),
                'start_time': self._start_time.isoformat()
            }

    def export_report(self) -> str:
        """导出完整性能报告"""
        report = {
            'overall': self.get_overall_stats(),
            'top_endpoints_by_requests': self.get_top_endpoints('requests', 10),
            'top_endpoints_by_duration': self.get_top_endpoints('duration', 10),
            'top_endpoints_by_errors': self.get_top_endpoints('errors', 10),
            'recent_slow_requests': self.get_slow_requests(20),
            'all_endpoint_stats': self.get_endpoint_stats()
        }
        return json.dumps(report, indent=2, ensure_ascii=False)

    def reset_stats(self):
        """重置统计数据"""
        with self._lock:
            self._endpoint_stats.clear()
            self._history.clear()
            self._start_time = datetime.now()
            logger.info("性能统计已重置")


# 全局性能监控器
performance_monitor = PerformanceMonitor(max_history=2000, slow_threshold=1.0)


def monitor_performance(f):
    """
    性能监控装饰器

    Example:
        @monitor_performance
        def my_api_endpoint():
            ...
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, g

        # 记录开始时间
        start_time = time.time()
        metrics = RequestMetrics(
            endpoint=request.endpoint or request.path,
            method=request.method,
            start_time=start_time,
            remote_addr=request.remote_addr or 'unknown',
            user_agent=request.user_agent.string if request.user_agent else '',
            request_size=request.content_length or 0
        )

        try:
            # 执行函数
            response = f(*args, **kwargs)

            # 记录响应
            if hasattr(response, 'status_code'):
                metrics.status_code = response.status_code
            else:
                # 如果是tuple (data, status_code)
                if isinstance(response, tuple) and len(response) >= 2:
                    metrics.status_code = response[1]
                else:
                    metrics.status_code = 200

            # 记录响应大小
            if hasattr(response, 'data'):
                metrics.response_size = len(response.data)

            return response

        except Exception as e:
            # 记录错误
            metrics.error = str(e)
            metrics.status_code = 500
            raise

        finally:
            # 记录结束时间和持续时间
            metrics.end_time = time.time()
            metrics.duration = metrics.end_time - metrics.start_time

            # 记录到监控器
            performance_monitor.record_request(metrics)

    return decorated_function


class PerformanceTimer:
    """
    性能计时器（上下文管理器）

    Example:
        with PerformanceTimer("database_query") as timer:
            # 执行数据库查询
            ...
        print(f"查询耗时: {timer.duration}秒")
    """

    def __init__(self, name: str, log_threshold: Optional[float] = None):
        """
        Args:
            name: 计时器名称
            log_threshold: 日志阈值（秒），超过此时间会记录日志
        """
        self.name = name
        self.log_threshold = log_threshold
        self.start_time = None
        self.end_time = None
        self.duration = None

    def __enter__(self):
        """开始计时"""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """结束计时"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time

        if self.log_threshold and self.duration > self.log_threshold:
            logger.warning(f"{self.name} 耗时过长: {self.duration * 1000:.2f}ms")
        else:
            logger.debug(f"{self.name} 耗时: {self.duration * 1000:.2f}ms")


def timed(log_threshold: Optional[float] = None):
    """
    函数计时装饰器

    Args:
        log_threshold: 日志阈值（秒）

    Example:
        @timed(log_threshold=0.5)
        def slow_function():
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            with PerformanceTimer(f.__name__, log_threshold):
                return f(*args, **kwargs)
        return decorated_function
    return decorator


if __name__ == '__main__':
    # 测试性能监控
    logging.basicConfig(level=logging.INFO)

    print("=== 性能监控测试 ===\n")

    # 模拟一些请求
    for i in range(10):
        metrics = RequestMetrics(
            endpoint="/api/test",
            method="GET",
            start_time=time.time(),
            remote_addr=f"192.168.1.{i}"
        )
        time.sleep(0.01 * (i + 1))  # 模拟不同的响应时间
        metrics.end_time = time.time()
        metrics.duration = metrics.end_time - metrics.start_time
        metrics.status_code = 200 if i % 5 != 0 else 500
        if metrics.status_code == 500:
            metrics.error = "Internal Server Error"

        performance_monitor.record_request(metrics)

    # 显示统计
    print("总体统计:")
    print(json.dumps(performance_monitor.get_overall_stats(), indent=2, ensure_ascii=False))

    print("\n端点统计:")
    print(json.dumps(performance_monitor.get_endpoint_stats(), indent=2, ensure_ascii=False))

    # 测试计时器
    print("\n=== 计时器测试 ===")
    with PerformanceTimer("test_operation", log_threshold=0.05) as timer:
        time.sleep(0.1)
    print(f"操作耗时: {timer.duration * 1000:.2f}ms")

    # 测试装饰器
    @timed(log_threshold=0.05)
    def test_function():
        time.sleep(0.1)
        return "完成"

    print("\n装饰器测试:")
    result = test_function()
    print(f"结果: {result}")
