"""
exceptions.py — 自定义业务异常
"""
from typing import Any, Optional


class BusinessException(Exception):
    """业务异常：service 层抛出，router 层统一捕获并返回友好提示"""

    def __init__(self, code: int = 40000, message: str = "业务处理失败", data: Optional[Any] = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


# ========== 通用业务错误码 ==========
OK = 0
# 4xxxx 业务错误
ERR_BAD_REQUEST = 40000
ERR_VALIDATION = 40001
ERR_NOT_FOUND = 40400
ERR_PERMISSION = 40300
ERR_AUTH = 40100
# 5xxxx 系统错误
ERR_SYSTEM = 50000
ERR_DB = 50001

# 模块细分错误码：元数据 41xxx、审批 42xxx、数据源 43xxx、标签 44xxx
ERR_META_TABLE_DUP = 41001
ERR_META_FIELD_DUP = 41002
ERR_META_NOT_FOUND = 41003
ERR_EXCEL_FORMAT = 41010
ERR_EXCEL_EMPTY = 41011
ERR_APPROVE_STATE = 42001
ERR_APPROVE_ROLE = 42002
ERR_DUP_DATASOURCE = 43001
ERR_DS_TEST_FAIL = 43002
ERR_DS_DISABLED = 43003
ERR_TAG_SQL_EMPTY = 44001
ERR_TAG_DUP = 44002
