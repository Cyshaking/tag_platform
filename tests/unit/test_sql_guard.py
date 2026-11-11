"""
tests/unit/test_sql_guard.py — V1.7 P0：SQL 只读校验与 SQLite 路径白名单
"""
import pytest

from app.utils.sql_guard import check_readonly_sql, ensure_db_path_allowed


class TestCheckReadonlySQL:
    def test_select_allowed(self):
        ok, msg, normalized = check_readonly_sql("SELECT id FROM t WHERE a = 1")
        assert ok is True
        assert msg == "校验通过"
        assert normalized == "SELECT id FROM t WHERE a = 1"

    def test_with_cte_allowed(self):
        ok, _, _ = check_readonly_sql("WITH c AS (SELECT 1 AS x) SELECT x FROM c")
        assert ok is True

    def test_trailing_semicolon_stripped(self):
        ok, _, normalized = check_readonly_sql("SELECT 1;")
        assert ok is True
        assert normalized == "SELECT 1"

    def test_comment_ignored(self):
        ok, _, _ = check_readonly_sql("-- 注释\nSELECT 1 /* 块注释 */")
        assert ok is True

    @pytest.mark.parametrize("sql", [
        "DELETE FROM t",
        "UPDATE t SET a = 1",
        "INSERT INTO t VALUES (1)",
        "DROP TABLE t",
        "CREATE TABLE t (id INT)",
        "PRAGMA table_info(t)",
        "ATTACH DATABASE 'x.db' AS x",
    ])
    def test_write_statements_rejected(self, sql):
        ok, msg, _ = check_readonly_sql(sql)
        assert ok is False

    def test_multi_statement_rejected(self):
        ok, msg, _ = check_readonly_sql("SELECT 1; SELECT 2")
        assert ok is False
        assert "多语句" in msg

    def test_empty_rejected(self):
        ok, msg, _ = check_readonly_sql("   ")
        assert ok is False

    def test_non_select_head_rejected(self):
        ok, msg, _ = check_readonly_sql("EXPLAIN SELECT 1")
        assert ok is False


class TestEnsureDbPathAllowed:
    def test_memory_allowed(self):
        assert ensure_db_path_allowed(":memory:") == ":memory:"

    def test_demo_data_dir_allowed(self):
        result = ensure_db_path_allowed("data/insurance_demo.db")
        assert result.endswith("insurance_demo.db")
        assert "data" in result

    def test_platform_db_rejected(self):
        with pytest.raises(ValueError, match="平台主库"):
            ensure_db_path_allowed("data/tag_platform.db")

    @pytest.mark.parametrize("path", [
        "/tmp/evil.db",
        "../outside.db",
        "C:/Windows/system.db",
    ])
    def test_outside_data_dir_rejected(self, path, tmp_path=None):
        with pytest.raises(ValueError):
            ensure_db_path_allowed(path)

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            ensure_db_path_allowed("")
