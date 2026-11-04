"""
tests/integration/conftest.py — 集成测试专用 fixture

启动完整 FastAPI 应用但使用内存 SQLite（TestClient 模式）

关键要点：
1. 必须在 import app.main 之前替换 database 模块的全局 engine
   否则 main.py 模块级 app = create_app() 会触发 startup 事件
   用 config.yaml 的文件 DB 建表
2. SQLite :memory: 必须用 StaticPool 让所有 connection 共享同一内存库，
   否则 create_all 用 connection A 建表，get_db() 用 connection B 查，
   B 里是空的！
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool, event
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="function")
def client() -> TestClient:
    """
    每个测试启动独立应用 + 内存 DB
    """
    import app.db.database as db_mod

    # ====== 步骤 1：确保所有 models 已注册到 Base.metadata ======
    import app.db.models  # noqa: F401 — 触发 models/__init__.py

    # ====== 步骤 2：构造内存 DB engine（关键：StaticPool）======
    engine = create_engine(
        "sqlite://",  # :memory: 也可以，StaticPool 让它共享
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _r):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    # ====== 步骤 3：替换全局变量（在 import app.main 之前！）======
    db_mod._engine = engine
    db_mod._SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # ====== 步骤 4：建表 + 预置默认数据 ======
    from app.db.database import Base
    Base.metadata.create_all(engine)
    db_mod._ensure_default_data()

    # ====== 步骤 5：创建应用 ======
    from app.main import create_app
    app = create_app()

    with TestClient(app) as c:
        yield c

    # 清理
    engine.dispose()


@pytest.fixture
def auth_headers(client) -> dict:
    """拿到 admin token 的 Authorization header"""
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200 and r.json()["code"] == 0
    return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}


@pytest.fixture
def dap_headers(client) -> dict:
    """data_approver token"""
    r = client.post("/api/auth/login", json={"username": "dap", "password": "123456"})
    token = r.json()["data"]["access_token"]
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def tap_headers(client) -> dict:
    r = client.post("/api/auth/login", json={"username": "tap", "password": "123456"})
    return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}


@pytest.fixture
def bap_headers(client) -> dict:
    r = client.post("/api/auth/login", json={"username": "bap", "password": "123456"})
    return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
