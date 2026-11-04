"""
engines/sqlite_engine.py — SQLite 同步执行引擎
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any, Dict, List, Optional

from app.engines.base_engine import BaseEngine, TaskStatusInfo


class SqliteEngine(BaseEngine):
    """
    SQLite 执行引擎

    - 同步执行：submit_sql 直接执行 SQL 并返回固定 task_id
    - get_task_status 立即返回执行结果（同步语义）
    """

    ENGINE_TYPE = "sqlite"

    # sqlite3 模块支持的 DDL/DML/DQL 语句前缀
    _NON_QUERY_PREFIXES = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE", "REPLACE")

    def validate_sql(self, sql: str, datasource_config: Dict[str, Any]) -> tuple[bool, str]:
        """
        V1.1：使用 EXPLAIN 编译校验（不读取数据、无副作用）。
        sqlite 编译期即会校验表/字段是否存在。
        """
        db_path = datasource_config.get("db_path")
        if not db_path:
            return False, "sqlite 数据源缺少 db_path 配置"

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("EXPLAIN " + sql)
            return True, "SQLite 编译校验通过"
        except Exception as e:
            return False, f"SQLite 校验失败: {e}"
        finally:
            if conn is not None:
                conn.close()

    def submit_sql(self, sql: str, datasource_config: Dict[str, Any]) -> str:
        db_path = datasource_config.get("db_path")
        if not db_path:
            raise ValueError("sqlite 数据源缺少 db_path 配置")

        start = time.time()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            # 支持多语句：用 executescript 不行（它不返回结果集），这里用 execute 单语句
            cursor.execute(sql)
            conn.commit()
        except Exception as e:
            conn.close()
            # 异常向上抛出，由 base_engine 包装
            raise
        # 同步保存结果到一个内部字典（get_task_status 读取）
        duration_ms = int((time.time() - start) * 1000)
        task_id = f"sqlite_{int(time.time() * 1000)}"
        # 简单执行：同步完成直接返回
        self._last_result = TaskStatusInfo(
            status=self.STATUS_SUCCESS,
            log=f"执行成功，耗时 {duration_ms}ms",
            row_count=cursor.rowcount,
            duration_ms=duration_ms,
        )
        conn.close()
        return task_id

    def get_task_status(self, task_id: str, datasource_config: Optional[Dict[str, Any]] = None) -> TaskStatusInfo:
        """同步引擎：submit_sql 已经执行完毕，这里直接返回结果"""
        return self._last_result


def test_sqlite_engine(db_path: str, sql: str) -> TaskStatusInfo:
    """快速调用入口 - 供测试或简单同步执行使用"""
    engine = SqliteEngine()
    try:
        engine.submit_sql(sql, {"db_path": db_path})
        return engine.get_task_status("")
    except Exception as e:
        return TaskStatusInfo(status="failed", log=str(e), error=str(e))
