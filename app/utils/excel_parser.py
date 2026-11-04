"""
excel_parser.py — Excel 模板生成 + 导入解析
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook, load_workbook


# Excel 模板头（两部分：表信息 sheet + 字段信息 sheet）
TEMPLATE_SHEETS = {
    "表信息": ["表名 (必填)", "表中文名/注释", "备注"],
    "字段信息": ["字段名 (必填)", "字段类型 (必填)", "字段中文名", "是否主键 (Y/N)", "是否可空 (Y/N)", "字段顺序"],
}


def get_template_path() -> str:
    """返回模板文件路径"""
    from app.config import BASE_DIR
    return str(BASE_DIR / "docs" / "excel_template" / "metadata_template.xlsx")


def ensure_template_exists() -> str:
    """模板不存在则生成，返回路径"""
    path = get_template_path()
    if not os.path.exists(path):
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "表信息"
        ws1.append(TEMPLATE_SHEETS["表信息"])
        # 示例数据
        ws1.append(["user_info", "用户基础信息", "示例"])

        ws2 = wb.create_sheet("字段信息")
        ws2.append(TEMPLATE_SHEETS["字段信息"])
        ws2.append(["user_id", "BIGINT", "用户ID", "Y", "N", 1])
        ws2.append(["user_name", "VARCHAR(64)", "用户名", "N", "Y", 2])

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
    return path


def generate_template_bytes() -> bytes:
    """生成模板并返回字节流（供浏览器下载）"""
    buf = io.BytesIO()
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "表信息"
    ws1.append(TEMPLATE_SHEETS["表信息"])
    ws1.append(["user_info", "用户基础信息", "示例"])

    ws2 = wb.create_sheet("字段信息")
    ws2.append(TEMPLATE_SHEETS["字段信息"])
    ws2.append(["user_id", "BIGINT", "用户ID", "Y", "N", 1])
    ws2.append(["user_name", "VARCHAR(64)", "用户名", "N", "Y", 2])

    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ========== 导入解析 ==========
class ExcelParseError(Exception):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def parse_metadata_excel(file_bytes: bytes) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    解析上传的 Excel 文件
    返回：(table_info_dict, field_list)
    解析失败抛 ExcelParseError（带详细错误列表）
    """
    errors: List[str] = []

    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        raise ExcelParseError([f"Excel 文件格式错误：{e}"])

    # ------ Sheet1: 表信息 ------
    ws_tables = None
    for sn in wb.sheetnames:
        if "表信息" in sn:
            ws_tables = wb[sn]
            break
    if ws_tables is None:
        raise ExcelParseError(["缺少【表信息】工作表"])

    table_info = _parse_table_sheet(ws_tables, errors)

    # ------ Sheet2: 字段信息 ------
    ws_fields = None
    for sn in wb.sheetnames:
        if "字段信息" in sn:
            ws_fields = wb[sn]
            break
    if ws_fields is None:
        raise ExcelParseError(["缺少【字段信息】工作表"])

    fields = _parse_field_sheet(ws_fields, errors)

    if errors:
        raise ExcelParseError(errors)

    return table_info, fields


def _parse_table_sheet(ws, errors: List[str]) -> Dict[str, Any]:
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        errors.append("【表信息】无数据行（至少保留表头 + 一行数据）")
        return {}

    header = [str(c).strip() if c else "" for c in rows[0]]
    # 兼容表头
    row = rows[1]  # 只取第一行表信息
    if not row or not str(row[0] or "").strip():
        errors.append("【表信息】第 2 行表名不能为空")
        return {}

    table_name = str(row[0]).strip()
    table_comment = str(row[1]).strip() if row[1] else ""

    # 表名校验
    if not _is_valid_identifier(table_name):
        errors.append(f"表名 '{table_name}' 不合法（只允许字母/数字/下划线，且不能以数字开头）")

    return {
        "table_name": table_name,
        "table_comment": table_comment,
    }


def _parse_field_sheet(ws, errors: List[str]) -> List[Dict[str, Any]]:
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        errors.append("【字段信息】无数据行（至少保留表头 + 一行数据）")
        return []

    header = [str(c).strip() if c else "" for c in rows[0]]
    # 兼容列位置
    col_name = _find_col(header, ["字段名", "field_name"])
    col_type = _find_col(header, ["字段类型", "field_type"])
    col_comment = _find_col(header, ["字段中文名", "字段注释", "field_comment"])
    col_pk = _find_col(header, ["是否主键", "is_primary_key"])
    col_null = _find_col(header, ["是否可空", "is_nullable"])
    col_order = _find_col(header, ["字段顺序", "ordinal"])

    fields: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows[1:], start=2):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue  # 跳过空行

        field_name = str(_safe_get(row, col_name) or "").strip()
        field_type = str(_safe_get(row, col_type) or "").strip()

        if not field_name:
            errors.append(f"【字段信息】第 {idx} 行：字段名不能为空")
            continue
        if not field_type:
            errors.append(f"【字段信息】第 {idx} 行：字段类型不能为空")
            continue
        if not _is_valid_identifier(field_name):
            errors.append(f"【字段信息】第 {idx} 行：字段名 '{field_name}' 不合法")
            continue

        fields.append({
            "field_name": field_name,
            "field_type": field_type,
            "field_comment": str(_safe_get(row, col_comment) or "").strip(),
            "is_primary_key": _parse_bool(_safe_get(row, col_pk)),
            "is_nullable": _parse_bool(_safe_get(row, col_null), default=True),
            "ordinal_position": _safe_int(_safe_get(row, col_order), default=len(fields) + 1),
        })

    if not fields:
        errors.append("【字段信息】解析后无有效字段，请检查内容")

    # 检查主键字段
    if not any(f["is_primary_key"] for f in fields):
        errors.append("字段信息中至少需要一个主键字段（标记 '是否主键' 为 Y）")

    return fields


def _find_col(header: List[str], keywords: List[str]) -> int:
    for kw in keywords:
        for i, h in enumerate(header):
            if kw.lower() in h.lower():
                return i
    return -1


def _safe_get(row, idx: int):
    if idx < 0 or idx >= len(row):
        return None
    return row[idx]


def _parse_bool(val, default: bool = False) -> bool:
    if val is None:
        return default
    s = str(val).strip().upper()
    if s in ("Y", "YES", "TRUE", "1", "是"):
        return True
    if s in ("N", "NO", "FALSE", "0", "否"):
        return False
    return default


def _safe_int(val, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return int(float(str(val).strip()))
    except Exception:
        return default


_IDENTIFIER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _is_valid_identifier(name: str) -> bool:
    if not name:
        return False
    if name[0].isdigit():
        return False
    return all(c in _IDENTIFIER_CHARS for c in name)
