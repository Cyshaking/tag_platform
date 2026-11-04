"""
schemas/metadata.py — 元数据（表 + 字段）
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ========== 字段 ==========
class MetaFieldCreate(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=128)
    field_type: str = Field(..., min_length=1, max_length=64)
    field_comment: Optional[str] = None
    is_primary_key: bool = False
    is_nullable: bool = True
    ordinal_position: Optional[int] = None


class MetaFieldOut(ORMModel):
    id: int
    table_id: int
    field_name: str
    field_type: str
    field_comment: Optional[str] = None
    is_primary_key: bool
    is_nullable: bool
    ordinal_position: int


# ========== 表 ==========
class MetaTableCreate(BaseModel):
    table_name: str = Field(..., min_length=1, max_length=128)
    table_comment: Optional[str] = None
    datasource_id: Optional[int] = None
    fields: List[MetaFieldCreate] = Field(default_factory=list)


class MetaTableUpdate(BaseModel):
    table_comment: Optional[str] = None
    datasource_id: Optional[int] = None
    # 简单更新：整体替换 fields 列表
    fields: Optional[List[MetaFieldCreate]] = None


class MetaTableOut(ORMModel):
    id: int
    table_name: str
    table_comment: Optional[str] = None
    datasource_id: Optional[int] = None
    status: str
    fields: List[MetaFieldOut] = []


class MetadataBatchCreate(BaseModel):
    """批量创建表 + 字段（一次提交多个表）"""
    tables: List[MetaTableCreate]


class ExcelImportResponse(BaseModel):
    table: MetaTableOut
    field_count: int
    message: str = "导入成功"
