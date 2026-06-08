"""
内部 API Key 鉴权中间件
仅允许持有正确 X-Internal-Key 的请求通过（来自 hub-svc 的代理调用）
开发模式下可通过环境变量 INTERNAL_AUTH=false 关闭鉴权
"""
import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class InternalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 仅对 /api/ 路径做鉴权，静态文件不拦截
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # 开发模式开关
        if os.getenv("INTERNAL_AUTH", "true").lower() == "false":
            return await call_next(request)

        expected_key = os.getenv("DOUGRAB_API_KEY", "")
        if not expected_key:
            # 未配置 key 时放行（兼容本地开发）
            return await call_next(request)

        provided_key = request.headers.get("X-Internal-Key", "")
        if provided_key != expected_key:
            logger.warning(
                "Unauthorized request from %s: invalid X-Internal-Key",
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized: invalid internal key"},
            )

        return await call_next(request)
