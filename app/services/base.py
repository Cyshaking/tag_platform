"""
services/base.py — Service 基类

职责：
- 持有一个 DB Session，子类通过 self.db 读写 ORM
- 提供日志便捷方法（写入 system_logs 表）
- 任何 service 方法不依赖 FastAPI 对象（脱离 Web 可独立调用）
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session


class BaseService:
    """所有业务 Service 的基类"""

    # 子类覆盖：日志中标识模块名
    MODULE: str = "base"

    def __init__(self, db: Session):
        self.db = db

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
