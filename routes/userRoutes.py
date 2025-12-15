from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from service.userService import register_user, login_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class User(BaseModel):
    username: str
    email: EmailStr
    password: str


@router.post("/register")
def register(user: User):
    return register_user(user)


@router.post("/login")
def login(user: User):
    return login_user(user)
