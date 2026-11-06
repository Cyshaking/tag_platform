"""
datasource.py — 数据源配置
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Datasource(Base):
    """数据源（sqlite / spark）"""
    __tablename__ = "datasources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    serial_no = Column(String(20), unique=True, nullable=True, index=True)  # V1.4.3
    name = Column(String(128), unique=True, nullable=False, index=True)
    ds_type = Column(String(16), nullable=False)  # sqlite / spark
    config_json = Column(Text, nullable=False)  # 连接配置 JSON
    is_enabled = Column(Boolean, default=True, nullable=False)
    remark = Column(String(256))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    tag_tasks = relationship("TagTask", back_populates="datasource")
