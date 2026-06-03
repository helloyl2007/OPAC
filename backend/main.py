import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.ppt_generate import api_router  # 修复错误的变量名
from app.api.ppt2video import router as ppt2video_router
from app.api.video_list import router as video_router
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.cache_control_middleware import CacheControlMiddleware
from app.utils.resource_manager import resource_manager
from app.api.resource_api import router as resource_router
from app.api.tts_api import router as tts_router
from app.api.exam import router as exam_router  # 正确导入exam模块的router
from app.api.users import router as users_router  # 导入用户路由
from app.api.lesson_plan import router as lesson_plan_router  # 新增此行
from app.api.chat import router as chat_router  # 导入聊天路由

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)

# 创建一个logger实例
logger = logging.getLogger(__name__)

app = FastAPI(title="AI智教助手系统API")

# 添加日志中间件
app.add_middleware(LoggingMiddleware)

# 添加缓存控制中间件，注意顺序在日志中间件之后
app.add_middleware(CacheControlMiddleware)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# 确保所有必要目录存在
os.makedirs("static/generated", exist_ok=True)
os.makedirs("static/generated/ppts", exist_ok=True)
os.makedirs("static/generated/videos", exist_ok=True)
os.makedirs("static/generated/audio", exist_ok=True)
os.makedirs("static/generated/temp", exist_ok=True)  
os.makedirs("static/templates/previews", exist_ok=True)
os.makedirs("static/thumbnails", exist_ok=True) 
os.makedirs("static/thumbnails/ppt_thumb", exist_ok=True)  

# 注册静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 注册路由
app.include_router(api_router, prefix="/api")
app.include_router(ppt2video_router, prefix="/api/ppt2video")
app.include_router(video_router, prefix="/api/video")  # 使用整合后的视频路由
app.include_router(resource_router, prefix="/api/resources", tags=["resources"])
app.include_router(tts_router, prefix="/api/tts", tags=["tts"])
app.include_router(exam_router, prefix="/api/exam", tags=["exam"])  # 注册试题生成路由
app.include_router(users_router, prefix="/api", tags=["users"])  # 注册用户路由

# 确保备课助手的路由放在最后注册
app.include_router(lesson_plan_router, prefix="/api/lesson-plan", tags=["lesson-plan"])  # 在其他路由注册后添加
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])  # 注册聊天路由

# 启动资源清理线程
@app.on_event("startup")
def startup_event():
    logger.info("应用启动 - 初始化资源管理器")
    resource_manager.start_cleanup_thread()

@app.on_event("shutdown")
def shutdown_event():
    logger.info("应用关闭 - 停止资源管理器")
    resource_manager.stop_cleanup_thread()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # 启用热重载，调试用
    # uvicorn.run(app, 
    #             host="0.0.0.0", 
    #             port=8000,
    #             reload=True,  # 启用热重载
    #             reload_dirs=["app"])  # 监视app目录的文件变化
