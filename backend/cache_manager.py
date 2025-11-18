"""
缓存管理器 - 提供多级本地内存缓存
支持TTL（Time To Live）和LRU（Least Recently Used）策略
"""

import time
import threading
from typing import Any, Optional, Callable, OrderedDict
from functools import wraps
from collections import OrderedDict as ODict
import logging

logger = logging.getLogger(__name__)


class LRUTTLCache:
    """结合LRU和TTL的高级缓存"""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000, use_lru: bool = True):
        """
        初始化缓存

        Args:
            ttl_seconds: 缓存过期时间（秒）
            max_size: 最大缓存条目数
            use_lru: 是否使用LRU策略（默认True）
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self.use_lru = use_lru

        # 使用OrderedDict实现LRU
        self._cache = ODict()  # {key: (value, expire_time, access_count)}
        self._lock = threading.RLock()

        # 统计信息
        self._stats = {
            'hits': 0,
            'misses': 0,
            'expired': 0,
            'evictions': 0,
            'sets': 0
        }

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                self._stats['misses'] += 1
                return None

            value, expire_time, access_count = self._cache[key]

            # 检查是否过期
            current_time = time.time()
            if current_time > expire_time:
                del self._cache[key]
                self._stats['expired'] += 1
                self._stats['misses'] += 1
                logger.debug(f"缓存过期: {key}")
                return None

            # 更新访问计数和顺序（LRU）
            self._stats['hits'] += 1
            if self.use_lru:
                # 移到末尾（最近使用）
                self._cache.move_to_end(key)
                self._cache[key] = (value, expire_time, access_count + 1)

            logger.debug(f"缓存命中: {key} (访问次数: {access_count + 1})")
            return value

    def set(self, key: str, value: Any):
        """设置缓存值"""
        with self._lock:
            current_time = time.time()
            self._stats['sets'] += 1

            # 如果超过最大大小，根据策略淘汰
            if key not in self._cache and len(self._cache) >= self.max_size:
                self._evict()

            expire_time = current_time + self.ttl

            # 如果key已存在，保留访问计数
            if key in self._cache:
                _, _, access_count = self._cache[key]
                self._cache[key] = (value, expire_time, access_count)
            else:
                self._cache[key] = (value, expire_time, 0)

            # LRU: 移到末尾
            if self.use_lru:
                self._cache.move_to_end(key)

            logger.debug(f"缓存设置: {key}, TTL={self.ttl}s")

    def _evict(self):
        """淘汰缓存条目"""
        with self._lock:
            if not self._cache:
                return

            if self.use_lru:
                # LRU: 删除最早的（最少使用的）
                evicted_key = next(iter(self._cache))
                del self._cache[evicted_key]
                logger.debug(f"缓存LRU淘汰: {evicted_key}")
            else:
                # TTL: 删除最早过期的
                oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
                del self._cache[oldest_key]
                logger.debug(f"缓存TTL淘汰: {oldest_key}")

            self._stats['evictions'] += 1

    def delete(self, key: str):
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"缓存删除: {key}")

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"缓存已清空 ({count} 项)")

    def cleanup_expired(self):
        """清理过期缓存"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, expire_time, _) in self._cache.items()
                if current_time > expire_time
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                self._stats['expired'] += len(expired_keys)
                logger.info(f"清理了 {len(expired_keys)} 个过期缓存")

            return len(expired_keys)

    def stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'strategy': 'LRU+TTL' if self.use_lru else 'TTL',
                'hit_rate': round(hit_rate, 2),
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'expired': self._stats['expired'],
                'evictions': self._stats['evictions'],
                'sets': self._stats['sets']
            }

    def reset_stats(self):
        """重置统计信息"""
        with self._lock:
            self._stats = {
                'hits': 0,
                'misses': 0,
                'expired': 0,
                'evictions': 0,
                'sets': 0
            }
            logger.info("缓存统计已重置")


# 向后兼容：TTLCache别名
TTLCache = LRUTTLCache


