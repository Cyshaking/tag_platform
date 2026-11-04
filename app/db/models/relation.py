"""
relation.py — 表关联关系
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class TableRelation(Base):
    """表关联规则"""
    __tablename__ = "table_relations"
    __table_args__ = (
        UniqueConstraint("left_table_id", "left_field_id", "right_table_id", "right_field_id",
                         name="uq_relation_pair"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    left_table_id = Column(Integer, ForeignKey("meta_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    left_field_id = Column(Integer, ForeignKey("meta_fields.id", ondelete="CASCADE"), nullable=False)
    right_table_id = Column(Integer, ForeignKey("meta_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    right_field_id = Column(Integer, ForeignKey("meta_fields.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(16), default="INNER", nullable=False)  # INNER/LEFT/RIGHT
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    left_table = relationship("MetaTable", foreign_keys=[left_table_id])
    right_table = relationship("MetaTable", foreign_keys=[right_table_id])
    left_field = relationship("MetaField", foreign_keys=[left_field_id])
    right_field = relationship("MetaField", foreign_keys=[right_field_id])
