"""
tests/engines/test_spark_engine_mock.py — SparkThriftEngine mock 测试

不依赖真实 Spark 集群，通过 tests/engines/conftest.py 预注入假 jaydebeapi 模块。
"""
import pytest


def test_submit_success(spark_mock_success):
    """Spark 提交成功 → 返回 spark_ 前缀 task_id"""
    from app.engines.spark_thrift_engine import SparkThriftEngine
    engine = SparkThriftEngine()
    tid = engine.submit_sql("SELECT 1", {"thrift_url": "jdbc:hive2://x"})
    assert tid.startswith("spark_")

    info = engine.get_task_status(tid)
    assert info.status == "running"


def test_submit_connection_failure(spark_mock_fail):
    """Spark 连接失败 → 抛异常"""
    from app.engines.spark_thrift_engine import SparkThriftEngine
    engine = SparkThriftEngine()
    with pytest.raises(RuntimeError):
        engine.submit_sql("SELECT 1", {"thrift_url": "jdbc:hive2://x"})


def test_get_task_status_cached():
    """未找到 task → pending"""
    from app.engines.spark_thrift_engine import SparkThriftEngine
    engine = SparkThriftEngine()
    info = engine.get_task_status("nonexistent")
    assert info.status == "pending"


def test_engine_type_constant():
    from app.engines.spark_thrift_engine import SparkThriftEngine
    from app.engines.sqlite_engine import SqliteEngine
    assert SparkThriftEngine.ENGINE_TYPE == "spark"
    assert SqliteEngine.ENGINE_TYPE == "sqlite"
