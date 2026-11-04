"""
database.py — SQLAlchemy engine / Session / Base / init_db
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# SQLAlchemy 2.x 声明式基类
class Base(DeclarativeBase):
    pass


def _make_sqlite_engine(url: str) -> Engine:
    """创建 SQLite 引擎，启用 WAL + 解除跨线程限制"""
    # 确保 DB 文件父目录存在
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///"):]
        if db_path and not db_path.startswith(":"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        url,
        echo=False,
        # SQLite 必须解除同线程检查
        connect_args={"check_same_thread": False},
        # SQLite 用 StaticPool 让多线程共享同一连接（作业场景足够）
        pool_pre_ping=True,
    )

    # 每次新建连接时设置 WAL 模式
    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    return engine


# 全局引擎 + Session 工厂（延迟初始化）
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        from app.config import db as db_cfg
        _engine = _make_sqlite_engine(db_cfg.sqlite_url())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def init_db() -> None:
    """自动建表 + 增量迁移 + 初始化默认数据 + 保险演示种子数据"""
    from app.db.models import (  # noqa: F401  确保所有 model 被 import 进 Base.metadata
        user, metadata, relation, enum_config,
        approval, datasource, tag_task, system_log, business_theme,
    )
    engine = get_engine()
    Base.metadata.create_all(engine)

    # V1.1：为既有 tag_tasks 表补齐新增列（幂等）
    _migrate_additive_columns()

    # 初始化默认数据（admin 用户 + 预置角色）
    _ensure_default_data()

    # V1.1：幂等写入保险行业演示种子数据
    from app.db.seed_data import init_insurance_seed_data
    try:
        init_insurance_seed_data()
    except Exception as exc:  # 种子失败不应阻断应用启动
        import logging
        logging.getLogger(__name__).warning("保险演示种子数据初始化失败: %s", exc)


def _migrate_additive_columns() -> None:
    """
    V1.1 增量迁移：仅新增列，不重建表、不改旧字段。

    读取 PRAGMA table_info(tag_tasks)，缺失列则 ALTER TABLE ADD COLUMN。
    幂等：列已存在则跳过，可重复执行。
    """
    additive_columns = [
        ("task_mode", "VARCHAR(16) NOT NULL DEFAULT 'FIELD'"),
        ("theme_id", "INTEGER"),
        ("raw_sql", "TEXT"),
        ("field_config_json", "TEXT"),
    ]
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(tag_tasks)").fetchall()
        if not rows:
            return  # 表由 create_all 新建，无需迁移
        existing = {row[1] for row in rows}
        for column_name, ddl in additive_columns:
            if column_name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE tag_tasks ADD COLUMN {column_name} {ddl}")



def _ensure_default_data() -> None:
    """检查并创建默认 admin 用户 + 预置角色 + 测试审批用户"""
    from sqlalchemy import select

    factory = get_session_factory()
    with factory() as session:
        # ========== 默认角色 ==========
        from app.config import roles as roles_cfg
        from app.db.models.user import Role
        import json

        for r in roles_cfg.roles:
            stmt = select(Role).where(Role.code == r["code"])
            if not session.execute(stmt).scalar_one_or_none():
                role = Role(
                    code=r["code"],
                    name=r["name"],
                    description=f"预置角色: {r['name']}",
                    permissions=json.dumps(r["permissions"], ensure_ascii=False),
                )
                session.add(role)

        # ========== 默认 admin ==========
        from app.config import admin as admin_cfg
        from app.db.models.user import User, UserRole
        from app.utils.security import hash_password

        # 用 username 直接查（避免 joined eager load 问题）
        user = session.execute(
            select(User).where(User.username == admin_cfg.username)
        ).unique().scalar_one_or_none()
        if not user:
            user = User(
                username=admin_cfg.username,
                password_hash=hash_password(admin_cfg.password),
                display_name=admin_cfg.display_name,
                is_active=True,
            )
            session.add(user)
            session.flush()  # 拿到 user.id

            # admin 默认拥有 admin 角色
            admin_role = session.execute(
                select(Role).where(Role.code == "admin")
            ).scalar_one_or_none()
            if admin_role:
                session.add(UserRole(user_id=user.id, role_id=admin_role.id))

        # ========== 测试审批用户（作业 demo 用）==========
        # 固定密码 123456
        _demo_users = [
            ("dap", "data_approver", "数据审批人"),
            ("tap", "tech_approver", "技术审批人"),
            ("bap", "biz_approver", "业务审批人"),
            ("normal", "user", "普通用户"),
        ]
        for uname, role_code, dname in _demo_users:
            existing = session.execute(
                select(User).where(User.username == uname)
            ).unique().scalar_one_or_none()
            if not existing:
                u = User(
                    username=uname,
                    password_hash=hash_password("123456"),
                    display_name=dname,
                    is_active=True,
                )
                session.add(u)
                session.flush()
                r = session.execute(
                    select(Role).where(Role.code == role_code)
                ).scalar_one_or_none()
                if r:
                    session.add(UserRole(user_id=u.id, role_id=r.id))

        session.commit()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入：每次请求获取一个 Session"""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
