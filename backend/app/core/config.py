from pydantic_settings import BaseSettings
from typing import List, Optional
import secrets
from dotenv import load_dotenv
import os

# 加载.env文件
load_dotenv()

class Settings(BaseSettings):
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "")
    # OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "ernie-4.5-8k-preview")
    # OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "deepseek-r1-250528")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "qwen-plus")
 
    # 百练智能体应用配置
    BAILIAN_APP_ID: str = os.getenv("BAILIAN_APP_ID", "")

    # 环境设置
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # JWT配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")  # 在生产环境中使用安全的密钥
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 7200  # 7200分钟
    ALGORITHM: str = "HS256"

    # CORS配置
    # CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173","http://edu.xiaojuai.com"]
    
    # BASE_URL配置
    BASE_URL: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
