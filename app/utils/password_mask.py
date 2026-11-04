"""
password_mask.py — 敏感字段掩码
"""
from typing import Any, Dict


MASK = "******"


def mask_password(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    对数据源 config_json 中的 password 字段做掩码处理（返回副本）
    - sqlite 类型：无密码字段
    - spark 类型：可能有 password 或 user_password
    """
    if not isinstance(config, dict):
        return config
    result = dict(config)
    for key in ("password", "user_password", "pw"):
        if key in result and result[key]:
            result[key] = MASK
    return result


def contains_password(config: Dict[str, Any]) -> bool:
    """判断配置是否包含密码字段"""
    for key in ("password", "user_password", "pw"):
        if key in config:
            return True
    return False
