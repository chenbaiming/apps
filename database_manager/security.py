"""数据库凭据的加密与随机密码生成工具。"""

import base64
import hashlib
import secrets
import string

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _get_fernet() -> Fernet:
    """根据配置生成 Fernet 实例，并兼容开发环境的临时密钥。"""
    configured_key = settings.CREDENTIAL_ENCRYPTION_KEY.strip()

    if configured_key:
        # 显式配置的密钥优先；格式不正确时让配置错误尽早暴露。
        try:
            return Fernet(configured_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ImproperlyConfigured(
                "CREDENTIAL_ENCRYPTION_KEY 必须是合法的 Fernet 密钥"
            ) from exc

    # 非调试环境禁止使用可推导的默认密钥，避免凭据实际上没有安全保护。
    if not settings.DEBUG:
        raise ImproperlyConfigured(
            "生产环境必须设置 CREDENTIAL_ENCRYPTION_KEY"
        )

    # 开发环境从 SECRET_KEY 派生稳定密钥，让重启后仍能解密已有记录。
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    development_key = base64.urlsafe_b64encode(digest)
    return Fernet(development_key)


def encrypt_secret(raw_value: str) -> str:
    """把明文凭据加密成可存入数据库的文本。"""
    if not raw_value:
        raise ValueError("待加密的凭据不能为空")
    # Fernet 同时提供机密性和完整性校验，返回值为 ASCII 字符串。
    token = _get_fernet().encrypt(raw_value.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """解密数据库中的凭据；密文被篡改时会抛出明确异常。"""
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("凭据无法解密，请检查加密密钥是否一致") from exc


def generate_database_password(length: int = 28) -> str:
    """生成包含大小写字母、数字和符号的高强度随机密码。"""
    if length < 12:
        raise ValueError("随机密码长度不能小于 12")

    character_groups = [
        string.ascii_lowercase,
        string.ascii_uppercase,
        string.digits,
        "!@#$%^&*()-_=+",
    ]
    # 先从每个字符组各取一个，保证生成的密码满足常见复杂度策略。
    password_chars = [secrets.choice(group) for group in character_groups]
    all_characters = "".join(character_groups)
    password_chars.extend(
        secrets.choice(all_characters) for _ in range(length - len(password_chars))
    )
    # 洗牌消除字符组固定顺序带来的可预测性。
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)
