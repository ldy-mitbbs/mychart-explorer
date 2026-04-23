"""FastAPI entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import DB_PATH
from .llm.chat import router as chat_router
from .routes.admin import router as admin_router
from .routes.browser import router as browser_router
from .routes.clinical import router as clinical_router

app = FastAPI(title="MyChart Explorer", version="0.1.0")

# CORS: allow the Vite dev server (localhost:5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FileNotFoundError)
async def missing_db_handler(request: Request, exc: FileNotFoundError):
    # Routes that expect the SQLite DB raise this when the user hasn't ingested yet.
    return JSONResponse(
        status_code=503,
        content={"error": "database_not_ingested", "detail": str(exc)},
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "db": str(DB_PATH), "db_exists": DB_PATH.exists()}


app.include_router(clinical_router, prefix="/api")
app.include_router(browser_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
