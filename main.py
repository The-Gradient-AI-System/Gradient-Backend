import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.userRoutes import router as user_router
from routes.gmailRoutes import router as gmail_router
from routes.settingsRoutes import router as settings_router
from routes.analyticsRoutes import router as analytics_router
from service.autosyncService import auto_sync_loop
from db import init_db

app = FastAPI()

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").strip().split(",")
_cors_origins = [o.strip() for o in _cors_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(gmail_router)
app.include_router(settings_router)
app.include_router(analytics_router)

@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(auto_sync_loop())
