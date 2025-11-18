"""
配置管理模块 - 集中管理所有配置项
支持环境变量覆盖，遵循12-Factor App原则
"""

import os
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """缓存配置"""
    namespaces_ttl: int = int(os.getenv('CACHE_NAMESPACES_TTL', '60'))
    namespaces_max_size: int = int(os.getenv('CACHE_NAMESPACES_MAX_SIZE', '100'))

    deployments_ttl: int = int(os.getenv('CACHE_DEPLOYMENTS_TTL', '30'))
    deployments_max_size: int = int(os.getenv('CACHE_DEPLOYMENTS_MAX_SIZE', '500'))

    pods_ttl: int = int(os.getenv('CACHE_PODS_TTL', '10'))
    pods_max_size: int = int(os.getenv('CACHE_PODS_MAX_SIZE', '1000'))

    logs_ttl: int = int(os.getenv('CACHE_LOGS_TTL', '5'))
    logs_max_size: int = int(os.getenv('CACHE_LOGS_MAX_SIZE', '200'))

    cleanup_interval: int = int(os.getenv('CACHE_CLEANUP_INTERVAL', '30'))

    # LRU策略配置
    use_lru: bool = os.getenv('CACHE_USE_LRU', 'true').lower() == 'true'


@dataclass
class DatabaseConfig:
    """数据库配置"""
    db_path: str = os.getenv('DB_PATH', 'k8s_logs.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '10'))
    timeout: int = int(os.getenv('DB_TIMEOUT', '30'))

    # 自动清理配置
    auto_cleanup_enabled: bool = os.getenv('DB_AUTO_CLEANUP', 'true').lower() == 'true'
    history_retention_days: int = int(os.getenv('DB_HISTORY_RETENTION_DAYS', '30'))

    # 性能优化
    journal_mode: str = os.getenv('DB_JOURNAL_MODE', 'WAL')  # WAL模式提升并发性能
    synchronous: str = os.getenv('DB_SYNCHRONOUS', 'NORMAL')  # NORMAL平衡性能和安全
    cache_size: int = int(os.getenv('DB_CACHE_SIZE', '10000'))  # 页面缓存大小


@dataclass
class KubectlConfig:
    """Kubectl配置"""
    timeout: int = int(os.getenv('KUBECTL_TIMEOUT', '300'))
    log_dir: str = os.getenv('KUBECTL_LOG_DIR', '/applog')

    # 重试配置
    max_retries: int = int(os.getenv('KUBECTL_MAX_RETRIES', '3'))
    retry_delay: float = float(os.getenv('KUBECTL_RETRY_DELAY', '1.0'))
    retry_backoff: float = float(os.getenv('KUBECTL_RETRY_BACKOFF', '2.0'))

    # 批量操作配置
    batch_max_workers: int = int(os.getenv('KUBECTL_BATCH_MAX_WORKERS', '5'))
    batch_timeout: int = int(os.getenv('KUBECTL_BATCH_TIMEOUT', '600'))


@dataclass
class ApiConfig:
    """API配置"""
    # 限流配置
    rate_limit_enabled: bool = os.getenv('API_RATE_LIMIT_ENABLED', 'true').lower() == 'true'
    rate_limit_per_minute: int = int(os.getenv('API_RATE_LIMIT_PER_MINUTE', '60'))
    rate_limit_burst: int = int(os.getenv('API_RATE_LIMIT_BURST', '10'))

    # 请求限制
    max_batch_pods: int = int(os.getenv('API_MAX_BATCH_PODS', '100'))
    max_download_size: int = int(os.getenv('API_MAX_DOWNLOAD_SIZE', str(100 * 1024 * 1024)))  # 100MB
    max_tail_lines: int = int(os.getenv('API_MAX_TAIL_LINES', '10000'))

    # 超时配置
    request_timeout: int = int(os.getenv('API_REQUEST_TIMEOUT', '300'))


@dataclass
class SecurityConfig:
    """安全配置"""
    secret_key: str = os.getenv('SECRET_KEY', 'k8s-log-viewer-secret-key-2025')
    login_password: str = os.getenv('LOGIN_PASSWORD', 'Cnnc@2025')

    # Session配置
    session_lifetime: int = int(os.getenv('SESSION_LIFETIME', '3600'))  # 1小时
    session_permanent: bool = os.getenv('SESSION_PERMANENT', 'true').lower() == 'true'

    # CORS配置
    cors_origins: str = os.getenv('CORS_ORIGINS', '*')
    cors_credentials: bool = os.getenv('CORS_CREDENTIALS', 'true').lower() == 'true'


@dataclass
class LogConfig:
    """日志配置"""
    level: str = os.getenv('LOG_LEVEL', 'INFO')
    format: str = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 文件日志配置
    file_enabled: bool = os.getenv('LOG_FILE_ENABLED', 'false').lower() == 'true'
    file_path: str = os.getenv('LOG_FILE_PATH', 'logs/app.log')
    file_max_bytes: int = int(os.getenv('LOG_FILE_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB
    file_backup_count: int = int(os.getenv('LOG_FILE_BACKUP_COUNT', '5'))


class Config:
    """全局配置类"""

    def __init__(self):
        self.cache = CacheConfig()
        self.database = DatabaseConfig()
        self.kubectl = KubectlConfig()
        self.api = ApiConfig()
        self.security = SecurityConfig()
        self.log = LogConfig()

        # 应用环境
        self.env = os.getenv('APP_ENV', 'production')
        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
        self.host = os.getenv('HOST', '0.0.0.0')
        self.port = int(os.getenv('PORT', '5000'))

        self._validate_config()
        self._log_config()

    def _validate_config(self):
        """验证配置的有效性"""
        errors = []

        # 验证密码强度
        if len(self.security.login_password) < 8:
            errors.append("登录密码长度至少为8个字符")

        # 验证缓存配置
        if self.cache.namespaces_ttl < 1:
            errors.append("缓存TTL必须大于0")

        # 验证数据库配置
        if self.database.pool_size < 1:
            errors.append("数据库连接池大小必须至少为1")

        # 验证API限流配置
        if self.api.rate_limit_enabled and self.api.rate_limit_per_minute < 1:
            errors.append("API限流频率必须大于0")

        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _log_config(self):
        """记录配置信息（隐藏敏感信息）"""
        if self.debug:
            logger.info("=" * 60)
            logger.info("应用配置:")
            logger.info(f"  环境: {self.env}")
            logger.info(f"  调试模式: {self.debug}")
            logger.info(f"  主机: {self.host}:{self.port}")
            logger.info(f"  数据库: {self.database.db_path}")
            logger.info(f"  缓存策略: {'LRU' if self.cache.use_lru else 'TTL'}")
            logger.info(f"  API限流: {self.api.rate_limit_enabled}")
            logger.info(f"  日志级别: {self.log.level}")
            logger.info("=" * 60)

    def get_flask_config(self) -> dict:
        """获取Flask应用配置"""
        return {
            'SECRET_KEY': self.security.secret_key,
            'DEBUG': self.debug,
            'PERMANENT_SESSION_LIFETIME': self.security.session_lifetime,
            'SESSION_COOKIE_SECURE': self.env == 'production',
            'SESSION_COOKIE_HTTPONLY': True,
            'SESSION_COOKIE_SAMESITE': 'Lax',
        }


# 全局配置实例
config = Config()


def reload_config():
    """重新加载配置（用于热更新）"""
    global config
    config = Config()
    logger.info("配置已重新加载")


if __name__ == '__main__':
    # 测试配置
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\n配置测试:")
    print(f"缓存TTL (namespaces): {config.cache.namespaces_ttl}秒")
    print(f"数据库路径: {config.database.db_path}")
    print(f"Kubectl超时: {config.kubectl.timeout}秒")
    print(f"API限流: {config.api.rate_limit_per_minute}次/分钟")
    print(f"日志级别: {config.log.level}")
    print(f"\nFlask配置: {config.get_flask_config()}")
