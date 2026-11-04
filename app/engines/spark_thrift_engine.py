"""
engines/spark_thrift_engine.py — Spark Thrift JDBC 异步执行引擎

真实对接需要可用的 Spark ThriftServer（默认端口 10015）。
JayDeBeApi 依赖 JVM（java 命令必须在 PATH 中）。

作业场景若无 Spark 集群，此模块提供完整代码框架但所有自动化测试使用 mock。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.engines.base_engine import BaseEngine, TaskStatusInfo


class SparkThriftEngine(BaseEngine):
    """
    Spark Thrift JDBC 异步执行引擎

    - submit_sql:  通过 JayDeBeApi 连接 ThriftServer 提交 SQL，返回 Spark 异步 task ID
    - get_task_status: 查询执行状态（通过 SHOW QUERIES 等命令）
    """

    ENGINE_TYPE = "spark"

    def __init__(self):
        self._results_cache: Dict[str, TaskStatusInfo] = {}  # 简单缓存（作业场景）

    def _get_connection(self, config: Dict[str, Any]):
        """建立 JDBC 连接。失败抛异常（由 BaseEngine._safe_execute 包装）"""
        import jaydebeapi

        url = config["thrift_url"]  # e.g. jdbc:hive2://host:10015/default
        user = config.get("username") or ""
        password = config.get("password") or ""

        return jaydebeapi.connect(
            "org.apache.hive.jdbc.HiveDriver",
            url,
            [user, password] if user else [],
        )

    def validate_sql(self, sql: str, datasource_config: Dict[str, Any]) -> tuple[bool, str]:
        """
        V1.1：SQL 校验。

        - mock=true：不建立 JDBC 连接，直接返回通过（演示环境无 Spark 集群）；
        - mock=false：连接 ThriftServer 执行 EXPLAIN 编译校验。
        """
        if datasource_config.get("mock"):
            return True, "Mock 模式默认通过"

        conn = None
        try:
            conn = self._get_connection(datasource_config)
            cursor = conn.cursor()
            cursor.execute("EXPLAIN " + sql)
            cursor.close()
            return True, "Spark 编译校验通过"
        except ImportError:
            return False, "JayDeBeApi 未安装或 JVM 不可用，无法校验 Spark SQL"
        except Exception as e:
            return False, f"Spark 校验失败: {e}"
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def submit_sql(self, sql: str, datasource_config: Dict[str, Any]) -> str:
        """
        通过 Thrift JDBC 提交 SQL
        返回形如 'spark_<timestamp>' 的异步任务 ID（真实场景会返回 Spark QueryExecution ID）
        """
        # ---------- Mock 模式：不连接 JDBC，直接成功 ----------
        if datasource_config.get("mock"):
            task_id = f"mock-{int(time.time() * 1000)}"
            self._results_cache[task_id] = TaskStatusInfo(
                status=self.STATUS_SUCCESS,
                log="Mock 模式执行成功（未连接 Spark 集群）",
            )
            return task_id

        start = time.time()
        conn = None
        try:
            conn = self._get_connection(datasource_config)
            cursor = conn.cursor()

            # Spark Thrift JDBC 默认是异步提交，execute() 会返回但查询尚未完成
            cursor.execute(sql)
            # 对于 SELECT，可以立即 fetch 获取结果（同步等待）；
            # 但按引擎抽象约定，submit_sql 应快速返回，所以这里只提交不等待。
            # 执行日志简单拼接
            task_id = f"spark_{int(time.time() * 1000)}"
            self._results_cache[task_id] = TaskStatusInfo(
                status=self.STATUS_RUNNING,
                log=f"Spark Thrift JDBC 已提交 SQL（耗时 {int((time.time() - start) * 1000)}ms）",
            )
            cursor.close()
            conn.close()
            return task_id

        except ImportError:
            raise RuntimeError(
                "JayDeBeApi 未安装或 JVM 不可用。"
                "请安装: pip install JayDeBeApi，并确保 java 命令在 PATH 中。"
            )
        except Exception as e:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            raise

    def get_task_status(self, task_id: str, datasource_config: Optional[Dict[str, Any]] = None) -> TaskStatusInfo:
        """
        查询任务状态。真实场景可以通过 SHOW QUERIES + task_id 过滤。
        作业简化实现：使用本地缓存的结果。
        """
        info = self._results_cache.get(task_id)
        if info:
            return info
        return TaskStatusInfo(status=self.STATUS_PENDING, log="任务未找到或已过期")
