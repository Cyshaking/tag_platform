"""
services/execution_service.py — SQL 统一执行调度 + 后台轮询
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tag_task import TagTask, TaskExecuteRecord
from app.db.models.datasource import Datasource
from app.services.base import BaseService
from app.services.datasource_service import DatasourceService
from app.engines.base_engine import BaseEngine, TaskStatusInfo
from app.engines.sqlite_engine import SqliteEngine
from app.engines.spark_thrift_engine import SparkThriftEngine
from app.utils.exceptions import BusinessException, ERR_NOT_FOUND, ERR_DS_DISABLED, ERR_TAG_SQL_EMPTY, ERR_APPROVE_STATE


# ds_type → 引擎类
_ENGINE_MAP: Dict[str, type] = {
    "sqlite": SqliteEngine,
    "spark": SparkThriftEngine,
}


class ExecutionService(BaseService):
    MODULE = "execution"

    # ======================================================================
    # 提交执行
    # ======================================================================
    def submit(self, tag_task_id: int, datasource_id: Optional[int] = None,
               background_tasks: Optional[BackgroundTasks] = None,
               operator_id: Optional[int] = None) -> TaskExecuteRecord:
        """
        提交一条标签任务的 SQL 执行

        Args:
            tag_task_id: 标签任务 ID
            datasource_id: 可选覆盖数据源
            background_tasks: FastAPI BackgroundTasks（Spark 异步场景需要）
            operator_id: 操作人

        Returns:
            TaskExecuteRecord（status=pending 或 running）
        """
        # 1. 读取标签任务
        task = self.db.get(TagTask, tag_task_id)
        if not task:
            raise BusinessException(ERR_NOT_FOUND, f"标签任务 {tag_task_id} 不存在")
        if not task.generated_sql:
            raise BusinessException(ERR_TAG_SQL_EMPTY, f"标签任务 '{task.task_name}' 未生成 SQL")

        # V1.2：执行审批门禁 — 标签任务必须审批通过才能执行
        if task.status != "approved":
            _status_labels = {
                "pending": "未提交审批",
                "in_progress": "审批中",
                "rejected": "已驳回",
            }
            label = _status_labels.get(task.status, task.status)
            raise BusinessException(
                ERR_APPROVE_STATE,
                f"标签任务 '{task.task_name}' 审批状态为「{label}」，需审批通过后方可执行",
            )

        # 2. 确定数据源
        effective_ds_id = datasource_id or task.datasource_id
        ds = self.db.get(Datasource, effective_ds_id)
        if not ds:
            raise BusinessException(ERR_NOT_FOUND, f"数据源 {effective_ds_id} 不存在")
        if not ds.is_enabled:
            raise BusinessException(ERR_DS_DISABLED, f"数据源 '{ds.name}' 已禁用")

        # 3. 创建执行记录
        record = TaskExecuteRecord(
            tag_task_id=task.id,
            datasource_id=ds.id,
            submitted_sql=task.generated_sql,
            ds_type=ds.ds_type,
            status="pending",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        # 4. 同步执行或注册后台任务
        engine_cls = _ENGINE_MAP.get(ds.ds_type)
        if not engine_cls:
            record.status = "failed"
            record.error_message = f"不支持的数据源类型: {ds.ds_type}"
            record.finished_at = datetime.utcnow()
            self.db.commit()
            raise BusinessException(ERR_BAD_REQUEST, f"不支持的数据源类型: {ds.ds_type}")

        engine = engine_cls()
        ds_config = self._ds_raw_config(ds)

        record.status = "running"
        record.started_at = datetime.utcnow()
        self.db.commit()

        if ds.ds_type == "sqlite":
            # 同步执行
            self._run_sync(engine, record, ds_config)
        elif ds.ds_type == "spark":
            # 异步提交 + BackgroundTasks 轮询
            self._run_async(engine, record, ds_config, background_tasks)

        self._log_info(f"提交执行 tag_task={task.id} ds={ds.id} ds_type={ds.ds_type}", operator_id)
        return record

    # ======================================================================
    # 轮询
    # ======================================================================
    def poll_task_status(self, record_id: int, engine: BaseEngine, ds_config: Dict[str, Any]) -> None:
        """
        BackgroundTasks 调用的轮询函数。查到完成则更新状态，否则继续等待。
        最多轮询 60 次（约 5 分钟）。
        """
        MAX_POLL = 60
        POLL_INTERVAL_SEC = 5

        with self.db.begin() as session:
            record = session.get(TaskExecuteRecord, record_id)
            if not record or record.status not in ("pending", "running"):
                return  # 已完成或不存在

            for i in range(MAX_POLL):
                status: TaskStatusInfo = engine.get_task_status(record.external_task_id or "", ds_config)
                record.execute_log = status.log
                if status.duration_ms:
                    record.execute_log += f"\n[耗时 {status.duration_ms}ms]"

                if status.status == BaseEngine.STATUS_SUCCESS:
                    record.status = "success"
                    record.finished_at = datetime.utcnow()
                    session.commit()
                    return
                elif status.status == BaseEngine.STATUS_FAILED:
                    record.status = "failed"
                    record.error_message = status.error
                    record.finished_at = datetime.utcnow()
                    session.commit()
                    return

                # 还在 running → 等下一轮
                time.sleep(POLL_INTERVAL_SEC)

            # 超时 → 标记为 running 并写日志
            record.execute_log = (record.execute_log or "") + "\n[轮询超时，任务仍在执行中]"
            session.commit()

    # ======================================================================
    # 查询（给外部接口用）
    # ======================================================================
    def list_records(self, tag_task_id: Optional[int] = None,
                     status: Optional[str] = None,
                     limit: int = 100) -> List[TaskExecuteRecord]:
        stmt = select(TaskExecuteRecord).order_by(TaskExecuteRecord.created_at.desc())
        if tag_task_id:
            stmt = stmt.where(TaskExecuteRecord.tag_task_id == tag_task_id)
        if status:
            stmt = stmt.where(TaskExecuteRecord.status == status)
        stmt = stmt.limit(limit)
        return self.db.execute(stmt).scalars().all()

    def get_record(self, record_id: int) -> Optional[TaskExecuteRecord]:
        return self.db.get(TaskExecuteRecord, record_id)

    # ======================================================================
    # 内部辅助
    # ======================================================================
    def _run_sync(self, engine: BaseEngine, record: TaskExecuteRecord,
                  ds_config: Dict[str, Any]) -> None:
        """同步执行（sqlite 场景）"""
        try:
            task_id = engine.submit_sql(record.submitted_sql, ds_config)
            record.external_task_id = task_id

            status: TaskStatusInfo = engine.get_task_status(task_id, ds_config)
            record.execute_log = status.log
            if status.duration_ms:
                record.execute_log += f"\n[耗时 {status.duration_ms}ms]"
            record.status = status.status
            if status.status == BaseEngine.STATUS_FAILED:
                record.error_message = status.error
        except Exception as e:
            record.status = "failed"
            record.error_message = str(e)
            record.execute_log = f"执行异常: {e}"
        finally:
            record.finished_at = datetime.utcnow()
            self.db.commit()

    def _run_async(self, engine: BaseEngine, record: TaskExecuteRecord,
                   ds_config: Dict[str, Any],
                   background_tasks: Optional[BackgroundTasks]) -> None:
        """异步提交（spark 场景）"""
        try:
            task_id = engine.submit_sql(record.submitted_sql, ds_config)
            record.external_task_id = task_id
            record.status = "running"
            self.db.commit()

            if background_tasks is not None:
                background_tasks.add_task(self.poll_task_status, record.id, engine, ds_config)
        except Exception as e:
            record.status = "failed"
            record.error_message = str(e)
            record.finished_at = datetime.utcnow()
            self.db.commit()

    def _ds_raw_config(self, ds: Datasource) -> Dict[str, Any]:
        try:
            return json.loads(ds.config_json)
        except Exception:
            return {}


# 避免循环 import
from app.utils.exceptions import ERR_BAD_REQUEST
