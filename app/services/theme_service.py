"""
services/theme_service.py — 业务主题（V1.1 新增）

职责：主题 CRUD、主题表绑定校验、被标签任务引用保护。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.business_theme import BusinessTheme
from app.db.models.metadata import MetaTable
from app.db.models.tag_task import TagTask
from app.services.base import BaseService
from app.utils.exceptions import (
    BusinessException, ERR_VALIDATION, ERR_NOT_FOUND, ERR_BAD_REQUEST,
    ERR_META_NOT_FOUND,
)


class ThemeService(BaseService):
    MODULE = "theme"

    # ========== 查询 ==========
    def list_themes(self) -> List[BusinessTheme]:
        return self.db.execute(
            select(BusinessTheme).order_by(BusinessTheme.id)
        ).scalars().all()

    def get_theme(self, theme_id: int) -> Optional[BusinessTheme]:
        return self.db.get(BusinessTheme, theme_id)

    def get_theme_table(self, theme_id: int) -> MetaTable:
        """主题绑定的主题表（含字段），供标签任务页调用"""
        theme = self.db.get(BusinessTheme, theme_id)
        if not theme:
            raise BusinessException(ERR_NOT_FOUND, f"业务主题 {theme_id} 不存在")
        table = self.db.get(MetaTable, theme.main_table_id)
        if not table:
            raise BusinessException(ERR_META_NOT_FOUND, "主题表不存在")
        return table

    def count_task_refs(self, theme_id: int) -> int:
        return int(self.db.execute(
            select(func.count(TagTask.id)).where(TagTask.theme_id == theme_id)
        ).scalar_one())

    # ========== 新增 ==========
    def create_theme(self, theme_code: str, theme_name: str, main_table_id: int,
                     description: Optional[str] = None, is_enabled: bool = True,
                     operator_id: Optional[int] = None) -> BusinessTheme:
        existing = self.db.execute(
            select(BusinessTheme).where(BusinessTheme.theme_code == theme_code)
        ).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_VALIDATION, f"主题编码 '{theme_code}' 已存在")

        self._validate_main_table(main_table_id)

        theme = BusinessTheme(
            theme_code=theme_code,
            theme_name=theme_name,
            main_table_id=main_table_id,
            description=description,
            is_enabled=is_enabled,
        )
        theme.serial_no = self._gen_serial_no(BusinessTheme, "THE")  # V1.4.3
        self.db.add(theme)
        self.db.flush()
        self._log_action("CREATE", "THEME", theme.id, theme_code, user_id=operator_id)
        self.db.commit()
        self.db.refresh(theme)
        self._log_info(f"创建业务主题 {theme_code}")
        return theme

    # ========== 修改 ==========
    def update_theme(self, theme_id: int, theme_name: Optional[str] = None,
                     main_table_id: Optional[int] = None, description: Optional[str] = None,
                     is_enabled: Optional[bool] = None,
                     operator_id: Optional[int] = None) -> BusinessTheme:
        theme = self.db.get(BusinessTheme, theme_id)
        if not theme:
            raise BusinessException(ERR_NOT_FOUND, f"业务主题 {theme_id} 不存在")

        if theme_name is not None:
            theme.theme_name = theme_name
        if description is not None:
            theme.description = description
        if is_enabled is not None:
            theme.is_enabled = is_enabled

        if main_table_id is not None and main_table_id != theme.main_table_id:
            self._validate_main_table(main_table_id)
            refs = self.count_task_refs(theme_id)
            if refs:
                raise BusinessException(
                    ERR_BAD_REQUEST,
                    f"主题 '{theme.theme_name}' 已被 {refs} 个标签任务引用，禁止修改主题表",
                )
            theme.main_table_id = main_table_id

        theme.updated_at = datetime.utcnow()
        self._log_action("UPDATE", "THEME", theme.id, theme.theme_code, user_id=operator_id)
        self.db.commit()
        self._log_info(f"更新业务主题 {theme.theme_code}")
        return theme

    # ========== 删除 ==========
    def delete_theme(self, theme_id: int, operator_id: Optional[int] = None) -> None:
        theme = self.db.get(BusinessTheme, theme_id)
        if not theme:
            raise BusinessException(ERR_NOT_FOUND, f"业务主题 {theme_id} 不存在")

        refs = self.count_task_refs(theme_id)
        if refs:
            raise BusinessException(
                ERR_BAD_REQUEST,
                f"主题 '{theme.theme_name}' 正被 {refs} 个标签任务引用，无法删除",
            )

        self._log_action("DELETE", "THEME", theme_id, theme.theme_code, user_id=operator_id)
        self.db.delete(theme)
        self.db.commit()
        self._log_info(f"删除业务主题 {theme.theme_code}")

    # ========== 校验 ==========
    def _validate_main_table(self, main_table_id: int) -> None:
        table = self.db.get(MetaTable, main_table_id)
        if not table:
            raise BusinessException(ERR_META_NOT_FOUND, f"主题表 {main_table_id} 不存在")
        if table.status != "approved":
            raise BusinessException(
                ERR_VALIDATION,
                f"主题表 '{table.table_name}' 尚未审批通过（当前状态: {table.status}）",
            )
