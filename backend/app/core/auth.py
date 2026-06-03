from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.logger import logger
from app.core.config import settings
from jwt import decode, PyJWTError
from datetime import datetime

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """验证用户Token"""
    try:
        token = credentials.credentials
        if not token:
            raise HTTPException(status_code=401, detail="未提供认证令牌")
            
        try:
            # 解码并验证token
            payload = decode(
                token, 
                settings.SECRET_KEY, 
                algorithms=["HS256"]
            )
            
            # 验证token是否过期
            if 'exp' in payload:
                expiration = datetime.fromtimestamp(payload['exp'])
                if expiration < datetime.utcnow():
                    raise HTTPException(status_code=401, detail="Token已过期")
            
            # 确保payload包含必要的用户信息
            if not all(k in payload for k in ['id', 'username', 'roles']):
                raise HTTPException(status_code=401, detail="Token信息不完整")
                
            logger.info(f"Token验证成功: user={payload['username']}")
            return payload
            
        except PyJWTError as e:
            logger.error(f"Token验证失败: {str(e)}")
            raise HTTPException(status_code=401, detail="无效的Token")
            
    except Exception as e:
        logger.error(f"认证失败: {str(e)}")
        raise HTTPException(status_code=401, detail="认证失败")
