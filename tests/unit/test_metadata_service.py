"""
tests/unit/test_metadata_service.py — 元数据 service 测试
"""
import io
import pytest
from sqlalchemy.orm import Session
from openpyxl import Workbook

from app.db.models.metadata import MetaTable, MetaField
from app.services.metadata_service import MetadataService
from app.utils.exceptions import BusinessException, ERR_META_TABLE_DUP, ERR_META_NOT_FOUND, ERR_EXCEL_FORMAT


class TestMetadataService:

    def test_create_table_ok(self, db: Session):
        svc = MetadataService(db)
        t = svc.create_table(
            table_name="users_t", table_comment="用户表",
            fields=[
                {"field_name": "id", "field_type": "INT", "is_primary_key": True, "is_nullable": False, "ordinal_position": 1},
                {"field_name": "name", "field_type": "VARCHAR(32)", "ordinal_position": 2},
            ],
            created_by=1,
        )
        assert t.id is not None
        assert t.table_name == "users_t"
        assert len(t.fields) == 2
        assert t.fields[0].is_primary_key is True
        assert t.status == "pending"

    def test_create_dup_table_rejected(self, db: Session, sample_table):
        svc = MetadataService(db)
        with pytest.raises(BusinessException) as exc:
            svc.create_table(table_name=sample_table.table_name, table_comment="", fields=[])
        assert exc.value.code == ERR_META_TABLE_DUP

    def test_delete_table_cascade(self, db: Session, sample_table):
        svc = MetadataService(db)
        tid = sample_table.id
        svc.delete_table(tid, operator_id=1)
        assert svc.get_table(tid) is None
        remaining = db.query(MetaField).filter(MetaField.table_id == tid).count()
        assert remaining == 0

    def test_set_table_status(self, db: Session, sample_table):
        svc = MetadataService(db)
        t = svc.set_table_status(sample_table.id, "approved")
        assert t.status == "approved"

    # ========== Excel 导入 ==========
    def _make_excel_bytes(self, rows_table, rows_field) -> bytes:
        wb = Workbook()
        ws1 = wb.active; ws1.title = "表信息"
        ws1.append(["表名", "表中文名", "备注"])
        for r in rows_table: ws1.append(r)
        ws2 = wb.create_sheet("字段信息")
        ws2.append(["字段名", "字段类型", "字段中文名", "是否主键(Y/N)", "是否可空(Y/N)", "顺序"])
        for r in rows_field: ws2.append(r)
        buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf.read()

    def test_excel_import_ok(self, db: Session):
        svc = MetadataService(db)
        data = self._make_excel_bytes(
            [["orders", "订单表", "test"]],
            [
                ["order_id", "BIGINT", "订单ID", "Y", "N", 1],
                ["user_id", "BIGINT", "用户ID", "N", "Y", 2],
                ["amount", "DECIMAL", "金额", "N", "Y", 3],
            ],
        )
        t = svc.import_excel(data, created_by=1)
        assert t.table_name == "orders"
        assert len(t.fields) == 3
        pk_field = [f for f in t.fields if f.is_primary_key][0]
        assert pk_field.field_name == "order_id"

    def test_excel_missing_pk_rejected(self, db: Session):
        svc = MetadataService(db)
        data = self._make_excel_bytes(
            [["bad_table", "无PK的表", ""]],
            [["f1", "INT", "", "N", "Y", 1]],
        )
        with pytest.raises(BusinessException):
            svc.import_excel(data)

    def test_excel_empty_file_rejected(self, db: Session):
        svc = MetadataService(db)
        with pytest.raises(BusinessException):
            svc.import_excel(b"")

    def test_template_download(self, db: Session):
        svc = MetadataService(db)
        bytes_data = svc.generate_template()
        assert isinstance(bytes_data, bytes)
        assert len(bytes_data) > 0
        # 是 openpyxl 生成的 zip/xlsx 格式
        assert bytes_data[:2] == b"PK"
