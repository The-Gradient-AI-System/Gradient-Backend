from fastapi import FastAPI
from routes.userRoutes import router as user_router
from routes.gmailRoutes import router as gmail_router
from service.autosyncService import auto_sync_loop
app = FastAPI()
app.include_router(user_router)

from fastapi import FastAPI
import asyncio

app = FastAPI(title="Gmail → Google Sheets")

app.include_router(gmail_router)

@app.on_event("startup")
async def startup():
    asyncio.create_task(auto_sync_loop())