class CacheManager:
    """统一缓存管理器 - 管理多个缓存实例"""

    def __init__(self, cache_config=None):
        """
        初始化缓存管理器

        Args:
            cache_config: 缓存配置对象（如果为None，将尝试导入默认配置）
        """
        # 延迟导入配置，避免循环依赖
        if cache_config is None:
            try:
                from config import config
                cache_config = config.cache
            except ImportError:
                # 如果配置模块不存在，使用默认值
                logger.warning("配置模块不存在，使用默认缓存配置")
                cache_config = type('CacheConfig', (), {
                    'namespaces_ttl': 60,
                    'namespaces_max_size': 100,
                    'deployments_ttl': 30,
                    'deployments_max_size': 500,
                    'pods_ttl': 10,
                    'pods_max_size': 1000,
                    'logs_ttl': 5,
                    'logs_max_size': 200,
                    'cleanup_interval': 30,
                    'use_lru': True
                })()

        # 创建各种缓存实例
        self.namespaces_cache = LRUTTLCache(
            ttl_seconds=cache_config.namespaces_ttl,
            max_size=cache_config.namespaces_max_size,
            use_lru=cache_config.use_lru
        )

        self.deployments_cache = LRUTTLCache(
            ttl_seconds=cache_config.deployments_ttl,
            max_size=cache_config.deployments_max_size,
            use_lru=cache_config.use_lru
        )

        self.pods_cache = LRUTTLCache(
            ttl_seconds=cache_config.pods_ttl,
            max_size=cache_config.pods_max_size,
            use_lru=cache_config.use_lru
        )

        self.logs_cache = LRUTTLCache(
            ttl_seconds=cache_config.logs_ttl,
            max_size=cache_config.logs_max_size,
            use_lru=cache_config.use_lru
        )

        self.cleanup_interval = cache_config.cleanup_interval
        self._running = True

        # 启动后台清理线程
        self._start_cleanup_thread()

        logger.info(f"缓存管理器初始化完成 (策略: {'LRU+TTL' if cache_config.use_lru else 'TTL'})")

    def _start_cleanup_thread(self):
        """启动后台清理过期缓存的线程"""
        def cleanup_loop():
            while self._running:
                time.sleep(self.cleanup_interval)
                try:
                    total_cleaned = 0
                    total_cleaned += self.namespaces_cache.cleanup_expired()
                    total_cleaned += self.deployments_cache.cleanup_expired()
                    total_cleaned += self.pods_cache.cleanup_expired()
                    total_cleaned += self.logs_cache.cleanup_expired()

                    if total_cleaned > 0:
                        logger.info(f"后台清理: 总共清理了 {total_cleaned} 个过期缓存")
                except Exception as e:
                    logger.error(f"清理缓存异常: {e}", exc_info=True)

        thread = threading.Thread(target=cleanup_loop, daemon=True, name="CacheCleanup")
        thread.start()
        logger.info(f"缓存清理线程已启动 (间隔: {self.cleanup_interval}秒)")

    def clear_all(self):
        """清空所有缓存"""
        self.namespaces_cache.clear()
        self.deployments_cache.clear()
        self.pods_cache.clear()
        self.logs_cache.clear()
        logger.info("所有缓存已清空")

    def reset_all_stats(self):
        """重置所有缓存统计"""
        self.namespaces_cache.reset_stats()
        self.deployments_cache.reset_stats()
        self.pods_cache.reset_stats()
        self.logs_cache.reset_stats()
        logger.info("所有缓存统计已重置")

    def get_stats(self) -> dict:
        """获取所有缓存统计信息"""
        stats = {
            'namespaces': self.namespaces_cache.stats(),
            'deployments': self.deployments_cache.stats(),
            'pods': self.pods_cache.stats(),
            'logs': self.logs_cache.stats()
        }

        # 计算总体统计
        total_size = sum(s['size'] for s in stats.values())
        total_max_size = sum(s['max_size'] for s in stats.values())
        total_hits = sum(s['hits'] for s in stats.values())
        total_misses = sum(s['misses'] for s in stats.values())

        stats['total'] = {
            'size': total_size,
            'max_size': total_max_size,
            'usage_percent': round(total_size / total_max_size * 100, 2) if total_max_size > 0 else 0,
            'hits': total_hits,
            'misses': total_misses,
            'overall_hit_rate': round(total_hits / (total_hits + total_misses) * 100, 2) if (total_hits + total_misses) > 0 else 0
        }

        return stats

    def shutdown(self):
        """优雅关闭缓存管理器"""
        logger.info("正在关闭缓存管理器...")
        self._running = False
        self.clear_all()
        logger.info("缓存管理器已关闭")


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
