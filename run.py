"""
run.py — 启动入口

使用方式：
    python run.py

默认监听 http://0.0.0.0:8000
"""
import uvicorn

from app.config import app as cfg


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level="info",
    )
