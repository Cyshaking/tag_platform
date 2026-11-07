"""
tests/conftest.py — pytest 全局 fixture
核心：内存 SQLite + 预置数据 + 测试用户
"""
import json
import sys
import os
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# 把项目根加到 sys.path
_PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT))

from app.db.database import Base
from app.db.models.user import User, Role, UserRole
from app.db.models.metadata import MetaTable, MetaField
from app.db.models.datasource import Datasource
from app.db.models.tag_task import TagTask
from app.utils.security import hash_password


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """
    每个测试独立的内存 SQLite Session（function scope）
    自动建表 + 预置默认 admin/roles
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _r):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()

    # 预置角色
    roles_data = [
        ("admin", "系统管理员", ["*"]),
        ("data_approver", "数据审批人", ["approval:data_node"]),
        ("tech_approver", "技术审批人", ["approval:tech_node"]),
        ("biz_approver", "业务审批人", ["approval:biz_node"]),
        ("user", "普通用户", ["metadata:view"]),
    ]
    for code, name, perms in roles_data:
        session.add(Role(code=code, name=name, description=f"预置{name}",
                         permissions=json.dumps(perms, ensure_ascii=False)))
    session.commit()

    # 预置默认 admin
    admin = User(
        username="admin", password_hash=hash_password("admin123"),
        display_name="Admin", is_active=True,
    )
    session.add(admin)
    session.flush()
    admin_role = session.execute(
        __import__('sqlalchemy').select(Role).where(Role.code == "admin")
    ).scalar_one_or_none()
    if admin_role:
        session.add(UserRole(user_id=admin.id, role_id=admin_role.id))

    # 预置额外用户（带审批角色）
    for code, uname in [("data_approver", "dap"), ("tech_approver", "tap"), ("biz_approver", "bap"), ("user", "normal")]:
        u = User(username=uname, password_hash=hash_password("123456"),
                 display_name=uname, is_active=True)
        session.add(u); session.flush()
        r = session.execute(__import__('sqlalchemy').select(Role).where(Role.code == code)).scalar_one_or_none()
        if r: session.add(UserRole(user_id=u.id, role_id=r.id))

    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_table(db: Session) -> MetaTable:
    """预置一张有主键的表 + 两个字段"""
    t = MetaTable(table_name="sample_order", table_comment="示例订单表",
                  status="approved", created_by=1)
    db.add(t); db.flush()
    db.add(MetaField(table_id=t.id, field_name="order_id", field_type="BIGINT",
                     is_primary_key=True, is_nullable=False, ordinal_position=1))
    db.add(MetaField(table_id=t.id, field_name="user_id", field_type="BIGINT",
                     is_primary_key=False, is_nullable=True, ordinal_position=2))
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture
def sample_table2(db: Session) -> MetaTable:
    """第二张示例表（用于测试 JOIN）"""
    t = MetaTable(table_name="sample_user", table_comment="示例用户表",
                  status="approved", created_by=1)
    db.add(t); db.flush()
    db.add(MetaField(table_id=t.id, field_name="user_id", field_type="BIGINT",
                     is_primary_key=True, is_nullable=False, ordinal_position=1))
    db.add(MetaField(table_id=t.id, field_name="user_name", field_type="VARCHAR(64)",
                     is_primary_key=False, is_nullable=True, ordinal_position=2))
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture
def sqlite_ds(db: Session) -> Datasource:
    """预置一个内存 sqlite 数据源"""
    ds = Datasource(
        name="test_sqlite", ds_type="sqlite",
        config_json=json.dumps({"db_path": ":memory:"}, ensure_ascii=False),
        is_enabled=True,
    )
    db.add(ds); db.commit(); db.refresh(ds)
    return ds


@pytest.fixture
def sample_tag_task(db: Session, sample_table: MetaTable, sqlite_ds: Datasource) -> TagTask:
    """预置一个可提交审批的标签任务（SQL 直配模式，引用 sample_table 的主键）"""
    pk_field = None
    for f in sample_table.fields:
        if f.is_primary_key:
            pk_field = f
            break
    if pk_field is None:
        # 兜底：用第一个字段
        pk_field = sample_table.fields[0]

    task = TagTask(
        task_name="test_tag_task",
        task_mode="SQL",
        business_theme="测试主题",
        main_table_id=sample_table.id,
        main_field_id=pk_field.id,
        tag_value_code="TAG_TEST",
        raw_sql=f"SELECT {pk_field.field_name} FROM {sample_table.table_name}",
        datasource_id=sqlite_ds.id,
        generated_sql=f"SELECT {pk_field.field_name} FROM {sample_table.table_name}",
        status="pending",
        created_by=1,
    )
    db.add(task); db.commit(); db.refresh(task)
    return task
