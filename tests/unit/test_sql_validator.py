"""
tests/unit/test_sql_validator.py — SQL 直配校验（V1.1 #2）
覆盖：只读静态校验、注释剥离、sqlite EXPLAIN 校验、Spark Mock 校验、禁用数据源。
"""
import json
import sqlite3

import pytest

from app.db.models.datasource import Datasource
from app.services.sql_validator import SQLValidator
from app.utils.exceptions import BusinessException


@pytest.fixture
def validator(db):
    return SQLValidator(db)


@pytest.fixture
def sqlite_datasource(db, tmp_path):
    """真实文件库 + 一张演示表，确保 EXPLAIN 能校验表/字段"""
    db_path = str(tmp_path / "validator_demo.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    ds = Datasource(
        name="validator_sqlite", ds_type="sqlite",
        config_json=json.dumps({"db_path": db_path}, ensure_ascii=False),
        is_enabled=True,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


@pytest.fixture
def spark_datasource(db):
    ds = Datasource(
        name="validator_spark", ds_type="spark",
        config_json=json.dumps({"mock": True}, ensure_ascii=False),
        is_enabled=True,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


class TestStaticValidation:

    def test_select_allowed(self, validator):
        ok, msg, normalized = validator.validate_text("SELECT id FROM demo")
        assert ok is True
        assert normalized == "SELECT id FROM demo"

    def test_with_allowed(self, validator):
        sql = "WITH t AS (SELECT 1 AS id) SELECT id FROM t"
        ok, _, _ = validator.validate_text(sql)
        assert ok is True

    def test_trailing_semicolon_removed(self, validator):
        ok, _, normalized = validator.validate_text("SELECT id FROM demo;")
        assert ok is True and normalized.endswith("demo")

    def test_reject_non_select(self, validator):
        ok, msg, _ = validator.validate_text("UPDATE demo SET name = 'x'")
        assert ok is False

    def test_reject_write_keyword(self, validator):
        ok, msg, _ = validator.validate_text("SELECT * FROM demo WHERE 1=1 DROP TABLE demo")
        assert ok is False
        assert "DROP" in msg

    def test_reject_multi_statement(self, validator):
        ok, msg, _ = validator.validate_text("SELECT 1; SELECT 2")
        assert ok is False
        assert "多语句" in msg

    def test_reject_empty(self, validator):
        ok, _, _ = validator.validate_text("   ")
        assert ok is False

    def test_comments_stripped_before_keyword_check(self, validator):
        sql = "/* 说明注释 */ SELECT id -- 行注释\nFROM demo"
        ok, _, normalized = validator.validate_text(sql)
        assert ok is True
        assert "说明注释" not in normalized and "行注释" not in normalized


class TestEngineValidation:

    def test_sqlite_valid_sql(self, validator, sqlite_datasource):
        r = validator.validate("SELECT id, name FROM demo", sqlite_datasource.id)
        assert r["valid"] is True
        assert r["normalized_sql"] == "SELECT id, name FROM demo"

    def test_sqlite_unknown_column_invalid(self, validator, sqlite_datasource):
        r = validator.validate("SELECT missing_col FROM demo", sqlite_datasource.id)
        assert r["valid"] is False
        assert "校验失败" in r["message"]

    def test_spark_mock_always_valid(self, validator, spark_datasource):
        r = validator.validate("SELECT policy_id FROM policy", spark_datasource.id)
        assert r["valid"] is True
        assert "Mock" in r["message"]

    def test_disabled_datasource_rejected(self, validator, sqlite_datasource):
        sqlite_datasource.is_enabled = False
        validator.db.commit()
        with pytest.raises(BusinessException):
            validator.validate("SELECT id FROM demo", sqlite_datasource.id)

    def test_unknown_datasource_rejected(self, validator):
        with pytest.raises(BusinessException):
            validator.validate("SELECT 1", 999999)
