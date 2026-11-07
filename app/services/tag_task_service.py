"""
services/tag_task_service.py — 标签任务配置（V1.1 双模式）

task_mode=FIELD：多表多字段 + 条件配置 → SQLGenerator.generate_by_fields
task_mode=SQL  ：用户直配 SQL → SQLValidator 校验 → 直接执行
两种模式的主表恒等于业务主题绑定的主题表。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tag_task import TagTask, TaskExecuteRecord
from app.db.models.metadata import MetaTable, MetaField
from app.db.models.datasource import Datasource
from app.services.base import BaseService
from app.services.sql_generator import SQLGenerator
from app.services.sql_validator import SQLValidator
from app.services.theme_service import ThemeService
from app.utils.exceptions import (
    BusinessException, ERR_NOT_FOUND, ERR_DS_DISABLED, ERR_TAG_SQL_EMPTY, ERR_VALIDATION,
)

_VALID_MODES = ("FIELD", "SQL")


class TagTaskService(BaseService):
    MODULE = "tag_task"

    def list_tasks(self) -> List[TagTask]:
        return self.db.execute(select(TagTask).order_by(TagTask.id.desc())).scalars().all()

    def get_task(self, task_id: int) -> Optional[TagTask]:
        return self.db.get(TagTask, task_id)

    # ==================================================================
    # 创建
    # ==================================================================
    def create_task(self, task_name: str, business_theme: Optional[str] = None,
                    main_table_id: Optional[int] = None, main_field_id: Optional[int] = None,
                    tag_value_code: Optional[str] = None, datasource_id: int = None,
                    created_by: Optional[int] = None,
                    task_mode: str = "FIELD", theme_id: Optional[int] = None,
                    raw_sql: Optional[str] = None,
                    field_config: Optional[Dict[str, Any]] = None) -> TagTask:
        task_mode = (task_mode or "FIELD").upper()
        if task_mode not in _VALID_MODES:
            raise BusinessException(ERR_VALIDATION, f"不支持的任务模式: {task_mode}")

        self._validate_datasource(datasource_id)

        # ---------- 业务主题：主表强制取主题表 ----------
        if theme_id is not None:
            theme = ThemeService(self.db).get_theme(theme_id)
            if not theme:
                raise BusinessException(ERR_NOT_FOUND, f"业务主题 {theme_id} 不存在")
            main_table_id = theme.main_table_id
            business_theme = theme.theme_name
        else:
            # 兼容 V1.0：未选主题时沿用主表配置
            if not main_table_id or not main_field_id:
                raise BusinessException(ERR_VALIDATION, "必须选择业务主题或指定主表/主字段")

        generator = SQLGenerator(self.db)
        config_json: Optional[str] = None

        if task_mode == "SQL":
            # ---------- SQL 直配模式 ----------
            result = SQLValidator(self.db).validate(raw_sql or "", datasource_id)
            if not result["valid"]:
                raise BusinessException(ERR_TAG_SQL_EMPTY, result["message"])
            normalized_sql = result["normalized_sql"]
            pk_field = generator._find_primary_key(main_table_id)
            if not pk_field:
                raise BusinessException(ERR_TAG_SQL_EMPTY, "主题表未定义主键字段")
            main_field_id = pk_field.id
            tag_value_code = tag_value_code or task_name
            generated_sql = normalized_sql
            raw_sql = normalized_sql
        else:
            # ---------- 字段配置模式 ----------
            if theme_id is not None:
                if not field_config:
                    raise BusinessException(ERR_VALIDATION, "字段配置模式至少需要选择一个字段")
                tag_value_code = tag_value_code or task_name
                generated_sql = generator.generate_by_fields(
                    main_table_id=main_table_id,
                    field_config=field_config,
                    tag_value_code=tag_value_code,
                )
                pk_field = generator._find_primary_key(main_table_id)
                if not pk_field:
                    raise BusinessException(ERR_TAG_SQL_EMPTY, "主题表未定义主键字段")
                main_field_id = pk_field.id
                config_json = json.dumps(
                    {**field_config, "tag_value_code": tag_value_code},
                    ensure_ascii=False,
                )
            else:
                # 兼容 V1.0：传统单表生成
                if not tag_value_code:
                    raise BusinessException(ERR_VALIDATION, "标签值编码不能为空")
                self._validate_main_table(main_table_id, main_field_id)
                generated_sql = generator.generate(
                    main_table_id=main_table_id,
                    main_field_id=main_field_id,
                    tag_value_code=tag_value_code,
                )

        task = TagTask(
            task_name=task_name,
            task_mode=task_mode,
            theme_id=theme_id,
            business_theme=business_theme or "",
            main_table_id=main_table_id,
            main_field_id=main_field_id,
            tag_value_code=tag_value_code,
            raw_sql=raw_sql if task_mode == "SQL" else None,
            field_config_json=config_json,
            datasource_id=datasource_id,
            generated_sql=generated_sql,
            created_by=created_by,
        )
        task.serial_no = self._gen_serial_no(TagTask, "TAG")  # V1.4.3
        self.db.add(task)
        self.db.flush()  # 先 flush 拿到 task.id，再写 action_log
        self._log_action("CREATE", "TAG_TASK", task.id, task_name,
                         detail=f"模式={task_mode}, 生成SQL长度={len(generated_sql)}",
                         user_id=created_by)
        self.db.commit()
        self._log_info(f"创建标签任务 {task_name}（{task_mode} 模式），生成 SQL {len(generated_sql)} 字符", created_by)
        return task

    # ==================================================================
    # 更新
    # ==================================================================
    def update_task(self, task_id: int, task_name: Optional[str] = None,
                    business_theme: Optional[str] = None,
                    tag_value_code: Optional[str] = None,
                    datasource_id: Optional[int] = None,
                    operator_id: Optional[int] = None,
                    raw_sql: Optional[str] = None,
                    field_config: Optional[Dict[str, Any]] = None) -> TagTask:
        task = self.db.get(TagTask, task_id)
        if not task:
            raise BusinessException(ERR_NOT_FOUND, f"标签任务 {task_id} 不存在")

        if task_name is not None:
            task.task_name = task_name
        if business_theme is not None:
            task.business_theme = business_theme
        if tag_value_code is not None:
            task.tag_value_code = tag_value_code
        if datasource_id is not None:
            self._validate_datasource(datasource_id)
            task.datasource_id = datasource_id

        generator = SQLGenerator(self.db)
        sql_changed = False  # V1.4.3：追踪 SQL 相关字段是否变更
        if task.task_mode == "SQL" and raw_sql is not None:
            result = SQLValidator(self.db).validate(raw_sql, task.datasource_id)
            if not result["valid"]:
                raise BusinessException(ERR_TAG_SQL_EMPTY, result["message"])
            task.raw_sql = result["normalized_sql"]
            task.generated_sql = result["normalized_sql"]
            sql_changed = True
        elif task.task_mode == "FIELD" and field_config is not None:
            task.field_config_json = json.dumps(field_config, ensure_ascii=False)
            task.generated_sql = generator.generate_by_fields(
                main_table_id=task.main_table_id,
                field_config=field_config,
                tag_value_code=task.tag_value_code,
            )
            sql_changed = True
        elif tag_value_code is not None or datasource_id is None:
            # 标签值变更：按模式重新生成 SQL
            if task.task_mode == "SQL":
                if task.raw_sql:
                    task.generated_sql = task.raw_sql
            elif task.field_config_json:
                task.generated_sql = generator.generate_by_fields(
                    main_table_id=task.main_table_id,
                    field_config=json.loads(task.field_config_json),
                    tag_value_code=task.tag_value_code,
                )
            else:
                task.generated_sql = generator.generate(
                    main_table_id=task.main_table_id,
                    main_field_id=task.main_field_id,
                    tag_value_code=task.tag_value_code,
                )
            sql_changed = True

        # V1.4.3 例外 (a)：修改 raw_sql / field_config / generated_sql 后重置为 pending，让执行门禁自然拦截
        if sql_changed and task.status in ("approved", "rejected"):
            task.status = "pending"

        task.updated_at = datetime.utcnow()
        self._log_action("UPDATE", "TAG_TASK", task.id, task.task_name,
                         detail=("SQL 变更, 状态重置为 pending" if sql_changed else "基本信息更新"),
                         user_id=operator_id)
        self.db.commit()
        self._log_info(f"更新标签任务 {task.task_name}", operator_id)
        return task

    def delete_task(self, task_id: int, operator_id: Optional[int] = None) -> None:
        task = self.db.get(TagTask, task_id)
        if not task:
            raise BusinessException(ERR_NOT_FOUND, f"标签任务 {task_id} 不存在")
        task_name = task.task_name
        task_pk = task.id
        self._log_action("DELETE", "TAG_TASK", task_pk, task_name, user_id=operator_id)
        self.db.delete(task)
        self.db.commit()
        self._log_info(f"删除标签任务 {task_name}", operator_id)

    # ==================================================================
    # 预览 / 校验
    # ==================================================================
    def preview_sql(self, main_table_id: Optional[int] = None,
                    main_field_id: Optional[int] = None,
                    tag_value_code: Optional[str] = None,
                    task_mode: str = "FIELD",
                    theme_id: Optional[int] = None,
                    raw_sql: Optional[str] = None,
                    field_config: Optional[Dict[str, Any]] = None) -> str:
        """实时生成 SQL（不保存任务）"""
        task_mode = (task_mode or "FIELD").upper()

        if task_mode == "SQL":
            ok, message, normalized = SQLValidator(self.db).validate_text(raw_sql or "")
            if not ok:
                raise BusinessException(ERR_TAG_SQL_EMPTY, message)
            return normalized

        if theme_id is not None:
            table = ThemeService(self.db).get_theme_table(theme_id)
            if not field_config:
                raise BusinessException(ERR_VALIDATION, "字段配置模式至少需要选择一个字段")
            return SQLGenerator(self.db).generate_by_fields(
                main_table_id=table.id,
                field_config=field_config,
                tag_value_code=tag_value_code or "",
            )

        # 兼容 V1.0 单表预览
        self._validate_main_table(main_table_id, main_field_id)
        return SQLGenerator(self.db).generate(
            main_table_id=main_table_id,
            main_field_id=main_field_id,
            tag_value_code=tag_value_code or "",
        )

    def validate_sql(self, sql: str, datasource_id: int) -> dict:
        """SQL 直配模式校验（router 直接转发）"""
        return SQLValidator(self.db).validate(sql, datasource_id)

    # ==================================================================
    # 校验辅助
    # ==================================================================
    def _validate_main_table(self, main_table_id: Optional[int],
                             main_field_id: Optional[int]) -> None:
        if not main_table_id or not main_field_id:
            raise BusinessException(ERR_VALIDATION, "主表与主字段不能为空")
        table = self.db.get(MetaTable, main_table_id)
        if not table:
            raise BusinessException(ERR_NOT_FOUND, f"主表 {main_table_id} 不存在")
        field = self.db.get(MetaField, main_field_id)
        if not field or field.table_id != main_table_id:
            raise BusinessException(ERR_NOT_FOUND, f"字段 {main_field_id} 不属于主表 {main_table_id}")

    def _validate_datasource(self, datasource_id: Optional[int]) -> None:
        if datasource_id is None:
            raise BusinessException(ERR_VALIDATION, "数据源不能为空")
        ds = self.db.get(Datasource, datasource_id)
        if not ds:
            raise BusinessException(ERR_NOT_FOUND, f"数据源 {datasource_id} 不存在")
        if not ds.is_enabled:
            raise BusinessException(ERR_DS_DISABLED, f"数据源 '{ds.name}' 已禁用")
