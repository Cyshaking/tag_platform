"""
services/enum_service.py — 字段枚举配置
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.enum_config import FieldEnum
from app.db.models.metadata import MetaTable, MetaField
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_NOT_FOUND, ERR_VALIDATION


class EnumService(BaseService):
    MODULE = "enum"

    def list_enums(self, field_id: Optional[int] = None, table_id: Optional[int] = None) -> List[FieldEnum]:
        stmt = select(FieldEnum).order_by(FieldEnum.field_id, FieldEnum.ordinal)
        if field_id is not None:
            stmt = stmt.where(FieldEnum.field_id == field_id)
        if table_id is not None:
            stmt = stmt.where(FieldEnum.table_id == table_id)
        return self.db.execute(stmt).scalars().all()

    def save_field_enums(self, table_id: int, field_id: int,
                         enums: List[dict], operator_id: Optional[int] = None) -> List[FieldEnum]:
        """整体替换某字段下的所有枚举"""
        # 校验表和字段存在
        table = self.db.get(MetaTable, table_id)
        if not table:
            raise BusinessException(ERR_NOT_FOUND, f"表 {table_id} 不存在")
        field = self.db.get(MetaField, field_id)
        if not field or field.table_id != table_id:
            raise BusinessException(ERR_VALIDATION, f"字段 {field_id} 不属于表 {table_id}")

        # 检查同 field 下 enum_code 唯一
        seen_codes = set()
        for e in enums:
            code = e.get("enum_code", "")
            if not code:
                raise BusinessException(ERR_VALIDATION, "枚举编码不能为空")
            if code in seen_codes:
                raise BusinessException(ERR_VALIDATION, f"枚举编码 '{code}' 重复")
            seen_codes.add(code)

        # 先删旧枚举
        self.db.query(FieldEnum).filter(FieldEnum.field_id == field_id).delete()

        new_enums: List[FieldEnum] = []
        for i, e in enumerate(enums):
            obj = FieldEnum(
                table_id=table_id,
                field_id=field_id,
                enum_code=e["enum_code"],
                enum_label=e.get("enum_label") or e["enum_code"],
                ordinal=e.get("ordinal", i),
            )
            self.db.add(obj)
            new_enums.append(obj)

        self.db.commit()
        self._log_info(f"保存字段 {field_id} 的 {len(new_enums)} 个枚举", operator_id)
        return new_enums

    def delete_enum(self, enum_id: int, operator_id: Optional[int] = None) -> None:
        enum = self.db.get(FieldEnum, enum_id)
        if not enum:
            raise BusinessException(ERR_NOT_FOUND, f"枚举 {enum_id} 不存在")
        self.db.delete(enum)
        self.db.commit()
