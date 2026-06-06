"""FastAPI entrypoint for the StockPilot backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="StockPilot API",
        version=APP_VERSION,
        description="Local-first portfolio ledger and valuation API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
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

    return app


app = create_app()
