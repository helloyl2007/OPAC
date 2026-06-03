import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.security import verify_password, get_password_hash, validate_password
from app.schemas.auth import LoginRequest, RegisterRequest
from app.utils.rate_limit import check_login_attempts, clear_login_attempts
from app.core.database import get_db
from app.models.models import User
from pydantic import BaseModel
from app.utils.logger import logger
from app.core.config import settings
from jwt import encode
from datetime import datetime, timedelta
from typing import Dict
from fastapi.security import HTTPBasicCredentials

router = APIRouter()

class UserUpdate(BaseModel):
    username: str
    password: str | None = None
    mobile: str | None = None
    status: str | None = None  
    roles: str | None = None  # 添加roles字段

class UserCreate(BaseModel):
    username: str
    password: str
    mobile: str | None = None
    roles: str = "user"

def validate_mobile(mobile: str | None) -> bool:
    if mobile is None:
        return True
    return bool(re.match(r'^1\d{10}$', mobile))

def create_access_token(user: User) -> Dict[str, str]:
    """创建访问令牌"""
    # 设置过期时间
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    
    # 创建JWT数据
    to_encode = {
        "id": user.id,  # 确保是整数
        "username": user.username,
        "roles": user.roles,
        "exp": expire
    }
    
    # 使用settings中的密钥生成token
    encoded_jwt = encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm="HS256"
    )
    
    logger.info(f"Generated token for user: {user.username}")
    return {"access_token": encoded_jwt, "token_type": "bearer"}

@router.post("/login")
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    # 使用LoginRequest而非HTTPBasicCredentials
    # 查询用户
    user = db.query(User).filter(User.username == credentials.username).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="用户名不存在")
        
    # 检查用户状态
    if user.status != "1":
        raise HTTPException(status_code=401, detail="账号待审核或已被禁用")
        
    # 实现密码验证
    if not verify_password(credentials.password, user.password):
        raise HTTPException(status_code=401, detail="密码错误")
        
    # 生成token
    token_data = create_access_token(user)
    
    return {
        "token": token_data["access_token"],
        "username": user.username,
        "roles": user.roles
    }

@router.post("/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if request.password != request.password_confirm:
        raise HTTPException(status_code=400, detail="两次密码输入不一致")
    
    if not validate_password(request.password):
        raise HTTPException(status_code=400, detail="密码必须包含大小写字母和数字，且长度至少6位")

    if request.mobile and not validate_mobile(request.mobile):
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    hashed_password = get_password_hash(request.password)
    new_user = User(
        username=request.username, 
        password=hashed_password,
        mobile=request.mobile,  
        roles="user",
        status="0", 
        created_at=datetime.now()  # 修改这里
    )
    db.add(new_user)
    db.commit()
    
    return {"message": "注册成功，请等待通过审核后登录"}

@router.get("/users")
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": user.id, 
             "username": user.username, 
             "roles": user.roles,
             "mobile": user.mobile,
             "status": user.status,  
             "created_at": user.created_at} for user in users]

@router.post("/users")
async def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    if not validate_password(user_data.password):
        raise HTTPException(status_code=400, detail="密码必须包含大小写字母和数字，且长度至少8位")
    
    if user_data.mobile and not validate_mobile(user_data.mobile):
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        password=hashed_password,
        mobile=user_data.mobile,
        roles=user_data.roles,
        status="1",  # 默认已审核
        created_at=datetime.now()  # 修改这里
    )
    
    db.add(new_user)
    db.commit()
    return {"message": "用户创建成功"}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    db.delete(user)
    db.commit()
    return {"message": "删除成功"}

@router.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 检查用户名是否已存在
    if user_data.username != user.username:
        existing = db.query(User).filter(User.username == user_data.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")
    
    user.username = user_data.username
    if user_data.password:
        if not validate_password(user_data.password):
            raise HTTPException(status_code=400, detail="密码必须包含大小写字母和数字，且长度至少8位")
        user.password = get_password_hash(user_data.password)
    if user_data.mobile:
        if not validate_mobile(user_data.mobile):
            raise HTTPException(status_code=400, detail="手机号格式不正确")
        user.mobile = user_data.mobile
    if user_data.status:
        user.status = user_data.status
    if user_data.roles:  # 添加roles更新逻辑
        user.roles = user_data.roles
    
    db.commit()
    return {"message": "更新成功"}

@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int, 
    status: str,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.status = status
    db.commit()
    return {"message": "状态更新成功"}

@router.post("/logout")
async def logout():
    return {"message": "登出成功"}