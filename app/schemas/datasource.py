"""
schemas/datasource.py — 数据源
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class SqliteConfig(BaseModel):
    db_path: str = Field(..., min_length=1, description="SQLite 数据库文件路径")


class SparkConfig(BaseModel):
    thrift_url: str = Field(..., min_length=1, description="Thrift JDBC 地址，如 jdbc:hive2://host:10015")
    username: Optional[str] = None
    password: Optional[str] = None


class DatasourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    ds_type: str = Field(..., pattern=r"^(sqlite|spark)$")
    config: Dict[str, Any] = Field(..., description="连接配置")
    is_enabled: bool = True
    remark: Optional[str] = None

    @model_validator(mode="after")
    def validate_config_structure(self):
        cfg = self.config or {}
        if self.ds_type == "sqlite":
            if not cfg.get("db_path"):
                raise ValueError("sqlite 数据源必须提供 db_path")
        elif self.ds_type == "spark":
            if not cfg.get("thrift_url"):
                raise ValueError("spark 数据源必须提供 thrift_url")
        return self


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    remark: Optional[str] = None


class DatasourceOut(ORMModel):
    id: int
    name: str
    ds_type: str
    # config_json 字符串转回去，密码字段掩码
    config: Dict[str, Any]
    is_enabled: bool
    remark: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class DatasourceTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


class DatasourceTestConnection(BaseModel):
    """仅测试连接（不保存），不需要 name / is_enabled"""
    ds_type: str = Field(..., pattern=r"^(sqlite|spark)$")
    config: Dict[str, Any] = Field(..., description="连接配置")
