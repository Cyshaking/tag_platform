"""
tag_task.py — 标签任务配置 + 执行记录
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class TagTask(Base):
    """标签任务配置"""
    __tablename__ = "tag_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(256), nullable=False)
    task_mode = Column(String(16), default="FIELD", nullable=False)  # V1.1: FIELD / SQL
    theme_id = Column(Integer, ForeignKey("business_themes.id", ondelete="SET NULL"), index=True)
    business_theme = Column(String(128), nullable=False)
    main_table_id = Column(Integer, ForeignKey("meta_tables.id", ondelete="RESTRICT"), nullable=False, index=True)
    main_field_id = Column(Integer, ForeignKey("meta_fields.id", ondelete="RESTRICT"), nullable=False)
    tag_value_code = Column(String(128), nullable=False)
    raw_sql = Column(Text)  # V1.1: SQL 直配模式原始/规范化 SQL
    field_config_json = Column(Text)  # V1.1: 字段配置模式快照
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_sql = Column(Text)  # 自动生成的 SQL 快照
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    main_table = relationship("MetaTable", foreign_keys=[main_table_id])
    main_field = relationship("MetaField", foreign_keys=[main_field_id])
    datasource = relationship("Datasource", back_populates="tag_tasks")
    records = relationship("TaskExecuteRecord", back_populates="tag_task", cascade="all, delete-orphan",
                           order_by="TaskExecuteRecord.created_at.desc()")


class TaskExecuteRecord(Base):
    """SQL 执行记录"""
    __tablename__ = "task_execute_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_task_id = Column(Integer, ForeignKey("tag_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="RESTRICT"), nullable=False, index=True)
    submitted_sql = Column(Text, nullable=False)
    ds_type = Column(String(16), nullable=False)  # sqlite / spark 快照
    external_task_id = Column(String(256))  # Spark 侧返回的异步任务 ID
    status = Column(String(32), default="pending", nullable=False)  # pending/running/success/failed
    execute_log = Column(Text)
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tag_task = relationship("TagTask", back_populates="records")
    datasource = relationship("Datasource")
