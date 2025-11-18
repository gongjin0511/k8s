"""
增强型缓存管理器 - 提供多级LRU缓存和智能过期策略
支持性能监控、并发控制和自动清理
"""

import time
import threading
from typing import Any, Optional, Dict, Callable
from functools import wraps
from collections import OrderedDict
import logging
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expired: int = 0
    total_get_time: float = 0.0
    total_set_time: float = 0.0

    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'expired': self.expired,
            'hit_rate': f"{self.hit_rate:.2f}%",
            'avg_get_time_ms': f"{(self.total_get_time / max(self.hits + self.misses, 1)) * 1000:.2f}",
            'avg_set_time_ms': f"{(self.total_set_time / max(self.hits, 1)) * 1000:.2f}"
        }


class LRUCache:
    """
    LRU缓存实现（带TTL）
    - 自动淘汰最少使用的条目
    - 支持TTL过期
    - 线程安全
    - 性能监控
    """

    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000, name: str = "cache"):
        """
        初始化LRU缓存

        Args:
            ttl_seconds: 缓存过期时间（秒）
            max_size: 最大缓存条目数
            name: 缓存名称
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self.name = name
        self._cache = OrderedDict()  # {key: (value, expire_time, access_count)}
        self._lock = threading.RLock()
        self._stats = CacheStats()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值（LRU策略）"""
        start_time = time.time()

        with self._lock:
            if key not in self._cache:
                self._stats.misses += 1
                self._stats.total_get_time += time.time() - start_time
                logger.debug(f"[{self.name}] 缓存未命中: {key}")
                return None

            value, expire_time, access_count = self._cache[key]

            # 检查是否过期
            if time.time() > expire_time:
                del self._cache[key]
                self._stats.misses += 1
                self._stats.expired += 1
                self._stats.total_get_time += time.time() - start_time
                logger.debug(f"[{self.name}] 缓存过期: {key}")
                return None

            # LRU: 移动到末尾
            self._cache.move_to_end(key)
            # 更新访问次数
            self._cache[key] = (value, expire_time, access_count + 1)

            self._stats.hits += 1
            self._stats.total_get_time += time.time() - start_time
            logger.debug(f"[{self.name}] 缓存命中: {key} (访问次数: {access_count + 1})")
            return value

    def set(self, key: str, value: Any):
        """设置缓存值（LRU淘汰）"""
        start_time = time.time()

        with self._lock:
            # 如果超过最大大小，删除最少使用的条目（第一个）
            if len(self._cache) >= self.max_size and key not in self._cache:
                evicted_key, _ = self._cache.popitem(last=False)
                self._stats.evictions += 1
                logger.debug(f"[{self.name}] 缓存满，淘汰最少使用: {evicted_key}")

            expire_time = time.time() + self.ttl
            self._cache[key] = (value, expire_time, 1)  # value, expire_time, access_count

            # 移动到末尾（最近使用）
            self._cache.move_to_end(key)

            self._stats.total_set_time += time.time() - start_time
            logger.debug(f"[{self.name}] 缓存设置: {key}, TTL={self.ttl}s")

    def delete(self, key: str):
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"[{self.name}] 缓存删除: {key}")

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"[{self.name}] 缓存已清空 ({count} 条目)")

    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, expire_time, _) in self._cache.items()
                if current_time > expire_time
            ]

            for key in expired_keys:
                del self._cache[key]
                self._stats.expired += 1

            if expired_keys:
                logger.info(f"[{self.name}] 清理了 {len(expired_keys)} 个过期缓存")

            return len(expired_keys)

    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self._lock:
            stats_dict = self._stats.to_dict()
            stats_dict.update({
                'name': self.name,
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'usage': f"{(len(self._cache) / self.max_size) * 100:.1f}%"
            })
            return stats_dict

    def get_keys(self) -> list:
        """获取所有缓存键"""
        with self._lock:
            return list(self._cache.keys())

    def get_hot_keys(self, top_n: int = 10) -> list:
        """获取访问最频繁的键"""
        with self._lock:
            items = [(k, access_count) for k, (_, _, access_count) in self._cache.items()]
            sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
            return sorted_items[:top_n]


