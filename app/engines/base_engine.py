"""
engines/base_engine.py — SQL 执行引擎抽象基类
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskStatusInfo:
    """查询执行状态的返回对象"""
    status: str  # pending / running / success / failed
    log: str = ""  # 执行日志片段
    error: str = ""  # 错误信息（失败时）
    # 可选：执行耗时、结果行数
    duration_ms: Optional[int] = None
    row_count: Optional[int] = None


class BaseEngine(ABC):
    """
    SQL 统一执行引擎基类

    子类职责：
    - submit_sql:   提交 SQL，返回引擎侧 task_id（同步引擎可返回固定值）
    - get_task_status: 查询执行状态
    """

    # 子类覆盖：引擎类型标识，与 Datasource.ds_type 对应
    ENGINE_TYPE: str = "base"

    # 任务状态常量
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    @abstractmethod
    def submit_sql(self, sql: str, datasource_config: Dict[str, Any]) -> str:
        """
        提交 SQL 执行

        Args:
            sql: 要执行的 SQL 语句
            datasource_config: 数据源连接配置（dict）

        Returns:
            str: 引擎侧的 task_id（用于后续 get_task_status）
                 同步引擎可返回固定字符串如 "ok"
        """
        raise NotImplementedError

    @abstractmethod
    def get_task_status(self, task_id: str, datasource_config: Optional[Dict[str, Any]] = None) -> TaskStatusInfo:
        """
        查询执行状态

        Args:
            task_id: submit_sql 返回的 task_id
            datasource_config: 数据源配置（Spark 场景可能需要复用连接）

        Returns:
            TaskStatusInfo: 包含 status / log / error 的结构化结果
        """
        raise NotImplementedError

    # ========== 辅助方法（子类可复用）==========
    def validate_sql(self, sql: str, datasource_config: Dict[str, Any]) -> tuple[bool, str]:
        """
        校验 SQL 合法性与可执行性（V1.1 新增，默认实现直接通过）。
        子类应按引擎特性覆盖：sqlite 用 EXPLAIN 编译；spark mock 直接通过。
        """
        return True, "默认校验通过"

    def _safe_execute(self, func, *args, **kwargs) -> TaskStatusInfo:
        """统一 try-except 包装，避免子类重复写异常处理"""
        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration = int((time.time() - start) * 1000)
            if isinstance(result, TaskStatusInfo):
                result.duration_ms = duration
                return result
            return TaskStatusInfo(status=self.STATUS_SUCCESS, log=str(result), duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return TaskStatusInfo(
                status=self.STATUS_FAILED,
                log=self._format_exception(e),
                error=str(e),
                duration_ms=duration,
            )

    @staticmethod
    def _format_exception(e: Exception) -> str:
        import traceback
        return traceback.format_exc()
