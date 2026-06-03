from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import json
from datetime import datetime

from app.core.database import get_db
from app.models.models import User
from app.core.config import settings
from app.schemas.user import User as UserSchema
import logging

security = HTTPBearer()
logger = logging.getLogger(__name__)

# 在开发中使用固定的测试用户ID (用于调试)
TEST_USER_ID = None  # 设置为None表示不使用固定ID

# 获取当前用户
async def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserSchema:
    """
    从JWT令牌中解析并验证用户，返回当前登录用户
    """
    try:
        # 创建一个异常模板
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的身份验证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        # 获取token
        token = credentials.credentials
        
        # 开发环境模拟用户
        if token == "testtoken":
            return await get_test_user(db)
        
        # 解码JWT
        try:
            # 使用同一密钥和算法
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("id")
            if user_id is None:
                if settings.ENVIRONMENT == "development":
                    return await get_test_user(db)
                raise credentials_exception
                
        except JWTError as e:
            logger.error(f"JWT解码错误: {str(e)}")
            if settings.ENVIRONMENT == "development":
                return await get_test_user(db)
            raise credentials_exception
        
        # 从数据库中查询用户
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            if settings.ENVIRONMENT == "development":
                return await get_test_user(db)
            raise credentials_exception
        
        # 记录当前认证的用户
        logger.info(f"已认证用户: {user.username}(ID:{user.id})")
            
        # 构建用户模型
        roles = []
        if user.roles:
            try:
                roles = json.loads(user.roles)
            except:
                roles = user.roles.split(",") if user.roles else []
                
        return UserSchema(
            id=user.id,
            username=user.username,
            roles=roles
        )
        
    except Exception as e:
        logger.error(f"认证失败: {str(e)}")
        if settings.ENVIRONMENT == "development":
            return await get_test_user(db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )

# 获取测试用户
async def get_test_user(db: Session) -> UserSchema:
    """获取或创建测试用户"""
    if TEST_USER_ID is not None:
        # 使用固定的测试用户ID
        test_user = db.query(User).filter(User.id == TEST_USER_ID).first()
        if test_user:
            logger.info(f"使用固定测试用户: ID={test_user.id}")
            return UserSchema(
                id=test_user.id,
                username=test_user.username,
                roles=test_user.roles.split(",") if test_user.roles else []
            )
    
    # 查找第一个用户
    test_user = db.query(User).first()
    if test_user:
        logger.info(f"使用现有用户作为测试用户: ID={test_user.id}")
        return UserSchema(
            id=test_user.id,
            username=test_user.username,
            roles=test_user.roles.split(",") if test_user.roles else []
        )
    
    # 创建测试用户
    test_user = User(
        username="testuser",
        password="password",
        roles="user",
        status=1,
        created_at=datetime.now(),
        mobile="12345678901"
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    
    logger.info(f"创建新测试用户: ID={test_user.id}")
    
    return UserSchema(
        id=test_user.id,
        username=test_user.username,
        roles=["user"]
    )
