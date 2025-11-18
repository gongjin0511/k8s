"""
安全工具模块
提供请求限流、CSRF保护、输入验证等安全功能
"""

import time
import hashlib
import secrets
from functools import wraps
from typing import Dict, Callable, Optional
from collections import defaultdict
from threading import Lock
import logging
from flask import request, session, jsonify
import re

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    请求限流器（Token Bucket算法）
    - 支持IP级别限流
    - 支持用户级别限流
    - 自动清理过期数据
    """

    def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
        """
        初始化限流器

        Args:
            capacity: 桶容量（最大令牌数）
            refill_rate: 令牌填充速率（令牌/秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets = defaultdict(lambda: {'tokens': capacity, 'last_update': time.time()})
        self._lock = Lock()

    def _refill(self, key: str):
        """填充令牌"""
        bucket = self._buckets[key]
        now = time.time()
        elapsed = now - bucket['last_update']

        # 计算新增令牌数
        new_tokens = elapsed * self.refill_rate
        bucket['tokens'] = min(self.capacity, bucket['tokens'] + new_tokens)
        bucket['last_update'] = now

    def is_allowed(self, key: str, cost: int = 1) -> bool:
        """
        检查是否允许请求

        Args:
            key: 限流键（通常是IP或用户ID）
            cost: 本次请求消耗的令牌数

        Returns:
            是否允许请求
        """
        with self._lock:
            self._refill(key)
            bucket = self._buckets[key]

            if bucket['tokens'] >= cost:
                bucket['tokens'] -= cost
                return True
            else:
                logger.warning(f"请求被限流: {key}")
                return False

    def get_remaining(self, key: str) -> int:
        """获取剩余令牌数"""
        with self._lock:
            self._refill(key)
            return int(self._buckets[key]['tokens'])

    def cleanup(self, max_age_seconds: int = 3600):
        """清理长时间未使用的bucket"""
        with self._lock:
            now = time.time()
            keys_to_remove = [
                k for k, v in self._buckets.items()
                if now - v['last_update'] > max_age_seconds
            ]
            for key in keys_to_remove:
                del self._buckets[key]

            if keys_to_remove:
                logger.info(f"清理了 {len(keys_to_remove)} 个过期的限流bucket")


# 全局限流器
# API限流器 - 每秒10个请求，最多100个请求
api_limiter = RateLimiter(capacity=100, refill_rate=10.0)

# 登录限流器 - 每分钟5次，最多10次
login_limiter = RateLimiter(capacity=10, refill_rate=5.0 / 60.0)


def rate_limit(limiter: RateLimiter = api_limiter, cost: int = 1, key_func: Optional[Callable] = None):
    """
    请求限流装饰器

    Args:
        limiter: 限流器实例
        cost: 令牌消耗数
        key_func: 生成限流键的函数，默认使用IP地址

    Example:
        @rate_limit(api_limiter, cost=2)
        def expensive_api():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 生成限流键
            if key_func:
                key = key_func()
            else:
                key = request.remote_addr or 'unknown'

            # 检查限流
            if not limiter.is_allowed(key, cost):
                remaining = limiter.get_remaining(key)
                return jsonify({
                    'success': False,
                    'error': '请求过于频繁，请稍后再试',
                    'rate_limit': {
                        'remaining': remaining,
                        'retry_after': 1  # 建议1秒后重试
                    }
                }), 429

            return f(*args, **kwargs)

        return decorated_function
    return decorator


class CSRFProtection:
    """
    CSRF保护
    - 基于双重提交Cookie模式
    - 自动生成和验证CSRF令牌
    """

    TOKEN_LENGTH = 32
    SESSION_KEY = '_csrf_token'

    @staticmethod
    def generate_token() -> str:
        """生成CSRF令牌"""
        return secrets.token_hex(CSRFProtection.TOKEN_LENGTH)

    @staticmethod
    def get_token() -> str:
        """获取当前会话的CSRF令牌（如不存在则生成）"""
        if CSRFProtection.SESSION_KEY not in session:
            session[CSRFProtection.SESSION_KEY] = CSRFProtection.generate_token()
        return session[CSRFProtection.SESSION_KEY]

    @staticmethod
    def validate_token(token: str) -> bool:
        """验证CSRF令牌"""
        session_token = session.get(CSRFProtection.SESSION_KEY)
        if not session_token:
            return False
        return secrets.compare_digest(session_token, token)


def csrf_protect(f):
    """
    CSRF保护装饰器
    仅对POST、PUT、DELETE请求进行验证

    Example:
        @csrf_protect
        def delete_resource():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 仅对修改性请求进行CSRF验证
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # 从请求头或表单获取令牌
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')

            if not token or not CSRFProtection.validate_token(token):
                logger.warning(f"CSRF验证失败: {request.remote_addr} - {request.path}")
                return jsonify({
                    'success': False,
                    'error': 'CSRF验证失败',
                    'requires_csrf': True
                }), 403

        return f(*args, **kwargs)

    return decorated_function


