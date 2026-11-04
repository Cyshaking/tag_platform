"""
services/metadata_service.py — 元数据（表 + 字段），含 Excel 导入
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.metadata import MetaTable, MetaField
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_META_TABLE_DUP, ERR_META_NOT_FOUND, ERR_EXCEL_FORMAT, ERR_EXCEL_EMPTY
from app.utils import excel_parser


class MetadataService(BaseService):
    MODULE = "metadata"

    # ========== 表 CRUD ==========
    def list_tables(self, status: Optional[str] = None) -> List[MetaTable]:
        stmt = select(MetaTable).order_by(MetaTable.id)
        if status:
            stmt = stmt.where(MetaTable.status == status)
        return self.db.execute(stmt).scalars().all()

    def get_table(self, table_id: int) -> Optional[MetaTable]:
        return self.db.get(MetaTable, table_id)

    def create_table(self, table_name: str, table_comment: Optional[str],
                     fields: List[dict], datasource_id: Optional[int] = None,
                     created_by: Optional[int] = None) -> MetaTable:
        # 表名唯一
        existing = self.db.execute(select(MetaTable).where(MetaTable.table_name == table_name)).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_META_TABLE_DUP, f"表名 '{table_name}' 已存在")

        table = MetaTable(
            table_name=table_name,
            table_comment=table_comment,
            datasource_id=datasource_id,
            status="pending",
            created_by=created_by,
        )
        self.db.add(table)
        self.db.flush()

        # 字段
        for i, f in enumerate(fields):
            field = MetaField(
                table_id=table.id,
                field_name=f["field_name"],
                field_type=f["field_type"],
                field_comment=f.get("field_comment"),
                is_primary_key=f.get("is_primary_key", False),
                is_nullable=f.get("is_nullable", True),
                ordinal_position=f.get("ordinal_position", i + 1),
            )
            self.db.add(field)

        self.db.commit()
        self._log_info(f"创建表 {table_name}，{len(fields)} 个字段", created_by)
        return table

    def update_table(self, table_id: int, table_comment: Optional[str] = None,
                     datasource_id: Optional[int] = None,
                     fields: Optional[List[dict]] = None,
                     operator_id: Optional[int] = None) -> MetaTable:
        table = self.db.get(MetaTable, table_id)
        if not table:
            raise BusinessException(ERR_META_NOT_FOUND, f"表 {table_id} 不存在")

        if table_comment is not None:
            table.table_comment = table_comment
        if datasource_id is not None:
            table.datasource_id = datasource_id
        table.updated_at = datetime.utcnow()

        # 整体替换字段列表
        if fields is not None:
            # 先删旧字段
            self.db.query(MetaField).filter(MetaField.table_id == table_id).delete()
            for i, f in enumerate(fields):
                self.db.add(MetaField(
                    table_id=table.id,
                    field_name=f["field_name"],
                    field_type=f["field_type"],
                    field_comment=f.get("field_comment"),
                    is_primary_key=f.get("is_primary_key", False),
                    is_nullable=f.get("is_nullable", True),
                    ordinal_position=f.get("ordinal_position", i + 1),
                ))

        self.db.commit()
        self._log_info(f"更新表 {table.table_name}", operator_id)
        return table

    def delete_table(self, table_id: int, operator_id: Optional[int] = None) -> None:
        table = self.db.get(MetaTable, table_id)
        if not table:
            raise BusinessException(ERR_META_NOT_FOUND, f"表 {table_id} 不存在")
        self.db.delete(table)
        self.db.commit()
        self._log_info(f"删除表 {table.table_name}", operator_id)

    def set_table_status(self, table_id: int, status: str) -> MetaTable:
        """审批通过/驳回时更新状态"""
        table = self.db.get(MetaTable, table_id)
        if not table:
            raise BusinessException(ERR_META_NOT_FOUND, f"表 {table_id} 不存在")
        table.status = status
        table.updated_at = datetime.utcnow()
        self.db.commit()
        return table

    # ========== 字段 ==========
    def get_fields(self, table_id: int) -> List[MetaField]:
        stmt = select(MetaField).where(MetaField.table_id == table_id).order_by(MetaField.ordinal_position)
        return self.db.execute(stmt).scalars().all()

    # ========== Excel 导入 ==========
    def generate_template(self) -> bytes:
        """生成 Excel 模板字节流"""
        return excel_parser.generate_template_bytes()

    def import_excel(self, file_bytes: bytes, created_by: Optional[int] = None) -> MetaTable:
        """
        从 Excel 文件导入元数据
        解析失败抛 BusinessException（带详细错误列表）
        """
        try:
            table_info, fields = excel_parser.parse_metadata_excel(file_bytes)
        except excel_parser.ExcelParseError as e:
            raise BusinessException(ERR_EXCEL_FORMAT, f"Excel 解析失败:\n{e.errors}")

        if not table_info or not table_info.get("table_name"):
            raise BusinessException(ERR_EXCEL_EMPTY, "Excel 中未找到有效的表信息")
        if not fields:
            raise BusinessException(ERR_EXCEL_EMPTY, "Excel 中未找到有效的字段信息")

        # 检查表名是否已存在
        existing = self.db.execute(select(MetaTable).where(MetaTable.table_name == table_info["table_name"])).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_META_TABLE_DUP, f"表名 '{table_info['table_name']}' 已存在")

        return self.create_table(
            table_name=table_info["table_name"],
            table_comment=table_info.get("table_comment"),
            fields=fields,
            created_by=created_by,
        )
