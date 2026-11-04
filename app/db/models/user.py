"""
user.py — 用户、角色、用户-角色关联
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(64))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # 多对多用户-角色
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("Role", secondary="user_roles", viewonly=True)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(64), nullable=False)
    description = Column(String(256))
    permissions = Column(Text, nullable=False)  # JSON 字符串
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")
