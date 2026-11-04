"""
security.py — 密码哈希 + JWT Token
直接使用 bcrypt 原生接口（避免 passlib 与 bcrypt 5.x 兼容问题）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt

from app.config import app as app_cfg


JWT_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """bcrypt 哈希，自动截断到 72 字节"""
    if len(plain.encode("utf-8")) > 72:
        plain = plain.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: int | str, expires_hours: Optional[int] = None) -> str:
    """创建 JWT Token。subject 通常为 user.id"""
    if expires_hours is None:
        expires_hours = app_cfg.token_expire_hours
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "exp": now + timedelta(hours=expires_hours),
        "iat": now,
    }
    return jwt.encode(payload, app_cfg.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 Token，过期或签名错误返回 None"""
    try:
        return jwt.decode(token, app_cfg.secret_key, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
