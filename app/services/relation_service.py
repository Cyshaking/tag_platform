"""
services/relation_service.py — 表关联关系
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.relation import TableRelation
from app.db.models.metadata import MetaTable, MetaField
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_VALIDATION, ERR_NOT_FOUND


class RelationService(BaseService):
    MODULE = "relation"

    def list_relations(self) -> List[TableRelation]:
        return self.db.execute(select(TableRelation).order_by(TableRelation.id)).scalars().all()

    def get_relation(self, relation_id: int) -> Optional[TableRelation]:
        return self.db.get(TableRelation, relation_id)

    def create_relation(self, left_table_id: int, left_field_id: int,
                        right_table_id: int, right_field_id: int,
                        relation_type: str = "INNER",
                        created_by: Optional[int] = None) -> TableRelation:
        # 校验表和字段存在
        for tid, fid, side in [(left_table_id, left_field_id, "left"), (right_table_id, right_field_id, "right")]:
            table = self.db.get(MetaTable, tid)
            if not table:
                raise BusinessException(ERR_NOT_FOUND, f"{side} 表 {tid} 不存在")
            field = self.db.get(MetaField, fid)
            if not field or field.table_id != tid:
                raise BusinessException(ERR_VALIDATION, f"{side} 字段 {fid} 不属于表 {tid}")

        # 同表不允许自关联（可放开，但作业场景简单限制）
        if left_table_id == right_table_id:
            raise BusinessException(ERR_VALIDATION, "不允许同表自关联")

        # 检查重复
        existing = self.db.execute(
            select(TableRelation).where(
                TableRelation.left_table_id == left_table_id,
                TableRelation.left_field_id == left_field_id,
                TableRelation.right_table_id == right_table_id,
                TableRelation.right_field_id == right_field_id,
            )
        ).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_VALIDATION, "该关联规则已存在")

        rel = TableRelation(
            left_table_id=left_table_id,
            left_field_id=left_field_id,
            right_table_id=right_table_id,
            right_field_id=right_field_id,
            relation_type=relation_type.upper(),
            created_by=created_by,
        )
        rel.serial_no = self._gen_serial_no(TableRelation, "REL")  # V1.4.3
        self.db.add(rel)
        self.db.commit()
        self._log_info(f"创建表关联 {left_table_id}.{left_field_id} ↔ {right_table_id}.{right_field_id}", created_by)
        return rel

    def update_relation(self, relation_id: int, relation_type: Optional[str] = None,
                        left_field_id: Optional[int] = None, right_field_id: Optional[int] = None,
                        operator_id: Optional[int] = None) -> TableRelation:
        rel = self.db.get(TableRelation, relation_id)
        if not rel:
            raise BusinessException(ERR_NOT_FOUND, f"关联规则 {relation_id} 不存在")

        if relation_type is not None:
            rel.relation_type = relation_type.upper()
        if left_field_id is not None:
            rel.left_field_id = left_field_id
        if right_field_id is not None:
            rel.right_field_id = right_field_id
        rel.updated_at = datetime.utcnow()

        self.db.commit()
        self._log_info(f"更新关联规则 {relation_id}", operator_id)
        return rel

    def delete_relation(self, relation_id: int, operator_id: Optional[int] = None) -> None:
        rel = self.db.get(TableRelation, relation_id)
        if not rel:
            raise BusinessException(ERR_NOT_FOUND, f"关联规则 {relation_id} 不存在")
        self.db.delete(rel)
        self.db.commit()
        self._log_info(f"删除关联规则 {relation_id}", operator_id)
