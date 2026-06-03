from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

class CacheControlMiddleware(BaseHTTPMiddleware):
    """设置特定资源的缓存控制头"""
    
    async def dispatch(self, request: Request, call_next):
        # 调用下一个中间件
        response = await call_next(request)
        
        # 为视频文件设置缓存控制头
        path = request.url.path
        if path.startswith("/static/generated/videos/"):
            # 设置为不缓存
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            logger.debug(f"为视频文件设置不缓存头: {path}")
        
        return response
