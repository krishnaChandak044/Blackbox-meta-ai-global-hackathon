"""
Blackbox FastAPI — Phase 1 entry point.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from services.api.routes import cases, media, jobs
from services.api.db.session import init_db

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
app.include_router(cases.router, prefix=PREFIX)
app.include_router(media.router, prefix=PREFIX)
app.include_router(jobs.router, prefix=PREFIX)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
