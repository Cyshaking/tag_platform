"""
schemas/relation.py — 表关联
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RelationCreate(BaseModel):
    left_table_id: int
    left_field_id: int
    right_table_id: int
    right_field_id: int
    relation_type: str = Field(default="INNER", pattern=r"^(INNER|LEFT|RIGHT)$")


class RelationUpdate(BaseModel):
    relation_type: Optional[str] = Field(default=None, pattern=r"^(INNER|LEFT|RIGHT)$")
    left_field_id: Optional[int] = None
    right_field_id: Optional[int] = None


class RelationOut(ORMModel):
    id: int
    left_table_id: int
    left_field_id: int
    right_table_id: int
    right_field_id: int
    relation_type: str
