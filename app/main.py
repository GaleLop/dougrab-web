"""
DouGrab Web — FastAPI 主入口
替代原 main.py 的 http.server + 单体架构
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.services.chrome_manager import chrome_manager
from app.core.config import FRONTEND_DIR, API_PORT, API_HOST
from app.core.auth_middleware import InternalAuthMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("DouGrab Web starting up (port=%d)...", API_PORT)
    # 启动时自动启动 Chrome（headless 模式）
    try:
        await chrome_manager.start()
        logger.info("Chrome ready")
    except Exception as e:
        logger.warning("Chrome not started yet: %s (will start on first request)", e)
    yield
    # 关闭时清理
    await chrome_manager.stop()
    logger.info("DouGrab Web shut down")


app = FastAPI(
    title="DouGrab Web",
    description="抖音视频批量下载 Web 服务",
    version="3.2.0-web",
    lifespan=lifespan,
)

# 内部 API Key 鉴权（hub-svc 代理调用时携带）
app.add_middleware(InternalAuthMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(api_router)

# 静态文件服务（前端）
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{path:path}")
    async def serve_static(path: str):
        file_path = FRONTEND_DIR / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))


def main():
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
