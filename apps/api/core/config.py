"""Runtime configuration for the StockPilot backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    db_file: Path
    offline_mode: bool
    history_enabled: bool
    using_default_db_file: bool


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[3]
    data_dir = root_dir / "data"
    configured_db = os.environ.get("PORTFOLIO_DB_FILE")
    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        db_file=Path(configured_db) if configured_db else data_dir / "portfolio.db",
        offline_mode=os.environ.get("PORTFOLIO_OFFLINE") == "1",
        history_enabled=os.environ.get("PORTFOLIO_HISTORY_ENABLED", "1") != "0",
        using_default_db_file=configured_db is None,
    )


settings = load_settings()
