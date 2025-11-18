"""
配置管理模块
集中管理所有配置项，支持环境变量覆盖
"""

import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class CacheConfig:
    """缓存配置"""
    # Namespaces缓存
    namespaces_ttl: int = 120  # 秒
    namespaces_max_size: int = 200

    # Deployments缓存
    deployments_ttl: int = 60
    deployments_max_size: int = 1000

    # Pods缓存
    pods_ttl: int = 30
    pods_max_size: int = 2000

    # Logs缓存
    logs_ttl: int = 10
    logs_max_size: int = 500

    # Files缓存
    files_ttl: int = 300
    files_max_size: int = 1000

    # 清理间隔
    cleanup_interval: int = 30  # 秒


@dataclass
class RateLimitConfig:
    """限流配置"""
    # API限流
    api_capacity: int = 100
    api_refill_rate: float = 10.0  # 令牌/秒

    # 登录限流
    login_capacity: int = 10
    login_refill_rate: float = 5.0 / 60.0  # 5次/分钟

    # 清理间隔
    cleanup_interval: int = 3600  # 秒


@dataclass
class PerformanceConfig:
    """性能配置"""
    # 历史记录保留数量
    max_history: int = 2000

    # 慢请求阈值
    slow_threshold: float = 1.0  # 秒

    # 监控开关
    enable_monitoring: bool = True


@dataclass
class KubectlConfig:
    """Kubectl配置"""
    # 超时时间
    timeout: int = 300  # 秒

    # 最大并发数
    max_workers: int = 10

    # 重试次数
    max_retries: int = 3

    # 缓存大小
    lru_cache_size: int = 128


@dataclass
class SecurityConfig:
    """安全配置"""
    # 密码
    login_password: str = field(default_factory=lambda: os.getenv('LOGIN_PASSWORD', 'Cnnc@2025'))

    # Session密钥
    secret_key: str = field(default_factory=lambda: os.getenv('SECRET_KEY', 'k8s-log-viewer-secret-key-2025'))

    # Session配置
    session_permanent: bool = True
    session_lifetime: int = 7200  # 2小时

    # CSRF配置
    csrf_enabled: bool = True
    csrf_token_length: int = 32

    # 安全响应头
    enable_security_headers: bool = True


@dataclass
class DatabaseConfig:
    """数据库配置"""
    db_path: str = 'k8s_logs.db'

    # 连接池配置
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30

    # 性能配置
    enable_wal: bool = True  # Write-Ahead Logging
    cache_size: int = 10000  # 页面缓存


@dataclass
class ApplicationConfig:
    """应用配置"""
    # Flask配置
    host: str = '0.0.0.0'
    port: int = 5000
    debug: bool = os.getenv('DEBUG', 'False').lower() == 'true'

    # 日志配置
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    log_file: Optional[str] = os.getenv('LOG_FILE')

    # 日志目录
    logs_dir: str = os.path.join(os.path.dirname(__file__), '..', 'logs')

    # 限制配置
    max_tail_lines: int = 10000
    max_batch_pods: int = 100
    max_download_size: int = 100 * 1024 * 1024  # 100MB


class Config:
    """统一配置类"""

    def __init__(self):
        self.cache = CacheConfig()
        self.rate_limit = RateLimitConfig()
        self.performance = PerformanceConfig()
        self.kubectl = KubectlConfig()
        self.security = SecurityConfig()
        self.database = DatabaseConfig()
        self.application = ApplicationConfig()

    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        config = cls()

        # 覆盖缓存配置
        if os.getenv('CACHE_NAMESPACES_TTL'):
            config.cache.namespaces_ttl = int(os.getenv('CACHE_NAMESPACES_TTL'))
        if os.getenv('CACHE_PODS_TTL'):
            config.cache.pods_ttl = int(os.getenv('CACHE_PODS_TTL'))

        # 覆盖限流配置
        if os.getenv('RATE_LIMIT_API_CAPACITY'):
            config.rate_limit.api_capacity = int(os.getenv('RATE_LIMIT_API_CAPACITY'))
        if os.getenv('RATE_LIMIT_API_REFILL_RATE'):
            config.rate_limit.api_refill_rate = float(os.getenv('RATE_LIMIT_API_REFILL_RATE'))

        # 覆盖性能配置
        if os.getenv('SLOW_THRESHOLD'):
            config.performance.slow_threshold = float(os.getenv('SLOW_THRESHOLD'))

        # 覆盖kubectl配置
        if os.getenv('KUBECTL_TIMEOUT'):
            config.kubectl.timeout = int(os.getenv('KUBECTL_TIMEOUT'))
        if os.getenv('KUBECTL_MAX_WORKERS'):
            config.kubectl.max_workers = int(os.getenv('KUBECTL_MAX_WORKERS'))

        return config

    def to_dict(self):
        """转换为字典"""
        return {
            'cache': self.cache.__dict__,
            'rate_limit': self.rate_limit.__dict__,
            'performance': self.performance.__dict__,
            'kubectl': self.kubectl.__dict__,
            'security': {
                # 不包含敏感信息
                'session_lifetime': self.security.session_lifetime,
                'csrf_enabled': self.security.csrf_enabled,
                'enable_security_headers': self.security.enable_security_headers
            },
            'database': self.database.__dict__,
            'application': {
                'host': self.application.host,
                'port': self.application.port,
                'debug': self.application.debug,
                'log_level': self.application.log_level
            }
        }


# 全局配置实例
config = Config.from_env()


if __name__ == '__main__':
    import json

    print("=== 当前配置 ===\n")
    print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))