class InputValidator:
    """输入验证器"""

    # 常用正则模式
    PATTERNS = {
        'namespace': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\*)?$',  # K8s namespace格式（支持通配符）
        'pod': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',  # Pod名称格式
        'deployment': r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',
        'file_path': r'^/[\w\-/\.]+$',  # 文件路径
        'keyword': r'^[\w\-\s]+$',  # 搜索关键字
    }

    @staticmethod
    def validate_pattern(value: str, pattern_name: str) -> bool:
        """
        验证值是否匹配指定模式

        Args:
            value: 要验证的值
            pattern_name: 模式名称

        Returns:
            是否有效
        """
        pattern = InputValidator.PATTERNS.get(pattern_name)
        if not pattern:
            raise ValueError(f"未知的验证模式: {pattern_name}")

        return bool(re.match(pattern, value))

    @staticmethod
    def validate_namespace(namespace: str) -> bool:
        """验证namespace格式"""
        if not namespace or len(namespace) > 63:
            return False
        return InputValidator.validate_pattern(namespace, 'namespace')

    @staticmethod
    def validate_pod_name(pod: str) -> bool:
        """验证pod名称格式"""
        if not pod or len(pod) > 253:
            return False
        return InputValidator.validate_pattern(pod, 'pod')

    @staticmethod
    def validate_file_path(path: str) -> bool:
        """验证文件路径"""
        # 防止路径遍历攻击
        if '..' in path or path.startswith('~'):
            return False
        return InputValidator.validate_pattern(path, 'file_path')

    @staticmethod
    def sanitize_keywords(keywords: list) -> list:
        """清理搜索关键字"""
        sanitized = []
        for kw in keywords:
            # 移除特殊字符，防止注入
            clean_kw = re.sub(r'[^\w\s\-\.]', '', kw.strip())
            if clean_kw:
                sanitized.append(clean_kw[:100])  # 限制长度
        return sanitized


def validate_input(validators: Dict[str, Callable]):
    """
    输入验证装饰器

    Args:
        validators: 验证器字典 {参数名: 验证函数}

    Example:
        @validate_input({
            'namespace': InputValidator.validate_namespace,
            'pod': InputValidator.validate_pod_name
        })
        def get_logs(namespace, pod):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 从请求中获取参数
            if request.method == 'GET':
                params = request.args
            else:
                params = request.get_json() or {}

            # 验证每个参数
            for param_name, validator_func in validators.items():
                value = params.get(param_name)
                if value and not validator_func(value):
                    logger.warning(f"输入验证失败: {param_name}={value}")
                    return jsonify({
                        'success': False,
                        'error': f'参数验证失败: {param_name}',
                        'invalid_param': param_name
                    }), 400

            return f(*args, **kwargs)

        return decorated_function
    return decorator


class SecurityHeaders:
    """安全响应头"""

    @staticmethod
    def add_security_headers(response):
        """添加安全响应头"""
        # 防止XSS
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # CSP
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"

        # HSTS
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return response


def hash_password(password: str) -> str:
    """密码哈希（使用SHA-256）"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    return secrets.compare_digest(hash_password(password), password_hash)


if __name__ == '__main__':
    # 测试限流器
    print("=== 限流器测试 ===")
    limiter = RateLimiter(capacity=5, refill_rate=1.0)

    # 快速请求6次
    for i in range(6):
        allowed = limiter.is_allowed('test_ip')
        remaining = limiter.get_remaining('test_ip')
        print(f"请求 {i + 1}: 允许={allowed}, 剩余令牌={remaining}")

    # 等待1秒后再试
    print("\n等待1秒...")
    time.sleep(1)
    allowed = limiter.is_allowed('test_ip')
    remaining = limiter.get_remaining('test_ip')
    print(f"1秒后: 允许={allowed}, 剩余令牌={remaining}")

    # 测试输入验证
    print("\n=== 输入验证测试 ===")
    test_cases = [
        ('erp-prod', 'namespace'),
        ('erp-*', 'namespace'),
        ('INVALID!', 'namespace'),
        ('/applog/root.log', 'file_path'),
        ('../etc/passwd', 'file_path'),
    ]

    for value, pattern in test_cases:
        valid = InputValidator.validate_pattern(value, pattern)
        print(f"{value:20} ({pattern:10}): {'✓ 有效' if valid else '✗ 无效'}")