class CacheManager:
    """
    统一缓存管理器 - 管理多个LRU缓存实例
    提供性能监控、自动清理和预热功能
    """

    def __init__(self):
        # 不同数据类型使用不同的TTL和大小
        self.namespaces_cache = LRUCache(
            ttl_seconds=120,  # 增加到2分钟
            max_size=200,     # 增加容量
            name="namespaces"
        )

        self.deployments_cache = LRUCache(
            ttl_seconds=60,   # 1分钟
            max_size=1000,    # 更大容量
            name="deployments"
        )

        self.pods_cache = LRUCache(
            ttl_seconds=30,   # 30秒（变化较快）
            max_size=2000,    # 大容量
            name="pods"
        )

        self.logs_cache = LRUCache(
            ttl_seconds=10,   # 10秒（日志更新快）
            max_size=500,     # 中等容量
            name="logs"
        )

        self.files_cache = LRUCache(
            ttl_seconds=300,  # 5分钟（文件列表相对稳定）
            max_size=1000,
            name="files"
        )

        # 全局统计
        self._global_stats = {
            'start_time': datetime.now(),
            'cleanup_runs': 0,
            'total_cleaned': 0
        }

        # 启动后台清理线程
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """启动后台清理过期缓存的线程"""
        def cleanup_loop():
            while True:
                time.sleep(30)  # 每30秒清理一次
                try:
                    total_cleaned = 0
                    total_cleaned += self.namespaces_cache.cleanup_expired()
                    total_cleaned += self.deployments_cache.cleanup_expired()
                    total_cleaned += self.pods_cache.cleanup_expired()
                    total_cleaned += self.logs_cache.cleanup_expired()
                    total_cleaned += self.files_cache.cleanup_expired()

                    self._global_stats['cleanup_runs'] += 1
                    self._global_stats['total_cleaned'] += total_cleaned

                    if total_cleaned > 0:
                        logger.info(f"缓存清理完成: 清理了 {total_cleaned} 个过期条目")
                except Exception as e:
                    logger.error(f"清理缓存异常: {e}", exc_info=True)

        thread = threading.Thread(target=cleanup_loop, daemon=True, name="CacheCleanup")
        thread.start()
        logger.info("缓存清理线程已启动")

    def clear_all(self):
        """清空所有缓存"""
        self.namespaces_cache.clear()
        self.deployments_cache.clear()
        self.pods_cache.clear()
        self.logs_cache.clear()
        self.files_cache.clear()
        logger.info("所有缓存已清空")

    def get_stats(self) -> Dict:
        """获取所有缓存统计信息"""
        uptime = (datetime.now() - self._global_stats['start_time']).total_seconds()

        return {
            'caches': {
                'namespaces': self.namespaces_cache.get_stats(),
                'deployments': self.deployments_cache.get_stats(),
                'pods': self.pods_cache.get_stats(),
                'logs': self.logs_cache.get_stats(),
                'files': self.files_cache.get_stats()
            },
            'global': {
                'uptime_seconds': int(uptime),
                'uptime_hours': f"{uptime / 3600:.2f}",
                'cleanup_runs': self._global_stats['cleanup_runs'],
                'total_cleaned': self._global_stats['total_cleaned'],
                'start_time': self._global_stats['start_time'].isoformat()
            }
        }

    def get_hot_keys(self) -> Dict:
        """获取所有缓存的热键"""
        return {
            'namespaces': self.namespaces_cache.get_hot_keys(10),
            'deployments': self.deployments_cache.get_hot_keys(10),
            'pods': self.pods_cache.get_hot_keys(10),
            'logs': self.logs_cache.get_hot_keys(10),
            'files': self.files_cache.get_hot_keys(10)
        }

    def export_stats(self) -> str:
        """导出统计信息为JSON"""
        stats = self.get_stats()
        stats['hot_keys'] = self.get_hot_keys()
        return json.dumps(stats, indent=2, ensure_ascii=False)

    def warmup(self, warmup_func: Callable):
        """
        预热缓存

        Args:
            warmup_func: 预热函数，应该执行一些常用的查询
        """
        logger.info("开始缓存预热...")
        try:
            warmup_func()
            logger.info("缓存预热完成")
        except Exception as e:
            logger.error(f"缓存预热失败: {e}", exc_info=True)


# 全局缓存管理器实例
cache_manager = CacheManager()


def cached(cache_type: str, key_func: Optional[Callable] = None, ttl: Optional[int] = None):
    """
    缓存装饰器（增强版）

    Args:
        cache_type: 缓存类型 ('namespaces', 'deployments', 'pods', 'logs', 'files')
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
                'logs': cache_manager.logs_cache,
                'files': cache_manager.files_cache
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
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=== LRU缓存测试 ===\n")

    # 创建小容量缓存测试LRU
    test_cache = LRUCache(ttl_seconds=10, max_size=3, name="test")

    # 添加数据
    print("添加数据...")
    test_cache.set("key1", "value1")
    test_cache.set("key2", "value2")
    test_cache.set("key3", "value3")

    # 访问key1（变成最近使用）
    print(f"访问 key1: {test_cache.get('key1')}")

    # 添加key4（应该淘汰key2）
    print("添加 key4...")
    test_cache.set("key4", "value4")

    # 验证key2被淘汰
    print(f"访问 key2: {test_cache.get('key2')}")  # None

    # 显示统计
    print("\n缓存统计:")
    print(json.dumps(test_cache.get_stats(), indent=2, ensure_ascii=False))

    # 热键测试
    print("\n热键:")
    print(test_cache.get_hot_keys())

    # 全局缓存管理器测试
    print("\n=== 全局缓存管理器测试 ===\n")
    print(cache_manager.export_stats())
