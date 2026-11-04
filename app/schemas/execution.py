"""
schemas/execution.py — 执行引擎相关
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExecutionSubmitRequest(BaseModel):
    tag_task_id: int
    # 允许覆盖默认数据源
    datasource_id: Optional[int] = None


class ExecutionRecordSimple(ORMModel):
    """列表视图 - 精简"""
    id: int
    tag_task_id: int
    datasource_id: int
    ds_type: str
    external_task_id: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class ExecutionRecordOut(ExecutionRecordSimple):
    """详情视图 - 完整"""
    submitted_sql: str
    execute_log: Optional[str] = None
    error_message: Optional[str] = None
