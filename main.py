from fastapi import FastAPI
from pydantic import BaseModel, EmailStr
from db import conn
from hashPswd import hash_password, verify_password

app = FastAPI()

class User(BaseModel):
    username: str
    email: EmailStr
    password: str

@app.post("/register")
def register(user: User):
    exists = conn.execute("SELECT 1 FROM users WHERE username = ?", [user.username]).fetchone()
    if exists:
        return {"error": "Username already exists"}
    
    hashed_pwd = hash_password(user.password)
    
    last_id = conn.execute("SELECT MAX(id) FROM users").fetchone()[0]
    new_id = 1 if last_id is None else last_id + 1

    conn.execute("INSERT INTO users (id, username, email, password) VALUES (?, ?, ?, ?)",
                 [new_id, user.username, user.email, hashed_pwd])
    return {"msg": "User registered successfully"}

@app.post("/login")
def login(user: User):
    row = conn.execute("SELECT password FROM users WHERE username = ?", [user.username]).fetchone()
    if not row or not verify_password(user.password, row[0]):
        return {"error": "Invalid username or password"}
    return {"msg": "Login successful"}
