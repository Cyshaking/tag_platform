"""
schemas/tag_task.py — 标签任务（V1.1 双模式）
"""
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TagTaskCreate(BaseModel):
    task_name: str = Field(..., min_length=1, max_length=256)
    task_mode: Literal["FIELD", "SQL"] = "FIELD"
    # V1.1：新流程必须选择业务主题（主表由主题表强制指定）
    theme_id: Optional[int] = None
    # 兼容 V1.0 调用：未传 theme_id 时沿用主表/主字段
    business_theme: Optional[str] = None
    main_table_id: Optional[int] = None
    main_field_id: Optional[int] = None
    tag_value_code: Optional[str] = None
    datasource_id: int
    raw_sql: Optional[str] = None
    field_config: Optional[Dict[str, Any]] = None


class TagTaskUpdate(BaseModel):
    task_name: Optional[str] = None
    business_theme: Optional[str] = None
    tag_value_code: Optional[str] = None
    datasource_id: Optional[int] = None
    raw_sql: Optional[str] = None
    field_config: Optional[Dict[str, Any]] = None


class ValidateSQLRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    datasource_id: int


class PreviewSQLRequest(BaseModel):
    task_mode: Literal["FIELD", "SQL"] = "FIELD"
    theme_id: Optional[int] = None
    main_table_id: Optional[int] = None
    main_field_id: Optional[int] = None
    tag_value_code: Optional[str] = None
    raw_sql: Optional[str] = None
    field_config: Optional[Dict[str, Any]] = None


class ValidateSQLResponse(BaseModel):
    valid: bool
    normalized_sql: str = ""
    message: str = ""


class TagTaskOut(ORMModel):
    id: int
    task_name: str
    task_mode: str = "FIELD"
    theme_id: Optional[int] = None
    business_theme: str
    main_table_id: int
    main_field_id: int
    tag_value_code: str
    raw_sql: Optional[str] = None
    field_config_json: Optional[str] = None
    datasource_id: int
    generated_sql: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
