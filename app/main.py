"""
main.py — FastAPI 应用工厂

职责：
- 创建 FastAPI 实例
- 注册全局异常处理器（BusinessException → 统一 JSON）
- 挂载静态文件
- include 所有 router
- startup 事件：init_db 自动建表 + 初始化默认数据
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.exceptions import BusinessException, ERR_SYSTEM


def create_app() -> FastAPI:
    app = FastAPI(
        title="标签配置平台 API",
        description="AI辅助软件开发综合实践作业 —— 标签配置管理 Web 平台",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ==================== 全局异常处理器 ====================
    @app.exception_handler(BusinessException)
    async def _handle_biz(request: Request, exc: BusinessException):
        return JSONResponse(
            status_code=200,  # 业务异常用 200 + code 区分
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):
        # 把 Pydantic 422 错误转成可读字符串
        errors = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            errors.append(f"{loc}: {err.get('msg')}")
        return JSONResponse(
            status_code=200,
            content={"code": 40001, "message": "参数校验失败", "data": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def _handle_unknown(request: Request, exc: Exception):
        # 系统异常：记录日志后返回友好提示
        from app.db.database import get_session_factory
        from app.db.models.system_log import SystemLog
        try:
            factory = get_session_factory()
            with factory() as db:
                db.add(SystemLog(
                    level="ERROR",
                    module="global",
                    message=f"{type(exc).__name__}: {exc}",
                ))
                db.commit()
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={"code": ERR_SYSTEM, "message": "系统繁忙，请稍后重试"},
        )

    # ==================== Startup 事件 ====================
    @app.on_event("startup")
    async def _on_startup():
        from app.db.database import init_db
        from app.config import BASE_DIR
        init_db()

        # 确保 logs 目录
        logs_dir = BASE_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

    # ==================== Router 注册 ====================
    from app.routers.auth import router as auth_router
    from app.routers.users import router as users_router
    from app.routers.metadata import router as metadata_router
    from app.routers.themes import router as themes_router
    from app.routers.relations import router as relations_router
    from app.routers.enum_config import router as enum_router
    from app.routers.approvals import router as approvals_router
    from app.routers.datasources import router as datasources_router
    from app.routers.tag_tasks import router as tag_tasks_router
    from app.routers.execution import router as execution_router

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(metadata_router)
    app.include_router(themes_router)
    app.include_router(relations_router)
    app.include_router(enum_router)
    app.include_router(approvals_router)
    app.include_router(datasources_router)
    app.include_router(tag_tasks_router)
    app.include_router(execution_router)

    # ==================== 静态文件 ====================
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def _root():
        return FileResponse(str(static_dir / "index.html"))

    return app


# 默认导出
app = create_app()
