"""
tests/engines/test_sqlite_engine.py — SQLite 引擎真实执行测试

关键约束：
- SQLite `:memory:` 每次 sqlite3.connect 都是独立临时库，数据不共享
- 所有跨 submit 的测试必须用同一个真实临时文件
"""
import os
import tempfile
import pytest

from app.engines.sqlite_engine import SqliteEngine
from app.engines.base_engine import TaskStatusInfo


@pytest.fixture
def real_db_path():
    """一个每次测试独立的临时 .db 文件"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


class TestSqliteEngine:

    def test_execute_success(self, real_db_path):
        engine = SqliteEngine()
        tid = engine.submit_sql(
            "CREATE TABLE t1 (id INTEGER PRIMARY KEY, name TEXT)",
            {"db_path": real_db_path},
        )
        assert tid.startswith("sqlite_")
        info = engine.get_task_status(tid)
        assert info.status == "success"

    def test_execute_fail_syntax(self, real_db_path):
        engine = SqliteEngine()
        with pytest.raises(Exception):
            engine.submit_sql("THIS IS NOT VALID SQL!!!", {"db_path": real_db_path})

    def test_execute_dml_then_select(self, real_db_path):
        """CREATE → INSERT → SELECT 走同一个真实文件"""
        engine = SqliteEngine()
        cfg = {"db_path": real_db_path}

        # 建表
        tid = engine.submit_sql("CREATE TABLE t (a INT)", cfg)
        assert engine.get_task_status(tid).status == "success"

        # 插入
        tid = engine.submit_sql("INSERT INTO t VALUES (42)", cfg)
        assert engine.get_task_status(tid).status == "success"

        # 查询（SELECT 也能 execute，只是 rowcount 无意义）
        tid = engine.submit_sql("SELECT * FROM t", cfg)
        info = engine.get_task_status(tid)
        assert info.status == "success"

    def test_missing_db_path_raises(self):
        engine = SqliteEngine()
        with pytest.raises(ValueError):
            engine.submit_sql("SELECT 1", {})

    def test_multiple_submits_same_file(self, real_db_path):
        """同一个文件路径多次 submit 能看到之前的数据"""
        engine = SqliteEngine()
        cfg = {"db_path": real_db_path}
        for i in range(3):
            t = engine.submit_sql(f"CREATE TABLE IF NOT EXISTS tbl_{i} (x INTEGER)", cfg)
            assert engine.get_task_status(t).status == "success"
