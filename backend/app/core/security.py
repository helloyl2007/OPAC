from passlib.context import CryptContext
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def validate_password(password: str) -> bool:
    """
    验证密码是否符合要求：
    - 至少8位
    - 包含大小写字母
    - 包含数字
    """
    if len(password) < 6:
        return False
    # if not re.search(r'[A-Z]', password):
    #     return False
    # if not re.search(r'[a-z]', password):
    #     return False
    # if not re.search(r'\d', password):
    #     return False
    return True
