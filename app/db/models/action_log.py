"""
action_log.py — V1.6 新增：用户操作日志（结构化审计）
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class ActionLog(Base):
    """用户操作日志：谁在什么时间对哪个模块的哪个对象做了什么"""
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username = Column(String(64))             # 冗余：查询无需 JOIN users
    module = Column(String(64), index=True)   # metadata / theme / tag_task / approval / ...
    action = Column(String(32), index=True)   # CREATE / UPDATE / DELETE / SUBMIT_APPROVAL / APPROVE / REJECT / EXECUTE / LOGIN / SWITCH / TEST
    target_type = Column(String(32), index=True)  # META_TABLE / TAG_TASK / APPROVAL_TICKET / ...
    target_id = Column(Integer, index=True)
    target_name = Column(String(256))         # 对象名（表名/任务名/主题编码...）
    detail = Column(Text)                     # 可选 JSON 快照
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User")
