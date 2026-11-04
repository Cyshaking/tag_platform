"""
tests/unit/test_seed_data.py — 保险演示种子数据（V1.1 #4）
覆盖：首次初始化、幂等跳过、5 表/4 主题/3 关系/枚举/数据源、主题主表绑定。
"""
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models.business_theme import BusinessTheme
from app.db.models.datasource import Datasource
from app.db.models.enum_config import FieldEnum
from app.db.models.metadata import MetaField, MetaTable
from app.db.models.relation import TableRelation
from app.db.seed_data import init_insurance_seed_data


def _factory(db):
    return sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False,
                        expire_on_commit=False)


def _count(db, model) -> int:
    return int(db.execute(select(func.count()).select_from(model)).scalar_one())


class TestSeedData:

    def test_first_run_creates_all(self, db):
        assert init_insurance_seed_data(_factory(db), physical=False) is True

        assert _count(db, MetaTable) == 5
        assert _count(db, MetaField) == 52
        assert _count(db, BusinessTheme) == 4
        assert _count(db, TableRelation) == 5  # policy↔person / policy↔group / policy↔policy_case / policy↔rel / policy_case↔rel
        assert _count(db, FieldEnum) == 16

        # 2 个演示数据源：sqlite 真实执行 + spark mock
        dss = db.execute(select(Datasource)).scalars().all()
        assert {d.ds_type for d in dss} == {"sqlite", "spark"}

    def test_idempotent_second_run_skipped(self, db):
        factory = _factory(db)
        assert init_insurance_seed_data(factory, physical=False) is True
        assert init_insurance_seed_data(factory, physical=False) is False
        assert _count(db, MetaTable) == 5
        assert _count(db, BusinessTheme) == 4

    def test_tables_are_approved(self, db):
        init_insurance_seed_data(_factory(db), physical=False)
        names = ["policy", "person_customer", "group_customer",
                 "policy_customer_rel", "policy_case"]
        rows = db.execute(select(MetaTable).where(MetaTable.table_name.in_(names))).scalars().all()
        assert len(rows) == 5
        assert all(r.status == "approved" for r in rows)

    def test_themes_bind_expected_main_tables(self, db):
        init_insurance_seed_data(_factory(db), physical=False)
        themes = {t.theme_code: t for t in db.execute(select(BusinessTheme)).scalars().all()}
        table_names = {t.id: t.table_name for t in db.execute(select(MetaTable)).scalars().all()}

        assert set(themes) == {"POLICY_THEME", "PERSON_THEME", "GROUP_THEME", "CASE_THEME"}
        assert table_names[themes["POLICY_THEME"].main_table_id] == "policy"
        assert table_names[themes["PERSON_THEME"].main_table_id] == "person_customer"
        assert table_names[themes["GROUP_THEME"].main_table_id] == "group_customer"
        assert table_names[themes["CASE_THEME"].main_table_id] == "policy_case"

    def test_relations_connect_real_business(self, db):
        init_insurance_seed_data(_factory(db), physical=False)
        tables = {t.id: t.table_name for t in db.execute(select(MetaTable)).scalars().all()}
        fields = {f.id: (tables[f.table_id], f.field_name)
                  for f in db.execute(select(MetaField)).scalars().all()}

        rels = db.execute(select(TableRelation)).scalars().all()
        pairs = {
            (fields[r.left_field_id], fields[r.right_field_id], r.relation_type)
            for r in rels
        }
        assert (("policy", "insured_id"), ("person_customer", "customer_id"), "LEFT") in pairs
        assert (("policy", "policy_holder_id"), ("group_customer", "group_id"), "LEFT") in pairs
        assert (("policy", "policy_id"), ("policy_case", "policy_id"), "LEFT") in pairs

    def test_enums_exist(self, db):
        init_insurance_seed_data(_factory(db), physical=False)
        enums = db.execute(select(FieldEnum)).scalars().all()
        codes = {e.enum_code for e in enums}
        assert {"EFFECTIVE", "LAPSED", "CLAIMED", "PAID", "PERSON"} <= codes
