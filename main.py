import os
import re
import asyncio
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.userRoutes import router as user_router
from routes.gmailRoutes import router as gmail_router
from routes.settingsRoutes import router as settings_router
from routes.analyticsRoutes import router as analytics_router
from service.autosyncService import auto_sync_loop
from db import init_db

_BASE_DIR = Path(__file__).resolve().parent
_CREDENTIALS_DIR = _BASE_DIR / "credentials"
_TOKEN_FILE = _CREDENTIALS_DIR / "token.json"


def _ensure_token_from_env():
    """If token.json is missing but GMAIL_TOKEN_JSON is set, write it to credentials/token.json (e.g. on Render)."""
    if _TOKEN_FILE.exists():
        return
    raw = os.getenv("GMAIL_TOKEN_JSON")
    if not raw or not raw.strip():
        return
    _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(raw.strip(), encoding="utf-8")
    print(f"[startup] token.json created from GMAIL_TOKEN_JSON at {_TOKEN_FILE}")


app = FastAPI()

_cors_origins_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
).strip().split(",")
_cors_origins = [o.strip() for o in _cors_origins_raw if o.strip()]
_allow_origin_regex_local = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")
_allow_origin_regex_vercel = re.compile(r"^https://[^/]+\.vercel\.app$", re.IGNORECASE)


def _cors_allow_origin(origin: str) -> str:
    if not origin:
        return _cors_origins[0] if _cors_origins else "http://localhost:3000"
    if origin in _cors_origins:
        return origin
    if _allow_origin_regex_local.match(origin) or _allow_origin_regex_vercel.match(origin):
        return origin
    return _cors_origins[0] if _cors_origins else "http://localhost:3000"


class OPTIONSCORSMiddleware(BaseHTTPMiddleware):
    """Handle OPTIONS preflight and add CORS headers to all responses for localhost."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin") or ""
        allow_origin = _cors_allow_origin(origin)
        cors_headers = {
            "Access-Control-Allow-Origin": allow_origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        }
        if request.method == "OPTIONS":
            return Response(status_code=200, headers={**cors_headers, "Access-Control-Max-Age": "86400"})
        try:
            response = await call_next(request)
        except Exception as e:
            import traceback
            import json as _json
            traceback.print_exc()
            body = {"detail": "Internal server error", "error": str(e)}
            return Response(
                status_code=500,
                content=_json.dumps(body, ensure_ascii=False),
                media_type="application/json",
                headers=cors_headers,
            )
        for key, value in cors_headers.items():
            response.headers[key] = value
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|https://[^/]+\.vercel\.app)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(OPTIONSCORSMiddleware)

app.include_router(user_router)
app.include_router(gmail_router)
app.include_router(settings_router)
app.include_router(analytics_router)

@app.on_event("startup")
async def startup():
    init_db()
    _ensure_token_from_env()
    asyncio.create_task(auto_sync_loop())
