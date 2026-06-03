from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    password_confirm: str
    mobile: str | None = None