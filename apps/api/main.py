"""FastAPI entrypoint for the StockPilot backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers.v1 import router as v1_router
from apps.api.services import market_refresh


APP_VERSION = "1.5.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    market_refresh.start()
    yield


def create_app() -> FastAPI:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    web_origin = os.environ.get("STOCKPILOT_WEB_ORIGIN")
    if web_origin and web_origin not in origins:
        origins.append(web_origin)
    app = FastAPI(
        title="StockPilot API",
        version=APP_VERSION,
        description="Local-first portfolio ledger and valuation API.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": "StockPilot API",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    @app.get("/api/v1/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "stockpilot-api",
            "version": APP_VERSION,
        }

    app.include_router(v1_router)

    return app


app = create_app()
