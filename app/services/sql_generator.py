"""
services/sql_generator.py — 主题 SQL 自动生成器

核心规则：
1. 主题字段（主表主键）作为 SQL 主键，原样出现在 SELECT 中；
2. 标签值字段固定别名 tag_value_code；
3. 根据 table_relations 自动 JOIN，使用 ANSI 通用写法（显式 INNER/LEFT JOIN ... ON）；
4. WHERE 子句可追加枚举过滤条件；
5. 所有表名/字段名来自数据库白名单（防止 SQL 注入）。
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.metadata import MetaTable, MetaField
from app.db.models.relation import TableRelation
from app.db.models.enum_config import FieldEnum
from app.utils.exceptions import BusinessException, ERR_NOT_FOUND, ERR_TAG_SQL_EMPTY, ERR_VALIDATION


class SQLGenerator:
    """
    SQL 生成器（纯函数类，不继承 BaseService，方便单元测试）
    可脱离 Web 独立调用：gen = SQLGenerator(db_session); sql = gen.generate(...)
    """

    def __init__(self, db: Session):
        self.db = db

    # ======================================================================
    # 核心入口：根据标签任务配置生成 SQL
    # ======================================================================
    def generate(self, main_table_id: int, main_field_id: int,
                 tag_value_code: str,
                 extra_relation_ids: Optional[List[int]] = None,
                 enum_filter_field_id: Optional[int] = None,
                 enum_filter_values: Optional[List[str]] = None,
                 extra_select_fields: Optional[List[int]] = None) -> str:
        """
        Args:
            main_table_id:      主表 ID（主题表）
            main_field_id:      标签值字段 ID（存入 tag_value_code 别名）
            tag_value_code:     标签值（字符串）
            extra_relation_ids: 显式选择的关联关系 ID（可选，不传则自动读所有已配置关系）
            enum_filter_field_id: 枚举过滤字段 ID（可选）
            enum_filter_values:  枚举过滤值列表（可选，配合 enum_filter_field_id）
            extra_select_fields: 额外要 SELECT 的字段 ID（可选）

        Returns:
            str: 完整的 SELECT SQL
        """
        # ---------- 1. 读取主表 & 主字段 ----------
        main_table = self.db.get(MetaTable, main_table_id)
        if not main_table:
            raise BusinessException(ERR_NOT_FOUND, f"主表 {main_table_id} 不存在")
        main_field = self.db.get(MetaField, main_field_id)
        if not main_field or main_field.table_id != main_table_id:
            raise BusinessException(ERR_NOT_FOUND, f"字段 {main_field_id} 不属于主表 {main_table_id}")

        # 找到主表的主键字段（SELECT 的首列）
        pk_field = self._find_primary_key(main_table_id)
        if not pk_field:
            raise BusinessException(ERR_TAG_SQL_EMPTY, f"主表 {main_table.table_name} 未定义主键字段")

        # ---------- 2. 收集关联表 ----------
        relations = self._collect_relations(main_table_id, extra_relation_ids)
        joined_tables_ids: set[int] = {main_table_id}
        for r in relations:
            joined_tables_ids.add(r.left_table_id)
            joined_tables_ids.add(r.right_table_id)

        # ---------- 3. SQL 拼装 ----------
        # SELECT 子句
        select_parts = [
            self._quote_ident(main_table.table_name) + "." + self._quote_ident(pk_field.field_name),   # 主键
            f"'{self._escape_sql_string(tag_value_code)}' AS tag_value_code",                           # 固定别名
        ]

        # FROM 子句
        from_clause = self._quote_ident(main_table.table_name)

        # JOIN 子句
        join_clauses = []
        for r in relations:
            left_table = self.db.get(MetaTable, r.left_table_id)
            right_table = self.db.get(MetaTable, r.right_table_id)
            left_field = self.db.get(MetaField, r.left_field_id)
            right_field = self.db.get(MetaField, r.right_field_id)
            if not all([left_table, right_table, left_field, right_field]):
                continue
            join_type = r.relation_type.upper()
            join_sql = (
                f"{join_type} JOIN {self._quote_ident(right_table.table_name)} "
                f"ON {self._quote_ident(left_table.table_name)}.{self._quote_ident(left_field.field_name)} = "
                f"{self._quote_ident(right_table.table_name)}.{self._quote_ident(right_field.field_name)}"
            )
            # 如果关联左表就是 main_table，先把它加进去；否则等它被 join 到时再加
            if r.left_table_id == main_table_id:
                join_clauses.insert(0, join_sql)
            else:
                join_clauses.append(join_sql)

        # WHERE 子句
        where_parts: List[str] = []
        if enum_filter_field_id and enum_filter_values:
            # 校验枚举过滤字段属于某张表
            filter_field = self.db.get(MetaField, enum_filter_field_id)
            if filter_field:
                filter_table = self.db.get(MetaTable, filter_field.table_id)
                if filter_table and filter_table.id in joined_tables_ids:
                    quoted_values = ", ".join(
                        f"'{self._escape_sql_string(v)}'" for v in enum_filter_values
                    )
                    where_parts.append(
                        f"{self._quote_ident(filter_table.table_name)}.{self._quote_ident(filter_field.field_name)}"
                        f" IN ({quoted_values})"
                    )

        # ---------- 4. 最终 SQL ----------
        sql_lines = ["SELECT", "  " + ",\n  ".join(select_parts), f"FROM {from_clause}"]
        sql_lines.extend(join_clauses)
        if where_parts:
            sql_lines.append("WHERE")
            sql_lines.append("  " + " AND ".join(where_parts))

        sql = "\n".join(sql_lines) + ";"
        return sql

    # ======================================================================
    # V1.1 字段配置模式：主题表外层 LEFT JOIN 内层子查询（配置表驱动）
    # ======================================================================
    # 最终结构（PRD §3.8.4 / 方案设计 §5.2）：
    #   SELECT a.<主题表.主键>, b.tag_value_code
    #   FROM <主题表> a
    #   LEFT JOIN (
    #       SELECT <配置表[0]>.FK_to_theme AS <主题表.主键>,
    #              CASE
    #                WHEN <条件1>
    #                [AND|OR <条件2> ...]
    #                THEN '<tag_value_code>'
    #              END AS tag_value_code
    #       FROM <配置表[0]>
    #       [INNER JOIN <配置表1> ON ...]     -- 全部 INNER JOIN
    #   ) b
    #     ON a.<主题表.主键> = b.<主题表.主键>
    #
    # 要点：
    #  - 主题表只出现在外层；内层 FROM = 用户选的第一张配置表（可以是任意表，含主题表）
    #  - 内层 JOIN 起点 = 第一张配置表，BFS 求所有配置表间路径，一律 INNER JOIN
    #  - 内层第一列 = 从 table_relations 反推的「配置表[0] ↔ 主题表」关系里，
    #    配置表[0] 侧的那个字段（命名同主题表主键，供外层 ON）
    #  - 条件链带 AND/OR 前缀；无条件 CASE WHEN 1=1
    # ======================================================================
    def generate_by_fields(self, main_table_id: int, field_config: Optional[dict],
                           tag_value_code: str) -> str:
        """
        field_config 结构：
            {
              "config_tables": [10, 12],            # 配置表 ID 列表，第一张 = 内层 FROM
              "conditions": [
                {"logic": None,   "field_id": 55, "operator": "EQ",      "value": "EFFECTIVE"},
                {"logic": "AND",  "field_id": 78, "operator": "EQ",      "value": "1"},
                {"logic": "OR",   "field_id": 90, "operator": "CONTAINS","value": "高危"},
              ]
            }
        """
        main_table = self.db.get(MetaTable, main_table_id)
        if not main_table:
            raise BusinessException(ERR_NOT_FOUND, f"主题表 {main_table_id} 不存在")
        pk_field = self._find_primary_key(main_table_id)
        if not pk_field:
            raise BusinessException(ERR_TAG_SQL_EMPTY, f"主题表 {main_table.table_name} 未定义主键字段")

        cfg = field_config or {}
        config_tables = cfg.get("config_tables") or []
        conditions_cfg = cfg.get("conditions") or []

        if not config_tables:
            raise BusinessException(ERR_TAG_SQL_EMPTY, "字段配置模式必须至少选择一张配置表")

        # ---------- 1. 加载配置表 ----------
        config_table_objs = []
        for tid in config_tables:
            t = self.db.get(MetaTable, int(tid))
            if not t:
                raise BusinessException(ERR_NOT_FOUND, f"配置表 {tid} 不存在")
            config_table_objs.append(t)

        first_cfg = config_table_objs[0]                   # 内层 FROM
        target_table_ids = {t.id for t in config_table_objs}

        # ---------- 2. 解析条件 ----------
        conditions: List[dict] = []   # {"logic": ..., "table": ..., "field": ..., "op": ..., "values": [...]}
        for item in conditions_cfg:
            field, table = self._resolve_field(item.get("field_id"))
            target_table_ids.add(table.id)
            op = str(item.get("operator") or "").upper()
            if op not in self.OPERATOR_MAP:
                raise BusinessException(ERR_VALIDATION, f"不支持的条件算子: {op}")

            # IS_NULL / IS_NOT_NULL 不需要值
            if op in ("IS_NULL", "IS_NOT_NULL"):
                values = []
            elif op == "IN":
                values = item.get("values")
                if not values:
                    raw = item.get("value")
                    values = [v.strip() for v in str(raw).split(",") if v.strip()] if raw else []
                if not values:
                    raise BusinessException(ERR_VALIDATION, "IN 算子至少需要一个值")
            else:
                raw_value = item.get("value")
                if raw_value is None:
                    raise BusinessException(ERR_VALIDATION, f"算子 {op} 的条件值不能为空")
                values = [raw_value]

            logic = (item.get("logic") or "").strip().upper() or None
            if logic is not None and logic not in ("AND", "OR"):
                raise BusinessException(ERR_VALIDATION, f"逻辑连接只能是 AND 或 OR，收到: {logic}")

            conditions.append({
                "logic": logic, "table": table, "field": field,
                "op": op, "values": values,
            })

        # ---------- 3. 反推：配置表[0] 连到主题表主键的那个字段 ----------
        fk_field = self._resolve_fk_to_theme(first_cfg.id, main_table_id)
        fk_alias = pk_field.field_name   # 内层第一列别名，供外层 ON 使用

        # ---------- 4. 内层子查询 JOIN 链（从配置表[0] BFS） ----------
        inner_join_clauses = self._build_inner_join_clauses(first_cfg.id, target_table_ids)

        # ---------- 5. CASE WHEN ----------
        case_expr = self._build_case_when_with_logic(conditions, tag_value_code)

        # ---------- 6. 组装内层 SQL ----------
        qt = self._quote_ident
        inner_lines = [
            "SELECT",
            f"  {qt(first_cfg.table_name)}.{qt(fk_field.field_name)} AS {qt(fk_alias)}",
            f"  ,{case_expr}",
            f"FROM {qt(first_cfg.table_name)}",
        ]
        inner_lines.extend(inner_join_clauses)
        inner_sql = "\n".join(inner_lines)

        # ---------- 7. 外层 SQL ----------
        outer_lines = [
            "SELECT",
            f"  a.{qt(pk_field.field_name)}",
            f"  ,b.tag_value_code",
            f"FROM {qt(main_table.table_name)} a",
            "LEFT JOIN (",
        ]
        for line in inner_sql.split("\n"):
            outer_lines.append("    " + line)
        outer_lines.append("  ) b")
        outer_lines.append(
            f"  ON a.{qt(pk_field.field_name)} = b.{qt(fk_alias)}"
        )

        return "\n".join(outer_lines) + ";"

    # ======================================================================
    # 子查询辅助（配置表驱动版）
    # ======================================================================
    def _resolve_fk_to_theme(self, first_cfg_table_id: int, main_table_id: int) -> MetaField:
        """
        从 table_relations 里找到「配置表[0] ↔ 主题表」的那条关系，
        返回配置表[0] 侧的字段（作为内层第一列，用于外层 ON）。

        若配置表[0] 就是主题表本身，直接返回主题表主键字段。
        """
        if first_cfg_table_id == main_table_id:
            return self._find_primary_key(main_table_id)

        relations = self.db.execute(
            select(TableRelation).where(
                ((TableRelation.left_table_id == first_cfg_table_id)
                 & (TableRelation.right_table_id == main_table_id))
                |
                ((TableRelation.right_table_id == first_cfg_table_id)
                 & (TableRelation.left_table_id == main_table_id))
            )
        ).scalars().all()

        for r in relations:
            if r.left_table_id == first_cfg_table_id:
                return self.db.get(MetaField, r.left_field_id)
            else:
                return self.db.get(MetaField, r.right_field_id)

        raise BusinessException(
            ERR_VALIDATION,
            f"配置表 {first_cfg_table_id} 与主题表 {main_table_id} 之间未配置关联关系，无法反推连接键"
        )

    def _build_inner_join_clauses(self, first_cfg_table_id: int,
                                  target_table_ids: set) -> List[str]:
        """
        以 first_cfg_table_id 为起点 BFS，生成所有配置表间的 INNER JOIN 链。
        """
        from collections import deque

        # 去掉起点自己
        remaining = target_table_ids - {first_cfg_table_id}
        if not remaining:
            return []

        relations = self.db.execute(
            select(TableRelation).order_by(TableRelation.id)
        ).scalars().all()

        adj: dict = {}
        for r in relations:
            adj.setdefault(r.left_table_id, []).append((r.right_table_id, r, False))
            adj.setdefault(r.right_table_id, []).append((r.left_table_id, r, True))

        prev: dict = {first_cfg_table_id: None}
        order: List[int] = []
        queue = deque([first_cfg_table_id])
        while queue:
            cur = queue.popleft()
            for nxt, rel, reversed_ in adj.get(cur, []):
                if nxt in prev:
                    continue
                prev[nxt] = (cur, rel, reversed_)
                order.append(nxt)
                queue.append(nxt)

        unreachable = remaining - set(prev)
        if unreachable:
            names = []
            for tid in unreachable:
                t = self.db.get(MetaTable, tid)
                names.append(t.table_name if t else f"#{tid}")
            raise BusinessException(
                ERR_VALIDATION,
                "以下配置表无法从首张配置表通过表关系连通: " + ", ".join(names),
            )

        needed: set = set()
        for tid in remaining:
            cur = tid
            while cur is not None and cur != first_cfg_table_id:
                needed.add(cur)
                cur = prev[cur][0]

        clauses: List[str] = []
        for tid in order:
            if tid not in needed:
                continue
            parent_id, rel, reversed_ = prev[tid]
            drive_table = self.db.get(MetaTable, parent_id)
            join_table = self.db.get(MetaTable, tid)
            l_field = self.db.get(MetaField, rel.left_field_id)
            r_field = self.db.get(MetaField, rel.right_field_id)
            if not all([drive_table, join_table, l_field, r_field]):
                continue

            clauses.append(
                f"INNER JOIN {self._quote_ident(join_table.table_name)} "
                f"ON {self._quote_ident(drive_table.table_name)}.{self._quote_ident(l_field.field_name)} = "
                f"{self._quote_ident(join_table.table_name)}.{self._quote_ident(r_field.field_name)}"
            )
        return clauses

    def _build_case_when_with_logic(self, conditions: List[dict], tag_value_code: str) -> str:
        """
        把 conditions（带 logic 前缀）渲染成 CASE WHEN <条件链> THEN '<tag>' END AS tag_value_code。
        无条件回退 CASE WHEN 1=1 THEN '<tag>' END。
        """
        escaped = self._escape_sql_string(tag_value_code)
        if not conditions:
            return f"CASE WHEN 1=1 THEN '{escaped}' END AS tag_value_code"

        rendered: List[str] = []
        for c in conditions:
            prefix = c["logic"]          # None / "AND" / "OR"
            fragment = self._render_condition(c["table"], c["field"], c["op"], c["values"])
            if prefix and rendered:
                rendered.append(prefix)
            rendered.append(fragment)

        return (
            "CASE WHEN "
            + " ".join(rendered)
            + f" THEN '{escaped}' END AS tag_value_code"
        )

    # 条件算子 → 渲染方法（13 种）
    OPERATOR_MAP = (
        "EQ", "NEQ",                                  # 等于 / 不等于
        "CONTAINS", "NOT_CONTAINS",                   # 包含 / 不包含
        "STARTS_WITH", "ENDS_WITH",                   # 开头 / 结尾
        "IN",                                         # 集合内
        "GT", "LT", "GTE", "LTE",                     # > < >= <=
        "IS_NULL", "IS_NOT_NULL",                     # 为空 / 非空（不需要值）
    )

    def _resolve_field(self, field_id) -> tuple:
        """校验并返回 (MetaField, MetaTable)"""
        try:
            fid = int(field_id)
        except (TypeError, ValueError):
            raise BusinessException(ERR_VALIDATION, "字段配置中的 field_id 非法")
        field = self.db.get(MetaField, fid)
        if not field:
            raise BusinessException(ERR_NOT_FOUND, f"字段 {fid} 不存在")
        table = self.db.get(MetaTable, field.table_id)
        if not table:
            raise BusinessException(ERR_NOT_FOUND, f"字段 {fid} 所属表不存在")
        return field, table

    def _build_join_clauses(self, main_table_id: int, target_table_ids: set) -> List[str]:
        """
        以主题表为起点，把 table_relations 视为无向图做 BFS，
        仅为主题表到目标表路径上的节点生成显式 JOIN。
        """
        from collections import deque

        relations = self.db.execute(
            select(TableRelation).order_by(TableRelation.id)
        ).scalars().all()

        adj: dict = {}
        for r in relations:
            adj.setdefault(r.left_table_id, []).append((r.right_table_id, r, False))
            adj.setdefault(r.right_table_id, []).append((r.left_table_id, r, True))

        prev: dict = {main_table_id: None}
        order: List[int] = []
        queue = deque([main_table_id])
        while queue:
            cur = queue.popleft()
            for nxt, rel, reversed_ in adj.get(cur, []):
                if nxt in prev:
                    continue
                prev[nxt] = (cur, rel, reversed_)
                order.append(nxt)
                queue.append(nxt)

        unreachable = target_table_ids - set(prev)
        if unreachable:
            names = []
            for tid in unreachable:
                t = self.db.get(MetaTable, tid)
                names.append(t.table_name if t else f"#{tid}")
            raise BusinessException(
                ERR_VALIDATION,
                "以下表无法从主题表通过表关系连通: " + ", ".join(names),
            )

        # 只保留目标表路径上的节点
        needed: set = set()
        for tid in target_table_ids:
            cur = tid
            while cur is not None and cur != main_table_id:
                needed.add(cur)
                cur = prev[cur][0]

        clauses: List[str] = []
        for tid in order:
            if tid not in needed:
                continue
            parent_id, rel, reversed_ = prev[tid]
            drive_table = self.db.get(MetaTable, parent_id)
            join_table = self.db.get(MetaTable, tid)
            l_field = self.db.get(MetaField, rel.left_field_id)
            r_field = self.db.get(MetaField, rel.right_field_id)
            if not all([drive_table, join_table, l_field, r_field]):
                continue

            join_type = rel.relation_type.upper()
            if reversed_:
                # 反向遍历：左右互换，LEFT/RIGHT 语义互换
                join_type = {"LEFT": "RIGHT", "RIGHT": "LEFT"}.get(join_type, join_type)

            clauses.append(
                f"{join_type} JOIN {self._quote_ident(join_table.table_name)} "
                f"ON {self._quote_ident(drive_table.table_name)}.{self._quote_ident(l_field.field_name)} = "
                f"{self._quote_ident(join_table.table_name)}.{self._quote_ident(r_field.field_name)}"
            )
        return clauses

    def _render_condition(self, table: MetaTable, field: MetaField,
                          op: str, values: List) -> str:
        """按算子渲染条件片段（13 种）"""
        col = f"{self._quote_ident(table.table_name)}.{self._quote_ident(field.field_name)}"

        if op == "IN":
            quoted = ", ".join(self._value_sql(v) for v in values)
            return f"{col} IN ({quoted})"

        if op == "IS_NULL":
            return f"{col} IS NULL"
        if op == "IS_NOT_NULL":
            return f"{col} IS NOT NULL"

        raw = str(values[0])
        if op == "EQ":
            return f"{col} = {self._value_sql(values[0])}"
        if op == "NEQ":
            return f"{col} <> {self._value_sql(values[0])}"
        if op == "GT":
            return f"{col} > {self._value_sql(values[0])}"
        if op == "LT":
            return f"{col} < {self._value_sql(values[0])}"
        if op == "GTE":
            return f"{col} >= {self._value_sql(values[0])}"
        if op == "LTE":
            return f"{col} <= {self._value_sql(values[0])}"

        escaped = self._escape_like(raw)
        if op == "CONTAINS":
            return f"{col} LIKE '%{escaped}%' ESCAPE '\\'"
        if op == "NOT_CONTAINS":
            return f"{col} NOT LIKE '%{escaped}%' ESCAPE '\\'"
        if op == "STARTS_WITH":
            return f"{col} LIKE '{escaped}%' ESCAPE '\\'"
        # ENDS_WITH
        return f"{col} LIKE '%{escaped}' ESCAPE '\\'"

    @staticmethod
    def _value_sql(value) -> str:
        """SQL 字面量：仅 int/float/bool 按数值写，其余一律加单引号"""
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        # 字符串一律加引号（包括内容为数字的字符串，避免 VARCHAR 字段隐式类型转换）
        text = str(value)
        return f"'{text.replace(chr(39), chr(39) * 2)}'"

    @classmethod
    def _escape_like(cls, value: str) -> str:
        """LIKE 值转义：单引号 + % _ 通配符（配合 ESCAPE '\\'）"""
        return (value
                .replace("\\", "\\\\")
                .replace("'", "''")
                .replace("%", "\\%")
                .replace("_", "\\_"))

    @staticmethod
    def _safe_alias(alias, fallback: str) -> str:
        """别名白名单校验，非法则回退字段名"""
        text = str(alias).strip() if alias else ""
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
        if text and len(text) <= 128 and all(c in safe_chars for c in text):
            return text
        return fallback

    # ======================================================================
    # 辅助方法
    # ======================================================================
    def _collect_relations(self, main_table_id: int, explicit_ids: Optional[List[int]]) -> List[TableRelation]:
        """收集与主表相关的关联规则"""
        if explicit_ids:
            # 使用指定的关联
            stmt = select(TableRelation).where(TableRelation.id.in_(explicit_ids))
            return self.db.execute(stmt).scalars().all()

        # 自动收集：以主表为一端的所有关系
        stmt = select(TableRelation).where(
            (TableRelation.left_table_id == main_table_id) |
            (TableRelation.right_table_id == main_table_id)
        ).order_by(TableRelation.id)
        return self.db.execute(stmt).scalars().all()

    def _find_primary_key(self, table_id: int) -> Optional[MetaField]:
        """从字段列表中找主键字段"""
        stmt = select(MetaField).where(
            MetaField.table_id == table_id,
            MetaField.is_primary_key == True,  # noqa: E712
        ).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def _quote_ident(name: str) -> str:
        """
        标识符引用（防止 SQL 注入 + 兼容关键字）。
        SQLite 用双引号；Spark SQL 也支持双引号。
        """
        # 安全检查：标识符只能包含字母、数字、下划线
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
        if not all(c in safe_chars for c in name):
            raise ValueError(f"不合法的标识符: {name}")
        return f'"{name}"'

    @staticmethod
    def _escape_sql_string(value: str) -> str:
        """SQL 字符串字面量转义"""
        return value.replace("'", "''")
