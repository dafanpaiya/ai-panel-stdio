"""
AI Panel Studio — FastAPI 入口。
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes import router, set_manager
from app.core.manager import DiscussionManager
from app.llm.factory import create_llm_client_from_config
from app.db.database import Database, init_db
from app.core.models import now_iso
from app.core.config import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时
    logger.info("初始化数据库…")
    init_db()

    # 初始化默认配置
    load_config()

    logger.info("初始化 DiscussionManager…")
    db = Database()
    manager = DiscussionManager(db)
    set_manager(manager)

    app.state.db = db
    app.state.manager = manager

    logger.info("AI Panel Studio 后端已就绪")
    yield

    # 关闭时
    logger.info("AI Panel Studio 后端关闭")


app = FastAPI(
    title="AI Panel Studio",
    description="AI 圆桌讨论本地 Web 应用",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 本地开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount('/demo', StaticFiles(directory='../demo', html=True), name='demo')
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": now_iso()}


def main():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
