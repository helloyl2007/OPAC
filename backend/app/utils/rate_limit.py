from fastapi import HTTPException
import time

login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME = 300

def check_login_attempts(ip: str):
    if ip in login_attempts:
        if login_attempts[ip]["attempts"] >= MAX_ATTEMPTS:
            if time.time() - login_attempts[ip]["timestamp"] < LOCKOUT_TIME:
                raise HTTPException(status_code=429, detail="账户已被锁定，请稍后再试")
            else:
                del login_attempts[ip]

def clear_login_attempts(ip: str):
    if ip in login_attempts:
        del login_attempts[ip]
