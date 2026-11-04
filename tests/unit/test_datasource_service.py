"""
tests/unit/test_datasource_service.py — 数据源 service 测试（含测试连接 + 密码掩码）
"""
import json
import pytest
from sqlalchemy.orm import Session

from app.db.models.datasource import Datasource
from app.services.datasource_service import DatasourceService
from app.utils.exceptions import BusinessException, ERR_DUP_DATASOURCE


class TestDatasourceService:

    def test_create_sqlite(self, db: Session):
        svc = DatasourceService(db)
        ds = svc.create_datasource(
            name="my_sqlite", ds_type="sqlite",
            config={"db_path": ":memory:"}, is_enabled=True, operator_id=1,
        )
        assert ds.id is not None
        assert ds.ds_type == "sqlite"
        assert json.loads(ds.config_json)["db_path"] == ":memory:"

    def test_create_spark_password_stored(self, db: Session):
        svc = DatasourceService(db)
        ds = svc.create_datasource(
            name="my_spark", ds_type="spark",
            config={"thrift_url": "jdbc:hive2://host:10015", "password": "supersecret"},
            operator_id=1,
        )
        raw = json.loads(ds.config_json)
        # 真实密码在 config_json 里（后端内部使用）
        assert raw["password"] == "supersecret"

        # 序列化输出做掩码
        out = svc.serialize(ds)
        assert out["config"]["password"] == "******"

    def test_name_unique(self, db: Session):
        svc = DatasourceService(db)
        svc.create_datasource(name="dup", ds_type="sqlite", config={"db_path": ":memory:"})
        with pytest.raises(BusinessException) as exc:
            svc.create_datasource(name="dup", ds_type="sqlite", config={"db_path": "/tmp/a.db"})
        assert exc.value.code == ERR_DUP_DATASOURCE

    def test_toggle_enabled(self, db: Session, sqlite_ds):
        svc = DatasourceService(db)
        svc.toggle_enabled(sqlite_ds.id, False)
        db.refresh(sqlite_ds)
        assert sqlite_ds.is_enabled is False

    def test_delete_with_tag_task_ref_rejected(self, db: Session, sqlite_ds):
        """被标签任务绑定后删除被拒绝"""
        from app.db.models.metadata import MetaTable, MetaField
        from app.db.models.tag_task import TagTask
        from app.services.sql_generator import SQLGenerator

        t = MetaTable(table_name="t1", status="approved")
        db.add(t); db.flush()
        db.add(MetaField(table_id=t.id, field_name="id", field_type="INT", is_primary_key=True))
        db.commit()

        gen = SQLGenerator(db)
        sql = gen.generate(t.id, 1, "x")
        db.add(TagTask(task_name="task1", business_theme="b", main_table_id=t.id,
                       main_field_id=1, tag_value_code="x", datasource_id=sqlite_ds.id,
                       generated_sql=sql))
        db.commit()

        svc = DatasourceService(db)
        with pytest.raises(BusinessException):
            svc.delete_datasource(sqlite_ds.id)

    def test_test_connection_sqlite_ok(self, db: Session):
        svc = DatasourceService(db)
        result = svc.test_connection("sqlite", {"db_path": ":memory:"})
        assert result["success"] is True
        assert result["latency_ms"] is not None

    def test_test_connection_sqlite_fail(self, db: Session):
        svc = DatasourceService(db)
        result = svc.test_connection("sqlite", {"db_path": ""})
        # _test_sqlite 里 `not ""` → True → raise ValueError → success=False
        assert result["success"] is False
        assert result["message"]  # 有错误描述
