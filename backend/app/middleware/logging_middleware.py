import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import json

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 记录请求开始时间
        start_time = time.time()
        
        # 获取请求路径和方法
        path = request.url.path
        method = request.method
        
        # 获取请求体
        try:
            if method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                request_body = body.decode()
                # 限制日志长度，避免大型请求体
                if len(request_body) > 1000:
                    request_body = request_body[:1000] + "... [截断]"
                logger.info(f"请求: {method} {path}, 请求体: {request_body}")
            else:
                logger.info(f"请求: {method} {path}")
        except Exception as e:
            logger.warning(f"无法记录请求体: {str(e)}")
        
        # 调用下一个中间件或路由处理器
        response = await call_next(request)
        
        # 记录响应时间和状态码
        process_time = time.time() - start_time
        logger.info(f"响应: {method} {path} - 状态码: {response.status_code}, 处理时间: {process_time:.3f}s")
        
        return response
