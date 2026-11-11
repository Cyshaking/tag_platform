"""
utils/sql_guard.py — SQL 只读校验 + SQLite 库路径白名单（V1.7 P0）

纯函数模块，不依赖 ORM 与业务层，供以下位置复用同一套规则：
- services/sql_validator.py       保存 / 校验接口的静态校验
- services/execution_service.py   执行阶段的二次校验（防止绕过保存时校验）
- services/datasource_service.py  数据源落库与连接测试的路径限制
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

from app.config import BASE_DIR

# 演示数据目录：SQLite 数据源唯一允许落盘的位置
DATA_DIR = (BASE_DIR / "data").resolve()
# 平台主库：禁止被当作业务数据源读取
PLATFORM_DB = (BASE_DIR / "data" / "tag_platform.db").resolve()

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|"
    r"ATTACH|DETACH|PRAGMA|VACUUM|GRANT|REVOKE|MERGE)\b",
    re.IGNORECASE,
)
_READONLY_HEAD = re.compile(r"^(SELECT|WITH)\b", re.IGNORECASE)
_COMMENT = re.compile(r"(--[^\n]*\n)|(/\*.*?\*/)", re.DOTALL)


def check_readonly_sql(sql: str) -> Tuple[bool, str, str]:
    """
    只读静态校验。

    Returns:
        (是否通过, 原因, 去除注释与尾部封号后的规范化 SQL)
    """
    raw = (sql or "").strip()
    if not raw:
        return False, "SQL 不能为空", ""

    normalized = _COMMENT.sub(" ", raw).strip()
    while normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()

    if ";" in normalized:
        return False, "仅支持单条 SELECT 语句，禁止多语句", normalized
    if not _READONLY_HEAD.match(normalized):
        return False, "仅允许 SELECT 或 WITH 开头的只读查询", normalized

    match = _FORBIDDEN.search(normalized)
    if match:
        return False, f"SQL 包含禁止的写操作关键字: {match.group(0).upper()}", normalized
    return True, "校验通过", normalized


def is_memory_db(raw: str) -> bool:
    """是否为内存库（演示与测试场景）"""
    return raw == ":memory:" or raw.startswith("file::memory:")


def ensure_db_path_allowed(raw: str) -> str:
    """
    校验并规范化 SQLite 数据源路径。

    只允许内存库或 data/ 演示数据目录内的文件，禁止指向平台主库。
    非法时抛 ValueError，由调用方转换为 BusinessException。
    """
    if not raw:
        raise ValueError("sqlite 数据源缺少 db_path 配置")
    if is_memory_db(raw):
        return raw

    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    path = path.resolve()

    try:
        path.relative_to(DATA_DIR)
    except ValueError:
        raise ValueError(f"SQLite 数据库路径必须位于 {DATA_DIR} 目录内: {raw}")

    if path == PLATFORM_DB:
        raise ValueError("SQLite 数据源不允许指向平台主库 data/tag_platform.db")
    return str(path)
