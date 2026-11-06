"""
services/base.py — Service 基类

职责：
- 持有一个 DB Session，子类通过 self.db 读写 ORM
- 提供日志便捷方法（写入 system_logs 表）
- 提供 serial_no 编号生成器（前缀 + YYYYMMDD + 001 递增）
- 任何 service 方法不依赖 FastAPI 对象（脱离 Web 可独立调用）
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session


class BaseService:
    """所有业务 Service 的基类"""

    # 子类覆盖：日志中标识模块名
    MODULE: str = "base"

    def __init__(self, db: Session):
        self.db = db

    # ========== 通用编号生成器 ==========
    def _gen_serial_no(self, model_cls, prefix: str) -> str:
        """
        生成 serial_no：前缀(3位大写) + YYYYMMDD + NNN(3位递增)
        例：MET20261105001, THE20261105001, TAG20261105001

        Args:
            model_cls: SQLAlchemy ORM 类（用于查最大序号）
            prefix:    3 位大写前缀

        Returns:
            serial_no 字符串
        """
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix_date = f"{prefix}{today}"

        # 查当天最大序号
        serial_col = getattr(model_cls, 'serial_no', None)
        if serial_col is None:
            raise ValueError(f"{model_cls.__name__} 没有 serial_no 字段")

        stmt = (
            select(func.max(serial_col))
            .where(serial_col.like(f"{prefix_date}%"))
        )
        max_no = self.db.execute(stmt).scalar_one_or_none()

        if max_no:
            # 取出末尾 3 位数字，+1
            try:
                seq = int(max_no[-3:]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1

        return f"{prefix_date}{seq:03d}"

    # ========== 日志便捷方法 ==========
    def _log(self, level: str, message: str, user_id: Optional[int] = None, module: Optional[str] = None) -> None:
        from app.db.models.system_log import SystemLog
        log = SystemLog(
            level=level,
            module=module or self.MODULE,
            message=message[:4000],
            user_id=user_id,
        )
        try:
            self.db.add(log)
            self.db.flush()  # 不 commit，由外层决定
        except Exception:
            # 日志写入失败不应影响主流程
            pass

    def _log_info(self, message: str, user_id: Optional[int] = None) -> None:
        self._log("INFO", message, user_id)

    def _log_warn(self, message: str, user_id: Optional[int] = None) -> None:
        self._log("WARN", message, user_id)

    def _log_error(self, message: str, user_id: Optional[int] = None) -> None:
        self._log("ERROR", message, user_id)
