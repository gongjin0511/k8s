"""
缓存管理器 - 提供多级本地内存缓存
使用TTL（Time To Live）策略，自动过期
"""

import time
import threading
from typing import Any, Optional, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """带过期时间的缓存"""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        """
        初始化缓存

        Args:
            ttl_seconds: 缓存过期时间（秒）
            max_size: 最大缓存条目数
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache = {}  # {key: (value, expire_time)}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                return None

            value, expire_time = self._cache[key]

            # 检查是否过期
            if time.time() > expire_time:
                del self._cache[key]
                logger.debug(f"缓存过期: {key}")
                return None

            logger.debug(f"缓存命中: {key}")
            return value

    def set(self, key: str, value: Any):
        """设置缓存值"""
        with self._lock:
            # 如果超过最大大小，删除最旧的条目
            if len(self._cache) >= self.max_size:
                # 删除最早过期的条目
                oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
                del self._cache[oldest_key]
                logger.debug(f"缓存已满，删除最旧条目: {oldest_key}")

            expire_time = time.time() + self.ttl
            self._cache[key] = (value, expire_time)
            logger.debug(f"缓存设置: {key}, TTL={self.ttl}s")

    def delete(self, key: str):
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"缓存删除: {key}")

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            logger.info("缓存已清空")

    def cleanup_expired(self):
        """清理过期缓存"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, expire_time) in self._cache.items()
                if current_time > expire_time
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.info(f"清理了 {len(expired_keys)} 个过期缓存")

    def stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl
            }


class CacheManager:
    """统一缓存管理器 - 管理多个缓存实例"""

    def __init__(self):
        # 不同数据类型使用不同的TTL
        self.namespaces_cache = TTLCache(ttl_seconds=60, max_size=100)      # Namespace列表，60秒
        self.deployments_cache = TTLCache(ttl_seconds=30, max_size=500)     # Deployment列表，30秒
        self.pods_cache = TTLCache(ttl_seconds=10, max_size=1000)           # Pod列表，10秒（变化较快）
        self.logs_cache = TTLCache(ttl_seconds=5, max_size=200)             # 日志缓存，5秒（仅用于频繁查询）

        # 启动后台清理线程
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """启动后台清理过期缓存的线程"""
        def cleanup_loop():
            while True:
                time.sleep(30)  # 每30秒清理一次
                try:
                    self.namespaces_cache.cleanup_expired()
                    self.deployments_cache.cleanup_expired()
                    self.pods_cache.cleanup_expired()
                    self.logs_cache.cleanup_expired()
                except Exception as e:
                    logger.error(f"清理缓存异常: {e}", exc_info=True)

        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        logger.info("缓存清理线程已启动")

    def clear_all(self):
        """清空所有缓存"""
        self.namespaces_cache.clear()
        self.deployments_cache.clear()
        self.pods_cache.clear()
        self.logs_cache.clear()
        logger.info("所有缓存已清空")

    def get_stats(self) -> dict:
        """获取所有缓存统计信息"""
        return {
            'namespaces': self.namespaces_cache.stats(),
            'deployments': self.deployments_cache.stats(),
            'pods': self.pods_cache.stats(),
            'logs': self.logs_cache.stats()
        }


# 全局缓存管理器实例
cache_manager = CacheManager()


def cached(cache_type: str, key_func: Optional[Callable] = None, ttl: Optional[int] = None):
    """
    缓存装饰器

    Args:
        cache_type: 缓存类型 ('namespaces', 'deployments', 'pods', 'logs')
        key_func: 生成缓存键的函数，默认使用函数名和参数
        ttl: 自定义TTL（秒），覆盖默认值

    Example:
        @cached('namespaces', key_func=lambda pattern: f"ns:{pattern}")
        def get_namespaces(pattern):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 选择缓存实例
            cache_map = {
                'namespaces': cache_manager.namespaces_cache,
                'deployments': cache_manager.deployments_cache,
                'pods': cache_manager.pods_cache,
                'logs': cache_manager.logs_cache
            }

            cache = cache_map.get(cache_type)
            if not cache:
                raise ValueError(f"无效的缓存类型: {cache_type}")

            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数作为键
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 缓存未命中，执行函数
            result = func(*args, **kwargs)

            # 存入缓存
            if ttl:
                # 临时修改TTL
                old_ttl = cache.ttl
                cache.ttl = ttl
                cache.set(cache_key, result)
                cache.ttl = old_ttl
            else:
                cache.set(cache_key, result)

            return result

        return wrapper
    return decorator


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)

    @cached('namespaces', key_func=lambda pattern='': f"ns:{pattern}")
    def get_test_namespaces(pattern=''):
        print(f"执行函数: get_test_namespaces({pattern})")
        return ['ns1', 'ns2', 'ns3']

    # 第一次调用，缓存未命中
    print("第一次调用:")
    result1 = get_test_namespaces('test')
    print(f"结果: {result1}\n")

    # 第二次调用，缓存命中
    print("第二次调用（应该命中缓存）:")
    result2 = get_test_namespaces('test')
    print(f"结果: {result2}\n")

    # 查看统计信息
    print("缓存统计:")
    print(cache_manager.get_stats())
