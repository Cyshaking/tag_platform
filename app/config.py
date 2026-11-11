"""
config.py — 唯一配置加载入口
只从 config.yaml 读取，不引入 .env 或环境变量覆盖
"""
import os
from pathlib import Path
from typing import Any, Dict

import yaml


# 项目根目录（tag_platform/）
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"


def _load_yaml() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 模块首次 import 时加载一次
_RAW: Dict[str, Any] = _load_yaml()

# V1.7 P0：视为占位值的特征片段（命中任意一个即拒绝直接使用）
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "please-change", "your-secret", "todo", "default")


def _resolve_secret_key(raw: str) -> str:
    """
    校验 JWT 签名密钥强度。

    config.yaml 仍是唯一配置入口（不引入 .env / 环境变量）。检测到占位值或
    长度不足 32 位时，为本次进程生成临时强随机密钥并输出强告警；
    生产部署必须在 config.yaml 中写入独立的强随机密钥，否则重启后 Token 失效。
    """
    value = (raw or "").strip()
    lowered = value.lower()
    strong = len(value) >= 32 and not any(m in lowered for m in _PLACEHOLDER_MARKERS)
    if strong:
        return value

    import secrets
    import warnings

    warnings.warn(
        "app.secret_key 为占位值或长度不足 32 位，已为本次进程生成临时随机密钥；"
        "重启后既有 Token 将全部失效。生产部署必须在 config.yaml 中配置独立强随机密钥。",
        RuntimeWarning,
        stacklevel=2,
    )
    return secrets.token_urlsafe(48)


class AppConfig:
    """应用配置"""
    host: str = _RAW["app"]["host"]
    port: int = int(_RAW["app"]["port"])
    secret_key: str = _resolve_secret_key(_RAW["app"]["secret_key"])
    token_expire_hours: int = int(_RAW["app"]["token_expire_hours"])


class DBConfig:
    """数据库配置"""
    _raw = _RAW["database"]

    @classmethod
    def sqlite_path(cls) -> str:
        raw = cls._raw["sqlite_path"]
        # 相对路径解析到项目根
        p = Path(raw)
        if not p.is_absolute():
            p = BASE_DIR / p
        return str(p.resolve())

    @classmethod
    def sqlite_url(cls) -> str:
        """SQLAlchemy sqlite URL"""
        return f"sqlite:///{cls.sqlite_path()}"


class DefaultAdminConfig:
    username: str = _RAW["default_admin"]["username"]
    password: str = _RAW["default_admin"]["password"]
    display_name: str = _RAW["default_admin"].get("display_name", "Admin")


class DemoDataConfig:
    """保险演示数据（V1.1）"""
    _raw = _RAW.get("demo_data", {})

    enabled: bool = bool(_raw.get("enabled", True))

    @classmethod
    def sqlite_path(cls) -> str:
        raw = cls._raw.get("sqlite_path", "./data/insurance_demo.db")
        p = Path(raw)
        if not p.is_absolute():
            p = BASE_DIR / p
        return str(p.resolve())


class DemoSwitchConfig:
    """演示身份切换白名单（V1.1）"""
    _raw = _RAW.get("demo_switch", {})

    enabled: bool = bool(_raw.get("enabled", False))
    users: list = list(_raw.get("users", []))



class LogConfig:
    level: str = _RAW["log"]["level"]
    dir: str = _RAW["log"]["dir"]


class DefaultRolesConfig:
    roles: list = _RAW.get("default_roles", [])


# 便捷导出
app = AppConfig
db = DBConfig
admin = DefaultAdminConfig
demo_data = DemoDataConfig
demo_switch = DemoSwitchConfig
log = LogConfig
roles = DefaultRolesConfig
