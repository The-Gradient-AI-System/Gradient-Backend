from db import conn
from hashPswd import hash_password, verify_password
from datetime import datetime, timedelta
from jose import jwt
from fastapi import HTTPException, status
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", 2))

PHRASE_TOKEN_EXPIRE_DAYS = 0.000694  # 30 днів в подальшому одна хвилина 0.000694 для тесту


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

    if PHRASE_TOKEN_EXPIRE_DAYS > 0:
        phrase_hash = hash_password("phrase1,phrase2,phrase3")
        expires_at = datetime.utcnow()
    else:
        phrase_hash = None
        expires_at = None

    conn.execute(
        """
        INSERT INTO users (username, email, password, phrase_hash, phrase_expires_at, phrase_revoked)
        VALUES (?, ?, ?, ?, ?, FALSE)
        """,
        [user.username, user.email, hashed_pwd, phrase_hash, expires_at]
    )

    response = {"msg": "User registered successfully"}
    if phrase_hash:
        response["phrases"] = "phrase1,phrase2,phrase3"
    return response


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def login_user(user, phrases: str = None):
    row = conn.execute(
        "SELECT password, phrase_hash, phrase_expires_at, phrase_revoked FROM users WHERE username = ?",
        [user.username]
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    hashed_password, phrase_hash, phrase_expires_at, phrase_revoked = row

    if not verify_password(user.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    require_phrases = False
    if phrase_hash:
        if phrase_expires_at is None or phrase_expires_at <= datetime.utcnow() or phrase_revoked:
            require_phrases = True

    if require_phrases:
        if not phrases:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Enter your 3 phrases to continue login"
            )
        if not verify_password(phrases, phrase_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Incorrect phrases"
            )
        new_expire = datetime.utcnow() + timedelta(days=PHRASE_TOKEN_EXPIRE_DAYS)
        conn.execute(
            "UPDATE users SET phrase_expires_at = ?, phrase_revoked = FALSE WHERE username = ?",
            [new_expire, user.username]
        )

    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "require_phrases": require_phrases}
