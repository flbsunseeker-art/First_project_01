"""SQLite storage and schema migration for the portfolio ledger."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from apps.api.core.config import settings


BASE_DIR = settings.root_dir
DATA_DIR = settings.data_dir
DEFAULT_DB_FILE = DATA_DIR / "portfolio.db"
LEGACY_DB_FILE = BASE_DIR / "portfolio.db"
DB_FILE = settings.db_file
SCHEMA_VERSION = "2"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _metadata(conn: sqlite3.Connection, key: str) -> str | None:
    if not _table_exists(conn, "metadata"):
        return None
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _using_default_db_file() -> bool:
    return settings.using_default_db_file and DB_FILE == DEFAULT_DB_FILE


def _migrate_default_database_location() -> Path | None:
    if not _using_default_db_file():
        return None
    if DB_FILE.exists() or not LEGACY_DB_FILE.exists():
        return None

    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{LEGACY_DB_FILE.stem}-before-data-dir-{stamp}.db"
    shutil.copy2(LEGACY_DB_FILE, backup_path)
    shutil.copy2(LEGACY_DB_FILE, DB_FILE)
    return backup_path


def _backup_legacy_database(conn: sqlite3.Connection) -> Path | None:
    if not DB_FILE.exists() or not _table_exists(conn, "holdings"):
        return None
    if _metadata(conn, "schema_version") == SCHEMA_VERSION:
        return None

    backup_dir = DB_FILE.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{DB_FILE.stem}-before-v2-{stamp}.db"
    if not backup_path.exists():
        conn.commit()
        shutil.copy2(DB_FILE, backup_path)
    return backup_path


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS securities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL CHECK (market IN ('A', 'HK', 'US')),
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency IN ('CNY', 'HKD', 'USD')),
            industry TEXT NOT NULL DEFAULT '其他',
            industry_manual INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (market, code)
        );

        CREATE TABLE IF NOT EXISTS opening_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            security_id INTEGER NOT NULL UNIQUE,
            start_date TEXT NOT NULL,
            shares TEXT NOT NULL,
            average_cost TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (security_id) REFERENCES securities(id)
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            security_id INTEGER NOT NULL,
            trade_date TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            shares TEXT NOT NULL,
            price TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (security_id) REFERENCES securities(id),
            UNIQUE (trade_date, sequence)
        );

        CREATE INDEX IF NOT EXISTS idx_trades_security_date
            ON trades(security_id, trade_date, sequence);

        CREATE TABLE IF NOT EXISTS market_prices (
            security_id INTEGER NOT NULL,
            price_date TEXT NOT NULL,
            close_price TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (security_id, price_date),
            FOREIGN KEY (security_id) REFERENCES securities(id)
        );

        CREATE TABLE IF NOT EXISTS exchange_rates (
            currency TEXT NOT NULL,
            rate_date TEXT NOT NULL,
            cny_rate TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (currency, rate_date)
        );

        CREATE TABLE IF NOT EXISTS daily_position_snapshots (
            snapshot_date TEXT NOT NULL,
            security_id INTEGER NOT NULL,
            shares TEXT NOT NULL,
            average_cost TEXT NOT NULL,
            close_price TEXT NOT NULL,
            cny_rate TEXT NOT NULL,
            market_value_cny TEXT NOT NULL,
            cost_value_cny TEXT NOT NULL,
            unrealized_pnl_cny TEXT NOT NULL,
            PRIMARY KEY (snapshot_date, security_id),
            FOREIGN KEY (security_id) REFERENCES securities(id)
        );

        CREATE TABLE IF NOT EXISTS daily_portfolio_snapshots (
            snapshot_date TEXT PRIMARY KEY,
            total_market_value_cny TEXT NOT NULL,
            daily_pnl_cny TEXT,
            cumulative_pnl_cny TEXT NOT NULL,
            realized_pnl_cny TEXT NOT NULL,
            unrealized_pnl_cny TEXT NOT NULL,
            buy_flow_cny TEXT NOT NULL,
            sell_flow_cny TEXT NOT NULL,
            status TEXT NOT NULL,
            is_final INTEGER NOT NULL,
            error_message TEXT,
            calculated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL,
            details TEXT
        );
        """
    )


def _migrate_legacy_holdings(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "holdings"):
        return 0
    if _metadata(conn, "legacy_holdings_migrated") == "1":
        return 0

    existing = conn.execute("SELECT COUNT(*) AS n FROM securities").fetchone()["n"]
    if existing:
        _set_metadata(conn, "legacy_holdings_migrated", "1")
        return 0

    rows = conn.execute(
        """
        SELECT market, code, name, currency, industry, shares, cost_price
        FROM holdings ORDER BY id
        """
    ).fetchall()
    now = datetime.now().isoformat(timespec="seconds")
    baseline = date.today().isoformat()
    for row in rows:
        cursor = conn.execute(
            """
            INSERT INTO securities
                (market, code, name, currency, industry, industry_manual,
                 active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                row["market"],
                str(row["code"]).strip(),
                row["name"],
                row["currency"],
                row["industry"] or "其他",
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO opening_positions
                (security_id, start_date, shares, average_cost, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                baseline,
                str(row["shares"]),
                str(row["cost_price"]),
                now,
            ),
        )

    _set_metadata(conn, "portfolio_baseline_date", baseline)
    _set_metadata(conn, "legacy_holdings_migrated", "1")
    return len(rows)


def ensure_database() -> dict:
    location_backup = _migrate_default_database_location()
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        backup = _backup_legacy_database(conn)
        _create_schema(conn)
        migrated = _migrate_legacy_holdings(conn)
        _set_metadata(conn, "schema_version", SCHEMA_VERSION)
        conn.commit()
    return {
        "migrated": migrated,
        "backup": str(backup or location_backup) if (backup or location_backup) else None,
    }


def get_setting(key: str, default: str | None = None) -> str | None:
    ensure_database()
    with get_connection() as conn:
        return _metadata(conn, key) or default


def set_setting(key: str, value: str) -> None:
    ensure_database()
    with get_connection() as conn:
        _set_metadata(conn, key, value)
        conn.commit()


def create_backup(label: str = "manual") -> Path:
    ensure_database()
    backup_dir = DB_FILE.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{DB_FILE.stem}-{label}-{stamp}.db"
    with get_connection() as source:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    return target
