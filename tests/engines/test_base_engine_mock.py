"""
tests/engines/test_base_engine_mock.py — BaseEngine 抽象基类验证
"""
import pytest
from app.engines.base_engine import BaseEngine, TaskStatusInfo


class _MockImpl(BaseEngine):
    """用于验证抽象基类接口的测试子类"""
    ENGINE_TYPE = "mock"

    def __init__(self):
        self._counter = 0
        self._last_task = None

    def submit_sql(self, sql, datasource_config):
        self._counter += 1
        self._last_task = f"task_{self._counter}"
        return self._last_task

    def get_task_status(self, task_id, datasource_config=None):
        return TaskStatusInfo(status=self.STATUS_SUCCESS, log=f"ok: {task_id}", duration_ms=42)


class TestBaseEngine:

    def test_abc_not_directly_instantiable(self):
        """抽象基类不能直接实例化"""
        with pytest.raises(TypeError):
            BaseEngine()

    def test_subclass_implements_interface(self):
        engine = _MockImpl()
        tid = engine.submit_sql("SELECT 1", {"k": "v"})
        assert tid == "task_1"

        info = engine.get_task_status(tid)
        assert info.status == "success"
        assert info.duration_ms == 42

    def test_status_constants(self):
        assert BaseEngine.STATUS_PENDING == "pending"
        assert BaseEngine.STATUS_RUNNING == "running"
        assert BaseEngine.STATUS_SUCCESS == "success"
        assert BaseEngine.STATUS_FAILED == "failed"
