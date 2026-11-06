"""
business_theme.py — 业务主题表（V1.1 新增）

业务主题是标签体系的顶层业务域，必须且只能绑定一张元数据表作为主题表（主表）。
标签任务的最终 SQL 一律以主题表为 FROM 主表。
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class BusinessTheme(Base):
    """业务主题"""
    __tablename__ = "business_themes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    serial_no = Column(String(20), unique=True, nullable=True, index=True)  # V1.4.3
    theme_code = Column(String(64), unique=True, nullable=False, index=True)
    theme_name = Column(String(128), nullable=False)
    main_table_id = Column(Integer, ForeignKey("meta_tables.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    description = Column(String(256))
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    main_table = relationship("MetaTable")
