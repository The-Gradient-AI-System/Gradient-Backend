from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from typing import Optional
from service.userService import register_user, login_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterUser(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginUser(BaseModel):
    username: str
    password: str
    phrases: Optional[str] = None


@router.post("/register")
def register(user: RegisterUser):
    return register_user(user)


@router.post("/login")
def login(user: LoginUser):
    return login_user(user, phrases=user.phrases)
