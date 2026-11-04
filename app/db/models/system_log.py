"""
system_log.py — 系统日志
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class SystemLog(Base):
    """系统/业务日志"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(16), nullable=False)  # DEBUG/INFO/WARN/ERROR
    module = Column(String(64))
    message = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User")
