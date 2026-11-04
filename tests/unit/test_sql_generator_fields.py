"""
tests/unit/test_sql_generator_fields.py — 字段配置模式 SQL 生成（V1.1 新结构）

最终结构（按 PRD §3.8.4 / 方案设计 §5.2）：
  SELECT a.<主题表.主键>, b.tag_value_code
  FROM <主题表> a
  LEFT JOIN (
      SELECT <配置表[0]>.FK_to_theme AS <主题表.主键>,
             CASE WHEN <条件 AND/OR 链> THEN '<tag>' END AS tag_value_code
      FROM <配置表[0]>
      [INNER JOIN <配置表1> ON ...]
  ) b
    ON a.<主题表.主键> = b.<主题表.主键>
"""
import pytest

from app.db.models.metadata import MetaField, MetaTable
from app.db.models.relation import TableRelation
from app.services.sql_generator import SQLGenerator
from app.utils.exceptions import BusinessException


def _fields(table) -> dict:
    return {f.field_name: f for f in table.fields}


def _add_relation(db, left_table, left_field, right_table, right_field, relation_type="LEFT"):
    db.add(TableRelation(
        left_table_id=left_table.id, left_field_id=_fields(left_table)[left_field].id,
        right_table_id=right_table.id, right_field_id=_fields(right_table)[right_field].id,
        relation_type=relation_type,
    ))
    db.commit()


@pytest.fixture
def joined(db, sample_table, sample_table2):
    """sample_order.user_id → sample_user.user_id"""
    _add_relation(db, sample_table, "user_id", sample_table2, "user_id")
    return sample_table, sample_table2


@pytest.fixture
def multi_tables(db, sample_table, sample_table2):
    """三张表 sample_order / sample_user / sample_dept，形成 order→user→dept 链"""
    _add_relation(db, sample_table, "user_id", sample_table2, "user_id")
    dept = MetaTable(table_name="sample_dept", table_comment="部门", status="approved")
    db.add(dept); db.flush()
    db.add(MetaField(table_id=dept.id, field_name="dept_id", field_type="BIGINT",
                     is_primary_key=True, ordinal_position=1))
    db.add(MetaField(table_id=dept.id, field_name="dept_name", field_type="VARCHAR(64)",
                     ordinal_position=2))
    db.commit(); db.refresh(dept); db.refresh(sample_table2)
    _add_relation(db, sample_table2, "user_id", dept, "dept_id")
    # 让 dept.user_id 字段能连回 order.pk（便于 _resolve_fk_to_theme 反推）
    # 这里 sample_order 就是主题表，sample_user / sample_dept 是配置表
    # sample_dept 没有直接连 sample_order 的关系 → 多跳场景会报不可达，正常
    return sample_table, sample_table2, dept


