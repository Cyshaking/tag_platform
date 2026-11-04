"""
tests/unit/test_sql_generator.py — 主题 SQL 生成器测试
"""
import pytest
from sqlalchemy.orm import Session

from app.db.models.metadata import MetaTable, MetaField
from app.db.models.relation import TableRelation
from app.db.models.enum_config import FieldEnum
from app.services.sql_generator import SQLGenerator
from app.utils.exceptions import BusinessException


class TestSQLGenerator:
    """SQL 生成器核心逻辑"""

    def test_single_table_simple(self, db: Session, sample_table):
        """单表：主键 + tag_value_code"""
        gen = SQLGenerator(db)
        sql = gen.generate(
            main_table_id=sample_table.id,
            main_field_id=sample_table.fields[1].id,  # user_id 字段
            tag_value_code="vip_user",
        )
        assert "sample_order" in sql
        assert "tag_value_code" in sql
        assert "'vip_user'" in sql
        # 主键 order_id 必须出现在 SELECT
        assert '"order_id"' in sql

    def test_two_table_join(self, db: Session, sample_table, sample_table2):
        """两表 INNER JOIN"""
        # 创建关联
        db.add(TableRelation(
            left_table_id=sample_table.id, left_field_id=sample_table.fields[1].id,  # order.user_id
            right_table_id=sample_table2.id, right_field_id=sample_table2.fields[0].id,  # user.user_id
            relation_type="INNER",
        ))
        db.commit()

        gen = SQLGenerator(db)
        sql = gen.generate(
            main_table_id=sample_table.id,
            main_field_id=sample_table.fields[1].id,
            tag_value_code="high_value",
        )
        assert "INNER JOIN" in sql
        assert "sample_user" in sql
        assert "sample_order" in sql

    def test_missing_pk_raises(self, db: Session):
        """主表无主键 → 抛异常"""
        t = MetaTable(table_name="no_pk_table")
        db.add(t); db.flush()
        db.add(MetaField(table_id=t.id, field_name="f1", field_type="INT"))
        db.commit()

        gen = SQLGenerator(db)
        with pytest.raises(BusinessException) as exc:
            gen.generate(t.id, t.id, "x")
        assert "未定义主键" in str(exc.value.message)

    def test_invalid_identifier_rejected(self, db: Session, sample_table):
        """手动测试 _quote_ident 安全检查"""
        gen = SQLGenerator(db)
        # 特殊字符不合法
        with pytest.raises(ValueError):
            gen._quote_ident("bad;name")
        with pytest.raises(ValueError):
            gen._quote_ident("a.b")
        with pytest.raises(ValueError):
            gen._quote_ident("x y")
        # 合法通过
        assert gen._quote_ident("good_table") == '"good_table"'
        assert gen._quote_ident("_t1") == '"_t1"'

    def test_sql_string_escape(self, db: Session, sample_table):
        """单引号转义"""
        gen = SQLGenerator(db)
        sql = gen.generate(
            main_table_id=sample_table.id,
            main_field_id=sample_table.fields[0].id,
            tag_value_code="it's_vip",
        )
        assert "''" in sql  # 单引号被转义

    def test_explicit_relation_ids(self, db: Session, sample_table, sample_table2):
        """指定 relation_ids 时只使用指定的关联"""
        rel = TableRelation(
            left_table_id=sample_table.id, left_field_id=sample_table.fields[1].id,
            right_table_id=sample_table2.id, right_field_id=sample_table2.fields[0].id,
            relation_type="LEFT",
        )
        db.add(rel); db.commit()

        gen = SQLGenerator(db)
        # 不指定 → 自动收集到关联
        sql_auto = gen.generate(sample_table.id, sample_table.fields[1].id, "x")
        assert "LEFT JOIN" in sql_auto

        # 指定不存在的 id → 不使用任何关联
        sql_explicit = gen.generate(sample_table.id, sample_table.fields[1].id, "x",
                                    extra_relation_ids=[99999])
        assert "JOIN" not in sql_explicit.upper()

    def test_null_byte_filter(self, db: Session, sample_table):
        """枚举过滤"""
        db.add(FieldEnum(table_id=sample_table.id, field_id=sample_table.fields[1].id,
                          enum_code="BEIJING", enum_label="北京", ordinal=0))
        db.add(FieldEnum(table_id=sample_table.id, field_id=sample_table.fields[1].id,
                          enum_code="SHANGHAI", enum_label="上海", ordinal=1))
        db.commit()

        gen = SQLGenerator(db)
        sql = gen.generate(
            main_table_id=sample_table.id,
            main_field_id=sample_table.fields[1].id,
            tag_value_code="city_tag",
            enum_filter_field_id=sample_table.fields[1].id,
            enum_filter_values=["BEIJING"],
        )
        assert "WHERE" in sql.upper()
        assert "BEIJING" in sql
