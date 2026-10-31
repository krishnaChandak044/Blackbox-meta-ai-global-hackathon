"""
Blackbox FastAPI — Phase 1 entry point.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse

from services.api.auth.session import _password, _secret, is_authenticated
from services.api.auth.session import router as auth_router
from services.api.db.session import init_db
from services.api.routes import calibration, cases, jobs, media, tracks

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _secret()
    _password()
    logger.info("blackbox.api.startup")
    await init_db()
    yield
    logger.info("blackbox.api.shutdown")


app = FastAPI(
    title="Blackbox API",
    description="Evidence-first road crash investigation workspace",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(auth_router, prefix=PREFIX)
app.include_router(cases.router, prefix=PREFIX)
app.include_router(media.router, prefix=PREFIX)
app.include_router(jobs.router, prefix=PREFIX)
app.include_router(calibration.router, prefix=PREFIX)
app.include_router(tracks.router, prefix=PREFIX)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.middleware("http")
async def require_session(request: Request, call_next):
    path = request.url.path
    if (
        request.method != "OPTIONS"
        and path.startswith("/api/v1/")
        and not path.startswith("/api/v1/auth/")
    ):
        if not is_authenticated(request):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)
