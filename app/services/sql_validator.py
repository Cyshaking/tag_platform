"""
services/sql_validator.py — SQL 直配模式的只读校验（V1.1 新增）

校验逻辑集中在此，router 仅转发。校验分两层：
1. 静态校验：只读语句、单条语句、写操作关键字黑名单；
2. 编译校验：交给数据源对应引擎（sqlite EXPLAIN / spark mock）。
"""
from __future__ import annotations

import json
import re
from typing import Tuple

from sqlalchemy.orm import Session

from app.db.models.datasource import Datasource
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_NOT_FOUND, ERR_DS_DISABLED


_ENGINE_MAP = None


def _engines():
    global _ENGINE_MAP
    if _ENGINE_MAP is None:
        from app.engines.sqlite_engine import SqliteEngine
        from app.engines.spark_thrift_engine import SparkThriftEngine
        _ENGINE_MAP = {"sqlite": SqliteEngine, "spark": SparkThriftEngine}
    return _ENGINE_MAP


class SQLValidator(BaseService):
    MODULE = "tag_task"

    _FORBIDDEN = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|"
        r"ATTACH|DETACH|PRAGMA|VACUUM|GRANT|REVOKE|MERGE)\b",
        re.IGNORECASE,
    )
    _READONLY_HEAD = re.compile(r"^(SELECT|WITH)\b", re.IGNORECASE)
    _COMMENT = re.compile(r"(--[^\n]*\n)|(/\*.*?\*/)", re.DOTALL)

    # ==================================================================
    # 对外入口
    # ==================================================================
    def validate(self, sql: str, datasource_id: int) -> dict:
        """校验 SQL，返回 {valid, normalized_sql, message}"""
        ds = self.db.get(Datasource, datasource_id)
        if not ds:
            raise BusinessException(ERR_NOT_FOUND, f"数据源 {datasource_id} 不存在")
        if not ds.is_enabled:
            raise BusinessException(ERR_DS_DISABLED, f"数据源 '{ds.name}' 已禁用")

        ok, message, normalized = self.validate_text(sql)
        if not ok:
            self._log_info(f"[validate_sql] 静态校验失败: {message}")
            return {"valid": False, "normalized_sql": normalized, "message": message}

        engine_cls = _engines().get(ds.ds_type)
        if not engine_cls:
            return {"valid": False, "normalized_sql": normalized,
                    "message": f"不支持的数据源类型: {ds.ds_type}"}

        try:
            ds_config = json.loads(ds.config_json)
        except (json.JSONDecodeError, TypeError):
            ds_config = {}

        engine = engine_cls()
        ok, message = engine.validate_sql(normalized, ds_config)
        if not ok:
            self._log_info(f"[validate_sql] 引擎校验失败: {message}")
        return {"valid": ok, "normalized_sql": normalized, "message": message}

    # ==================================================================
    # 静态校验
    # ==================================================================
    def validate_text(self, sql: str) -> Tuple[bool, str, str]:
        """只读静态校验，返回 (是否通过, 原因, 规范化 SQL)"""
        raw = (sql or "").strip()
        if not raw:
            return False, "SQL 不能为空", ""

        normalized = self._COMMENT.sub(" ", raw).strip()
        while normalized.endswith(";"):
            normalized = normalized[:-1].rstrip()

        if ";" in normalized:
            return False, "仅支持单条 SELECT 语句，禁止多语句", normalized
        if not self._READONLY_HEAD.match(normalized):
            return False, "仅允许 SELECT 或 WITH 开头的只读查询", normalized
        match = self._FORBIDDEN.search(normalized)
        if match:
            return False, f"SQL 包含禁止的写操作关键字: {match.group(0).upper()}", normalized
        return True, "校验通过", normalized
