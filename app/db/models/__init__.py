"""
models/__init__.py — 一次性 import 所有子模块，确保 Base.metadata 注册到所有表
"""
from app.db.models import (  # noqa: F401
    user, metadata, relation, enum_config, approval, datasource,
    tag_task, system_log, business_theme, action_log,
)
