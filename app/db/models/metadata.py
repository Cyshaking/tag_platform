"""
metadata.py — 元数据表（meta_tables + meta_fields）
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class MetaTable(Base):
    """表元信息"""
    __tablename__ = "meta_tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    serial_no = Column(String(20), unique=True, nullable=True, index=True)  # V1.4.3
    table_name = Column(String(128), unique=True, nullable=False, index=True)
    table_comment = Column(String(256))
    datasource_id = Column(Integer, ForeignKey("datasources.id", ondelete="SET NULL"))
    status = Column(String(32), default="pending", nullable=False)  # pending/approved/rejected
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    fields = relationship("MetaField", back_populates="meta_table", cascade="all, delete-orphan",
                          order_by="MetaField.ordinal_position")
    datasource = relationship("Datasource")
    creator = relationship("User", foreign_keys=[created_by])


class MetaField(Base):
    """字段元信息"""
    __tablename__ = "meta_fields"
    __table_args__ = (UniqueConstraint("table_id", "field_name", name="uq_table_field_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(128), nullable=False)
    field_type = Column(String(64), nullable=False)
    field_comment = Column(String(256))
    is_primary_key = Column(Boolean, default=False, nullable=False)
    is_nullable = Column(Boolean, default=True, nullable=False)
    ordinal_position = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    meta_table = relationship("MetaTable", back_populates="fields")
