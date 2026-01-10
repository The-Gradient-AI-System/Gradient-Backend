from db import conn
from hashPswd import hash_password, verify_password
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException, status
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS"))

def register_user(user):
    exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ?",
        [user.username]
    ).fetchone()

    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    hashed_pwd = hash_password(user.password)

    conn.execute(
        "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
        [user.username, user.email, hashed_pwd]
    )

    return {"msg": "User registered successfully"}


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def login_user(user):
    row = conn.execute(
        "SELECT password FROM users WHERE username = ?",
        [user.username]
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    hashed_password = row[0]

    if not verify_password(user.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