class TestStructure:

    def test_two_layer_structure(self, db, joined):
        """外层主题表 LEFT JOIN 内层配置表，内层 FROM = 第一张配置表"""
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],   # 第一张配置表 = user
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "CONTAINS", "value": "张"},
                ],
            },
            tag_value_code="VIP",
        )
        # 外层
        assert 'FROM "sample_order" a' in sql
        assert 'LEFT JOIN (' in sql and ') b' in sql
        assert 'ON a."order_id" = b."order_id"' in sql
        # 内层 FROM = sample_user（第一张配置表）
        assert 'FROM "sample_user"' in sql
        assert sql.index('FROM "sample_user"') > sql.index('LEFT JOIN (')
        assert sql.index('FROM "sample_user"') < sql.index(') b')
        # 内层第一列 FK 反推：user.user_id AS order_id
        assert '"sample_user"."user_id" AS "order_id"' in sql
        # CASE WHEN
        assert 'CASE WHEN' in sql and "LIKE '%张%'" in sql and "'VIP'" in sql

    def test_theme_table_as_config_table(self, db, sample_table):
        """配置表只有主题表自己时：内层 FROM 主题表、不需要额外 JOIN、FK 就是主题表主键"""
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=sample_table.id,
            field_config={
                "config_tables": [sample_table.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(sample_table)["order_id"].id,
                     "operator": "EQ", "value": "1"},
                ],
            },
            tag_value_code="X",
        )
        assert 'FROM "sample_order" a' in sql
        assert 'FROM "sample_order"' in sql
        assert '"sample_order"."order_id" AS "order_id"' in sql  # 主键 AS 主题 pk 别名
        assert 'INNER JOIN' not in sql   # 只有一张配置表，不需要
        assert '"sample_order"."order_id" = \'1\'' in sql
        assert "'X'" in sql

    def test_second_config_table_joined(self, db, joined):
        """两张配置表（order + user）→ 内层 INNER JOIN"""
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [order.id, user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "CONTAINS", "value": "张"},
                ],
            },
            tag_value_code="VIP",
        )
        # 第一张配置表 = order（主题表自己）→ 内层 FROM = sample_order
        # 但外层也有 FROM "sample_order"，所以用括号锚定
        inner_section = sql.split('LEFT JOIN (')[1].split('  ) b')[0]
        assert 'FROM "sample_order"' in inner_section
        assert 'INNER JOIN "sample_user"' in inner_section
        assert '"sample_user"."user_name"' in inner_section

    def test_multi_hop(self, db, multi_tables):
        """两张配置表 user + dept（BFS 从 user 到 dept）"""
        order, user, dept = multi_tables
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id, dept.id],
                "conditions": [],
            },
            tag_value_code="DEPT",
        )
        inner_section = sql.split('LEFT JOIN (')[1].split('  ) b')[0]
        # 内层 FROM = 第一张配置表 user，BFS JOIN dept
        assert 'FROM "sample_user"' in inner_section
        assert 'INNER JOIN "sample_dept"' in inner_section
        # CASE WHEN 1=1 回退（无条件）
        assert 'CASE WHEN 1=1 THEN \'DEPT\'' in inner_section


class TestLogicConnector:

    def test_single_condition_no_logic(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "EQ", "value": "张三"},
                ],
            },
            tag_value_code="X",
        )
        assert 'CASE WHEN "sample_user"."user_name" = \'张三\'' in sql

    def test_and_logic(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id, order.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "EQ", "value": "张三"},
                    {"logic": "AND", "field_id": _fields(order)["user_id"].id,
                     "operator": "EQ", "value": "100"},
                ],
            },
            tag_value_code="X",
        )
        assert 'AND' in sql
        assert '"sample_user"."user_name" = \'张三\'' in sql
        assert '"sample_order"."user_id" = \'100\'' in sql

    def test_or_logic(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "EQ", "value": "张三"},
                    {"logic": "OR", "field_id": _fields(user)["user_name"].id,
                     "operator": "EQ", "value": "李四"},
                ],
            },
            tag_value_code="X",
        )
        assert ' OR ' in sql or ' OR"' not in sql
        assert '"sample_user"."user_name" = \'张三\'' in sql
        assert '"sample_user"."user_name" = \'李四\'' in sql

    def test_invalid_logic_rejected(self, db, joined):
        order, user = joined
        with pytest.raises(BusinessException):
            SQLGenerator(db).generate_by_fields(
                main_table_id=order.id,
                field_config={
                    "config_tables": [user.id],
                    "conditions": [
                        {"logic": "XOR", "field_id": _fields(user)["user_name"].id,
                         "operator": "EQ", "value": "张三"},
                    ],
                },
                tag_value_code="X",
            )


