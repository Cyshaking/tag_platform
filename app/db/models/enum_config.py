"""
enum_config.py — 字段枚举值
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class FieldEnum(Base):
    """字段-枚举值"""
    __tablename__ = "field_enums"
    __table_args__ = (UniqueConstraint("field_id", "enum_code", name="uq_field_enum_code"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id = Column(Integer, ForeignKey("meta_fields.id", ondelete="CASCADE"), nullable=False, index=True)
    enum_code = Column(String(64), nullable=False)
    enum_label = Column(String(128), nullable=False)
    ordinal = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    meta_table = relationship("MetaTable")
    meta_field = relationship("MetaField")
