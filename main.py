from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.userRoutes import router as user_router
from routes.gmailRoutes import router as gmail_router
from routes.settingsRoutes import router as settings_router
from service.autosyncService import auto_sync_loop
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(gmail_router)
app.include_router(settings_router)

@app.on_event("startup")
async def startup():
    asyncio.create_task(auto_sync_loop())