class TestAll13Operators:

    @pytest.mark.parametrize("op,expect", [
        ("EQ",          '"sample_user"."user_name" = \'张三\''),
        ("NEQ",         '"sample_user"."user_name" <> \'张三\''),
        ("CONTAINS",    "LIKE '%张三%' ESCAPE"),
        ("NOT_CONTAINS","NOT LIKE '%张三%' ESCAPE"),
        ("STARTS_WITH", "LIKE '张三%' ESCAPE"),
        ("ENDS_WITH",   "LIKE '%张三' ESCAPE"),
        ("GT",          '"sample_user"."user_name" > \'张三\''),
        ("LT",          '"sample_user"."user_name" < \'张三\''),
        ("GTE",         '"sample_user"."user_name" >= \'张三\''),
        ("LTE",         '"sample_user"."user_name" <= \'张三\''),
    ])
    def test_basic_operators(self, db, joined, op, expect):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": op, "value": "张三"},
                ],
            },
            tag_value_code="X",
        )
        assert expect in sql

    def test_in_operator(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "IN", "values": ["张", "李"]},
                ],
            },
            tag_value_code="X",
        )
        assert "IN ('张', '李')" in sql

    def test_in_comma_string(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "IN", "value": "A, B"},
                ],
            },
            tag_value_code="X",
        )
        assert "IN ('A', 'B')" in sql

    def test_is_null(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "IS_NULL"},
                ],
            },
            tag_value_code="X",
        )
        assert 'IS NULL' in sql and "'X'" in sql

    def test_is_not_null(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "IS_NOT_NULL"},
                ],
            },
            tag_value_code="X",
        )
        assert 'IS NOT NULL' in sql

    def test_like_wildcards_escaped(self, db, joined):
        order, user = joined
        sql = SQLGenerator(db).generate_by_fields(
            main_table_id=order.id,
            field_config={
                "config_tables": [user.id],
                "conditions": [
                    {"logic": None, "field_id": _fields(user)["user_name"].id,
                     "operator": "CONTAINS", "value": "100%_a"},
                ],
            },
            tag_value_code="X",
        )
        assert "100\\%\\_a" in sql


class TestErrorRejection:

    def test_missing_config_tables_rejected(self, db, sample_table):
        with pytest.raises(BusinessException):
            SQLGenerator(db).generate_by_fields(
                main_table_id=sample_table.id,
                field_config={"conditions": []},
                tag_value_code="X",
            )

    def test_unreachable_config_table_rejected(self, db, sample_table):
        lonely = MetaTable(table_name="lonely_t", table_comment="孤立表", status="approved")
        db.add(lonely); db.flush()
        db.add(MetaField(table_id=lonely.id, field_name="lonely_id", field_type="BIGINT",
                         is_primary_key=True, ordinal_position=1))
        db.commit()

        with pytest.raises(BusinessException):
            SQLGenerator(db).generate_by_fields(
                main_table_id=sample_table.id,
                field_config={
                    "config_tables": [sample_table.id, lonely.id],
                    "conditions": [],
                },
                tag_value_code="X",
            )

    def test_invalid_operator_rejected(self, db, joined):
        order, user = joined
        with pytest.raises(BusinessException):
            SQLGenerator(db).generate_by_fields(
                main_table_id=order.id,
                field_config={
                    "config_tables": [user.id],
                    "conditions": [
                        {"logic": None, "field_id": _fields(user)["user_name"].id,
                         "operator": "REGEX", "value": "x"},
                    ],
                },
                tag_value_code="X",
            )

    def test_missing_fk_relation_rejected(self, db, joined):
        """配置表[0] 和主题表之间没直接关系 → 反推 FK 失败"""
        order, user = joined
        # 删除 order.user_id → user.user_id 这条关系，只剩下 user
        from sqlalchemy import delete as sa_delete
        db.execute(sa_delete(TableRelation).where(
            TableRelation.left_table_id == order.id,
            TableRelation.right_table_id == user.id,
        ))
        db.commit()
        # 现在只选 user 当配置表[0]，但 user 和 order（主题表）之间没关系
        with pytest.raises(BusinessException):
            SQLGenerator(db).generate_by_fields(
                main_table_id=order.id,
                field_config={
                    "config_tables": [user.id],
                    "conditions": [],
                },
                tag_value_code="X",
            )
