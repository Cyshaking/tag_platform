"""
services/datasource_service.py — 数据源管理 + 测试连接
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.datasource import Datasource
from app.db.models.tag_task import TagTask
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_DUP_DATASOURCE, ERR_NOT_FOUND, ERR_DS_TEST_FAIL, ERR_DS_DISABLED
from app.utils.password_mask import mask_password, contains_password


class DatasourceService(BaseService):
    MODULE = "datasource"

    # ========== CRUD ==========
    def list_datasources(self, include_disabled: bool = True) -> List[Datasource]:
        stmt = select(Datasource).order_by(Datasource.id)
        if not include_disabled:
            stmt = stmt.where(Datasource.is_enabled == True)  # noqa: E712
        return self.db.execute(stmt).scalars().all()

    def get_datasource(self, ds_id: int) -> Optional[Datasource]:
        return self.db.get(Datasource, ds_id)

    def create_datasource(self, name: str, ds_type: str, config: Dict[str, Any],
                          is_enabled: bool = True, remark: Optional[str] = None,
                          operator_id: Optional[int] = None) -> Datasource:
        # 名称唯一
        existing = self.db.execute(select(Datasource).where(Datasource.name == name)).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_DUP_DATASOURCE, f"数据源名称 '{name}' 已存在")

        ds = Datasource(
            name=name,
            ds_type=ds_type,
            config_json=json.dumps(config, ensure_ascii=False),
            is_enabled=is_enabled,
            remark=remark,
        )
        self.db.add(ds)
        self.db.commit()
        self._log_info(f"创建数据源 {name} ({ds_type})", operator_id)
        return ds

    def update_datasource(self, ds_id: int, name: Optional[str] = None,
                          config: Optional[Dict[str, Any]] = None,
                          is_enabled: Optional[bool] = None,
                          remark: Optional[str] = None,
                          operator_id: Optional[int] = None) -> Datasource:
        ds = self.db.get(Datasource, ds_id)
        if not ds:
            raise BusinessException(ERR_NOT_FOUND, f"数据源 {ds_id} 不存在")

        if name is not None and name != ds.name:
            # 改名也要检查唯一
            existing = self.db.execute(select(Datasource).where(Datasource.name == name)).scalar_one_or_none()
            if existing:
                raise BusinessException(ERR_DUP_DATASOURCE, f"数据源名称 '{name}' 已存在")
            ds.name = name
        if config is not None:
            ds.config_json = json.dumps(config, ensure_ascii=False)
        if is_enabled is not None:
            ds.is_enabled = is_enabled
        if remark is not None:
            ds.remark = remark
        ds.updated_at = datetime.utcnow()

        self.db.commit()
        self._log_info(f"更新数据源 {ds.name}", operator_id)
        return ds

    def delete_datasource(self, ds_id: int, operator_id: Optional[int] = None) -> None:
        ds = self.db.get(Datasource, ds_id)
        if not ds:
            raise BusinessException(ERR_NOT_FOUND, f"数据源 {ds_id} 不存在")

        # 检查是否有标签任务在使用
        refs = self.db.execute(select(TagTask).where(TagTask.datasource_id == ds_id)).scalars().all()
        if refs:
            raise BusinessException(
                ERR_DS_DISABLED,
                f"数据源 '{ds.name}' 已绑定 {len(refs)} 个标签任务，请先解除绑定后再删除",
            )

        self.db.delete(ds)
        self.db.commit()
        self._log_info(f"删除数据源 {ds.name}", operator_id)

    def toggle_enabled(self, ds_id: int, enabled: bool, operator_id: Optional[int] = None) -> Datasource:
        ds = self.db.get(Datasource, ds_id)
        if not ds:
            raise BusinessException(ERR_NOT_FOUND, f"数据源 {ds_id} 不存在")
        ds.is_enabled = enabled
        ds.updated_at = datetime.utcnow()
        self.db.commit()
        self._log_info(f"{'启用' if enabled else '禁用'} 数据源 {ds.name}", operator_id)
        return ds

    # ========== 测试连接 ==========
    @staticmethod
    def test_connection(ds_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        测试连接，返回 {success, message, latency_ms}
        失败不抛 BusinessException，直接返回 success=False
        """
        start = time.time()
        try:
            if ds_type == "sqlite":
                DatasourceService._test_sqlite(config)
            elif ds_type == "spark":
                DatasourceService._test_spark(config)
            else:
                return {"success": False, "message": f"不支持的数据源类型: {ds_type}", "latency_ms": None}
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return {"success": False, "message": f"连接失败: {e}", "latency_ms": duration}

        duration = int((time.time() - start) * 1000)
        return {"success": True, "message": "连接成功", "latency_ms": duration}

    @staticmethod
    def _test_sqlite(config: Dict[str, Any]) -> None:
        db_path = config.get("db_path")
        if not db_path:
            raise ValueError("缺少 db_path")
        # 尝试打开（文件可能不存在，但 sqlite3 会自动创建——这里只连接不建表以允许不存在也能测试）
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()

    @staticmethod
    def _test_spark(config: Dict[str, Any]) -> None:
        thrift_url = config.get("thrift_url")
        if not thrift_url:
            raise ValueError("缺少 thrift_url")
        # 真实测试需要 JayDeBeApi，但作业场景可能没装，给出友好提示
        try:
            import jaydebeapi
        except ImportError:
            raise RuntimeError("JayDeBeApi 未安装，无法测试 Spark 连接（仅 Mock 场景可用）")
        # 真实连接（可能超时）
        user = config.get("username") or ""
        password = config.get("password") or ""
        conn = jaydebeapi.connect("org.apache.hive.jdbc.HiveDriver", thrift_url,
                                 [user, password] if user else [])
        conn.cursor().execute("SELECT 1")
        conn.close()

    # ========== 序列化（密码掩码） ==========
    def serialize(self, ds: Datasource) -> Dict[str, Any]:
        """序列化为 API 输出结构，密码字段自动掩码"""
        try:
            raw_config = json.loads(ds.config_json)
        except Exception:
            raw_config = {}
        masked = mask_password(raw_config)
        return {
            "id": ds.id,
            "name": ds.name,
            "ds_type": ds.ds_type,
            "config": masked,
            "is_enabled": ds.is_enabled,
            "remark": ds.remark,
            "created_at": ds.created_at.isoformat() if ds.created_at else None,
            "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        }

    def get_raw_config(self, ds: Datasource) -> Dict[str, Any]:
        """获取原始 config（含真实密码），仅引擎层内部使用"""
        try:
            return json.loads(ds.config_json)
        except Exception:
            return {}
