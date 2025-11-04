from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173"],
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# class Message(BaseModel):
#     text: str

# @app.post("/api/message")
# def get_message(msg: Message):
#     response = f"FastAPI отримав: {msg.text}"
#     return {"reply": response}
