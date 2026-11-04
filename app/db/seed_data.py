"""
db/seed_data.py — 保险行业脱敏演示种子数据（V1.1 新增）

职责：
- 在数据库初始化完成后，幂等写入一套保险业务演示数据：
  2 个演示数据源、5 张业务表元数据、3 条表关联、3 组字段枚举、
  4 个业务主题、以及独立的 SQLite 演示业务库（5 张物理表 + 脱敏样例）。
- 不修改既有业务表结构、不侵入 service / router。
- 幂等：已存在 POLICY_THEME 主题或 policy 元数据表时直接返回 False。

调用位置：app/db/database.py::init_db() 中 create_all + 增量迁移之后。
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import demo_data as demo_cfg
from app.db.models.business_theme import BusinessTheme
from app.db.models.datasource import Datasource
from app.db.models.enum_config import FieldEnum
from app.db.models.metadata import MetaField, MetaTable
from app.db.models.relation import TableRelation


# ======================================================================
# 业务表定义（字段名均为保险核心系统标准命名）
# (field_name, field_type, field_comment, is_primary_key, is_nullable)
# ======================================================================
_TABLE_SPECS: List[dict] = [
    {
        "table_name": "policy",
        "table_comment": "保单表",
        "fields": [
            ("policy_id", "VARCHAR(32)", "保单ID（主键）", True, False),
            ("policy_no", "VARCHAR(64)", "保单号", False, False),
            ("product_code", "VARCHAR(64)", "产品编码", False, True),
            ("product_name", "VARCHAR(128)", "产品名称", False, True),
            ("policy_status", "VARCHAR(32)", "保单状态（枚举 policy_status）", False, True),
            ("effective_date", "DATE", "生效日期", False, True),
            ("expiry_date", "DATE", "满期日期", False, True),
            ("premium_amount", "DECIMAL(18,2)", "保费金额", False, True),
            ("sum_insured", "DECIMAL(18,2)", "保险金额", False, True),
            ("policy_holder_id", "VARCHAR(32)", "投保人ID（团体客户）", False, True),
            ("insured_id", "VARCHAR(32)", "被保人ID（个人客户）", False, True),
            ("agent_code", "VARCHAR(32)", "代理人编码", False, True),
            ("channel_code", "VARCHAR(32)", "销售渠道编码", False, True),
            ("issue_date", "DATE", "承保日期", False, True),
        ],
    },
    {
        "table_name": "person_customer",
        "table_comment": "个人客户表",
        "fields": [
            ("customer_id", "VARCHAR(32)", "客户ID（主键）", True, False),
            ("customer_name", "VARCHAR(64)", "客户姓名（脱敏）", False, True),
            ("gender", "VARCHAR(8)", "性别", False, True),
            ("birth_date", "DATE", "出生日期", False, True),
            ("id_type", "VARCHAR(16)", "证件类型", False, True),
            ("id_no_masked", "VARCHAR(64)", "证件号码（脱敏）", False, True),
            ("mobile_masked", "VARCHAR(32)", "手机号码（脱敏）", False, True),
            ("customer_type", "VARCHAR(16)", "客户类型（枚举 customer_type）", False, True),
            ("occupation_code", "VARCHAR(32)", "职业编码", False, True),
            ("education_level", "VARCHAR(32)", "学历", False, True),
            ("marital_status", "VARCHAR(16)", "婚姻状况", False, True),
            ("risk_level", "VARCHAR(16)", "风险等级", False, True),
        ],
    },
    {
        "table_name": "group_customer",
        "table_comment": "团体客户表",
        "fields": [
            ("group_id", "VARCHAR(32)", "团体客户ID（主键）", True, False),
            ("group_name", "VARCHAR(128)", "团体客户名称", False, True),
            ("group_type", "VARCHAR(32)", "团体类型", False, True),
            ("unified_social_credit_code", "VARCHAR(32)", "统一社会信用代码", False, True),
            ("industry_code", "VARCHAR(32)", "行业编码", False, True),
            ("employee_count", "INTEGER", "员工人数", False, True),
            ("contact_name", "VARCHAR(64)", "联系人姓名", False, True),
            ("contact_phone_masked", "VARCHAR(32)", "联系电话（脱敏）", False, True),
            ("address_region", "VARCHAR(128)", "所在地区", False, True),
            ("customer_level", "VARCHAR(16)", "客户等级", False, True),
        ],
    },
    {
        "table_name": "policy_customer_rel",
        "table_comment": "保单客户关系表",
        "fields": [
            ("rel_id", "VARCHAR(32)", "关系ID（主键）", True, False),
            ("policy_id", "VARCHAR(32)", "保单ID", False, False),
            ("customer_id", "VARCHAR(32)", "客户ID", False, False),
            ("customer_role", "VARCHAR(16)", "客户角色（投保人/被保人/受益人）", False, True),
            ("hold_ratio", "DECIMAL(5,4)", "持有比例", False, True),
            ("relation_status", "VARCHAR(16)", "关系状态", False, True),
        ],
    },
    {
        "table_name": "policy_case",
        "table_comment": "保单案件表",
        "fields": [
            ("case_id", "VARCHAR(32)", "案件ID（主键）", True, False),
            ("policy_id", "VARCHAR(32)", "关联保单ID", False, False),
            ("case_no", "VARCHAR(64)", "案件号", False, False),
            ("case_type", "VARCHAR(32)", "案件类型", False, True),
            ("case_status", "VARCHAR(32)", "案件状态（枚举 case_status）", False, True),
            ("report_date", "DATE", "报案日期", False, True),
            ("close_date", "DATE", "结案日期", False, True),
            ("claim_amount", "DECIMAL(18,2)", "赔付金额", False, True),
            ("handler_code", "VARCHAR(32)", "理赔人员编码", False, True),
            ("case_desc", "VARCHAR(256)", "案件描述", False, True),
        ],
    },
]


# ======================================================================
# 脱敏样例数据（写入独立演示业务库，不写平台库）
# ======================================================================
_SAMPLE_ROWS: Dict[str, Tuple[List[str], List[tuple]]] = {
    "person_customer": (
        ["customer_id", "customer_name", "gender", "birth_date", "id_type", "id_no_masked",
         "mobile_masked", "customer_type", "occupation_code", "education_level",
         "marital_status", "risk_level"],
        [
            ("C0001", "张*明", "M", "1985-03-12", "ID_CARD", "3101**********1234", "138****5678",
             "PERSON", "OCC_01", "BACHELOR", "MARRIED", "LOW"),
            ("C0002", "李*华", "F", "1990-07-25", "ID_CARD", "3101**********2345", "139****6789",
             "PERSON", "OCC_02", "MASTER", "MARRIED", "LOW"),
            ("C0003", "王*芳", "F", "1978-11-08", "ID_CARD", "3101**********3456", "137****7890",
             "PERSON", "OCC_03", "COLLEGE", "DIVORCED", "MEDIUM"),
        ],
    ),
    "group_customer": (
        ["group_id", "group_name", "group_type", "unified_social_credit_code",
         "industry_code", "employee_count", "contact_name", "contact_phone_masked",
         "address_region", "customer_level"],
        [
            ("G0001", "华信保险代理有限公司", "AGENCY", "91310000MA1K****01",
             "IND_AGENCY", 120, "陈*", "021-****0001", "上海市浦东新区", "A"),
            ("G0002", "恒安物流集团有限公司", "ENTERPRISE", "91310000MA1K****02",
             "IND_LOGISTICS", 860, "刘*", "021-****0002", "上海市宝山区", "B"),
        ],
    ),
    "policy": (
        ["policy_id", "policy_no", "product_code", "product_name", "policy_status",
         "effective_date", "expiry_date", "premium_amount", "sum_insured",
         "policy_holder_id", "insured_id", "agent_code", "channel_code", "issue_date"],
        [
            ("P0001", "P2024000001", "PRD_TERM_LIFE", "定期寿险", "EFFECTIVE",
             "2024-01-01", "2034-01-01", 3800.00, 500000.00, "G0001", "C0001",
             "A1001", "CH_ONLINE", "2023-12-28"),
            ("P0002", "P2024000002", "PRD_ACCIDENT", "个人意外伤害险", "LAPSED",
             "2024-02-01", "2025-02-01", 260.00, 100000.00, "G0002", "C0002",
             "A1002", "CH_OFFLINE", "2024-01-30"),
            ("P0003", "P2024000003", "PRD_MEDICAL", "住院医疗保险", "CLAIMED",
             "2024-03-01", "2025-03-01", 1580.00, 200000.00, "G0001", "C0003",
             "A1001", "CH_ONLINE", "2024-02-28"),
        ],
    ),
    "policy_customer_rel": (
        ["rel_id", "policy_id", "customer_id", "customer_role", "hold_ratio", "relation_status"],
        [
            ("R0001", "P0001", "C0001", "PRIMARY", 1.0000, "ACTIVE"),
            ("R0002", "P0002", "C0002", "PRIMARY", 1.0000, "ACTIVE"),
            ("R0003", "P0003", "C0003", "PRIMARY", 1.0000, "ACTIVE"),
        ],
    ),
    "policy_case": (
        ["case_id", "policy_id", "case_no", "case_type", "case_status", "report_date",
         "close_date", "claim_amount", "handler_code", "case_desc"],
        [
            ("K0001", "P0003", "CL20240001", "MEDICAL", "PAID",
             "2024-06-01", "2024-07-15", 12000.00, "H2001", "住院医疗费用理赔，材料齐全"),
            ("K0002", "P0001", "CL20240002", "ACCIDENT", "SURVEYING",
             "2024-09-10", None, None, "H2002", "意外伤害案件调查中"),
        ],
    ),
}


# ======================================================================
# 枚举定义
# ======================================================================
_ENUM_SPECS: List[dict] = [
    {
        "table_name": "policy", "field_name": "policy_status",
        "items": [
            ("DRAFT", "草稿"), ("UNDERWRITING", "核保中"), ("EFFECTIVE", "生效"),
            ("LAPSED", "失效"), ("SURRENDERED", "退保"), ("CLAIMED", "理赔中"),
            ("TERMINATED", "终止"),
        ],
    },
    {
        "table_name": "policy_case", "field_name": "case_status",
        "items": [
            ("REPORTED", "已报案"), ("REGISTERED", "已立案"), ("SURVEYING", "调查中"),
            ("ASSESSED", "已定损"), ("PAID", "已赔付"), ("CLOSED", "已结案"),
            ("REJECTED", "拒赔"),
        ],
    },
    {
        "table_name": "person_customer", "field_name": "customer_type",
        "items": [("PERSON", "个人客户"), ("GROUP", "团体客户")],
    },
]


# ======================================================================
# 关联关系（左表.字段 = 右表.字段，relation_type 相对左表）
# ======================================================================
_RELATION_SPECS = [
    ("policy", "insured_id", "person_customer", "customer_id", "LEFT", "保单 → 个人被保人"),
    ("policy", "policy_holder_id", "group_customer", "group_id", "LEFT", "保单 → 团体投保人"),
    ("policy", "policy_id", "policy_case", "policy_id", "LEFT", "保单 → 保单案件"),
    ("policy", "policy_id", "policy_customer_rel", "policy_id", "LEFT", "保单 → 保单客户关系"),
    ("policy_case", "policy_id", "policy_customer_rel", "policy_id", "INNER", "案件 ↔ 保单客户关系（同保单）"),
]


# ======================================================================
# 业务主题
# ======================================================================
_THEME_SPECS = [
    ("POLICY_THEME", "保单主题", "policy", "以保单为主表，承载保单维度的标签"),
    ("PERSON_THEME", "个人客户主题", "person_customer", "以个人客户为主表，承载客户画像标签"),
    ("GROUP_THEME", "团体客户主题", "group_customer", "以团体客户为主表，承载团体客户标签"),
    ("CASE_THEME", "案件主题", "policy_case", "以保单案件为主表，承载理赔案件标签"),
]


def _demo_db_path() -> str:
    """演示业务库路径（来自 config.yaml demo_data.sqlite_path）"""
    return demo_cfg.sqlite_path()


# ======================================================================
# 对外入口
# ======================================================================
def init_insurance_seed_data(session_factory: Optional[sessionmaker] = None,
                             physical: bool = True) -> bool:
    """
    幂等写入保险行业演示数据。

    Args:
        session_factory: Session 工厂；默认取平台库 get_session_factory()，测试可传内存库工厂
        physical: 是否创建独立 SQLite 演示业务库及样例数据（测试可传 False）

    Returns:
        bool: True = 本次执行了初始化；False = 数据已存在，幂等跳过
    """
    factory = session_factory
    if factory is None:
        from app.db.database import get_session_factory
        factory = get_session_factory()

    if not demo_cfg.enabled:
        return False

    with factory() as session:
        # ---------- 幂等检查 ----------
        theme_exists = session.execute(
            select(BusinessTheme).where(BusinessTheme.theme_code == "POLICY_THEME")
        ).scalar_one_or_none()
        policy_exists = session.execute(
            select(MetaTable).where(MetaTable.table_name == "policy")
        ).scalar_one_or_none()
        if theme_exists or policy_exists:
            return False

        try:
            # ---------- 1. 演示数据源 ----------
            ds_sqlite = Datasource(
                name="保险演示库（SQLite）",
                ds_type="sqlite",
                config_json=json.dumps({"db_path": _demo_db_path()}, ensure_ascii=False),
                is_enabled=True,
                remark="种子函数自动创建的保险业务演示库",
            )
            ds_spark = Datasource(
                name="Spark 演示数据源（Mock）",
                ds_type="spark",
                config_json=json.dumps({"mock": True}, ensure_ascii=False),
                is_enabled=True,
                remark="Mock 模式，校验/执行默认成功，无需 Spark 集群",
            )
            session.add_all([ds_sqlite, ds_spark])
            session.flush()

            # ---------- 2. 演示业务库物理表 + 样例 ----------
            if physical:
                _create_physical_demo_db(ds_sqlite.config_json)

            # ---------- 3. 表元数据 + 字段元数据 ----------
            tables: Dict[str, MetaTable] = {}
            fields: Dict[Tuple[str, str], MetaField] = {}
            for spec in _TABLE_SPECS:
                table = MetaTable(
                    table_name=spec["table_name"],
                    table_comment=spec["table_comment"],
                    datasource_id=ds_sqlite.id,
                    status="approved",
                )
                session.add(table)
                session.flush()
                tables[table.table_name] = table

                for pos, (fname, ftype, fcomment, is_pk, nullable) in enumerate(spec["fields"], start=1):
                    field = MetaField(
                        table_id=table.id,
                        field_name=fname,
                        field_type=ftype,
                        field_comment=fcomment,
                        is_primary_key=is_pk,
                        is_nullable=nullable,
                        ordinal_position=pos,
                    )
                    session.add(field)
                    fields[(table.table_name, fname)] = field
            session.flush()

            # ---------- 4. 表关联关系 ----------
            for l_table, l_field, r_table, r_field, rel_type, _ in _RELATION_SPECS:
                session.add(TableRelation(
                    left_table_id=tables[l_table].id,
                    left_field_id=fields[(l_table, l_field)].id,
                    right_table_id=tables[r_table].id,
                    right_field_id=fields[(r_table, r_field)].id,
                    relation_type=rel_type,
                ))

            # ---------- 5. 枚举 ----------
            for spec in _ENUM_SPECS:
                table = tables[spec["table_name"]]
                field = fields[(spec["table_name"], spec["field_name"])]
                for ordinal, (code, label) in enumerate(spec["items"]):
                    session.add(FieldEnum(
                        table_id=table.id,
                        field_id=field.id,
                        enum_code=code,
                        enum_label=label,
                        ordinal=ordinal,
                    ))

            # ---------- 6. 业务主题 ----------
            for code, name, main_table, desc in _THEME_SPECS:
                session.add(BusinessTheme(
                    theme_code=code,
                    theme_name=name,
                    main_table_id=tables[main_table].id,
                    description=desc,
                    is_enabled=True,
                ))

            session.commit()
            return True
        except Exception:
            session.rollback()
            raise


# ======================================================================
# 内部辅助
# ======================================================================
def _create_physical_demo_db(config_json: str) -> None:
    """在独立 SQLite 演示库中建 5 张物理表并写入脱敏样例（幂等）"""
    try:
        cfg = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        cfg = {}
    db_path = cfg.get("db_path") or _demo_db_path()

    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for spec in _TABLE_SPECS:
            cur.execute(_build_create_sql(spec))

        for table_name, (columns, rows) in _SAMPLE_ROWS.items():
            placeholders = ", ".join("?" for _ in columns)
            cols_sql = ", ".join(f'"{c}"' for c in columns)
            cur.execute(f'DELETE FROM "{table_name}"')
            cur.executemany(
                f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders})',
                rows,
            )
        conn.commit()
    finally:
        conn.close()


def _build_create_sql(spec: dict) -> str:
    """根据表定义拼装 CREATE TABLE IF NOT EXISTS"""
    columns = []
    pk = None
    for fname, ftype, _, is_pk, nullable in spec["fields"]:
        not_null = "" if nullable else " NOT NULL"
        columns.append(f'"{fname}" {ftype}{not_null}')
        if is_pk:
            pk = fname
    if pk:
        columns.append(f'PRIMARY KEY ("{pk}")')
    return f'CREATE TABLE IF NOT EXISTS "{spec["table_name"]}" ({", ".join(columns)})'
