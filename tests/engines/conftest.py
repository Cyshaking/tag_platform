"""
tests/engines/conftest.py — 引擎测试共享 fixture

为 SparkThriftEngine 测试预注入一个假的 jaydebeapi 模块，
避免 monkeypatch 偶发时机问题。
"""
import sys
import types
import pytest


class _MockCursor:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    def execute(self, sql):
        if self.should_fail:
            raise RuntimeError("Thrift JDBC connection refused")
        return []

    def fetchone(self): return None
    def fetchall(self): return []
    def close(self): pass


class _MockConn:
    def __init__(self, fail=False):
        self.fail = fail

    def cursor(self):
        return _MockCursor(self.fail)

    def close(self): pass


# 在 import 任何 jaydebeapi 相关代码之前，把假模块塞进 sys.modules
if "jaydebeapi" not in sys.modules:
    _fake = types.ModuleType("jaydebeapi")

    def _default_connect(*a, **kw):
        return _MockConn(fail=False)
    _fake.connect = _default_connect

    sys.modules["jaydebeapi"] = _fake


@pytest.fixture
def spark_mock_success(monkeypatch):
    """返回一个 mock connect，连接成功"""
    import jaydebeapi

    def _ok(*a, **kw):
        return _MockConn(fail=False)
    monkeypatch.setattr(jaydebeapi, "connect", _ok)


@pytest.fixture
def spark_mock_fail(monkeypatch):
    """返回一个 mock connect，连接失败"""
    import jaydebeapi

    def _fail(*a, **kw):
        raise RuntimeError("Thrift JDBC connection refused")
    monkeypatch.setattr(jaydebeapi, "connect", _fail)
