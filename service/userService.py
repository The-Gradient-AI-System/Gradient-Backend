from db import conn
from hashPswd import hash_password, verify_password
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException, status
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

try:
    ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "2"))
except ValueError:
    ACCESS_TOKEN_EXPIRE_HOURS = 2

def register_user(user):
    exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ? OR email = ?",
        [user.username, user.email]
    ).fetchone()

    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    hashed_pwd = hash_password(user.password)

    next_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM users"
    ).fetchone()[0]

    conn.execute(
        "INSERT INTO users (id, username, email, password) VALUES (?, ?, ?, ?)",
        [next_id, user.username, user.email, hashed_pwd]
    )

    return {"msg": "User registered successfully"}


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def login_user(user):
    username = user.username or user.email

    row = conn.execute(
        "SELECT username, password FROM users WHERE username = ? OR email = ?",
        [username, user.email or username]
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    stored_username, hashed_password = row

    if not verify_password(user.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    access_token = create_access_token({"sub": stored_username})
    return {"access_token": access_token, "token_type": "bearer"}
