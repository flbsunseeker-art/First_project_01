import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from apps.api.domain import ledger
from apps.api.repositories import storage
from apps.api.services import csv_io, valuation


class PortfolioTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = storage.DB_FILE
        storage.DB_FILE = Path(self.temp_dir.name) / "portfolio.db"

    def tearDown(self):
        storage.DB_FILE = self.original_db
        self.temp_dir.cleanup()

    def seed_price(self, security_id, day, price):
        storage.ensure_database()
        with storage.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO market_prices
                    (security_id, price_date, close_price, source, status, fetched_at)
                VALUES (?, ?, ?, 'test', 'ok', '2026-01-01T00:00:00')
                """,
                (security_id, day, str(price)),
            )
            conn.commit()

    def test_legacy_holdings_migrate_to_opening_positions(self):
        conn = sqlite3.connect(storage.DB_FILE)
        conn.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL, name TEXT NOT NULL, code TEXT NOT NULL,
                cost_price REAL NOT NULL, shares INTEGER NOT NULL,
                currency TEXT NOT NULL, industry TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO holdings
                (market, name, code, cost_price, shares, currency, industry,
                 created_at, updated_at)
            VALUES ('A', '测试股票', '600519', 100, 10, 'CNY', '自定义行业',
                    '2026-01-01', '2026-01-01')
            """
        )
        conn.commit()
        conn.close()

        result = storage.ensure_database()
        securities = ledger.list_securities()
        openings = ledger.list_opening_positions()

        self.assertEqual(result["migrated"], 1)
        self.assertTrue(Path(result["backup"]).exists())
        self.assertEqual(securities[0]["industry"], "自定义行业")
        self.assertEqual(openings[0]["shares"], "10")
        self.assertEqual(openings[0]["average_cost"], "100.0")

    def test_moving_average_partial_sale_and_oversell(self):
        storage.ensure_database()
        security_id = ledger.create_security("US", "AAPL", "Apple", "消费电子")
        ledger.record_trade(security_id, "2026-01-02", "BUY", 10, 100)
        ledger.record_trade(security_id, "2026-01-03", "BUY", 10, 200)
        position = ledger.calculate_positions("2026-01-03")[security_id]
        self.assertEqual(position.shares, Decimal("20"))
        self.assertEqual(position.average_cost, Decimal("150"))

        ledger.record_trade(security_id, "2026-01-04", "SELL", 5, 180)
        position = ledger.calculate_positions("2026-01-04")[security_id]
        self.assertEqual(position.shares, Decimal("15"))
        self.assertEqual(position.average_cost, Decimal("150"))
        self.assertEqual(position.realized_pnl_native, Decimal("150"))

        with self.assertRaises(ledger.LedgerError):
            ledger.record_trade(security_id, "2026-01-05", "SELL", 16, 180)
        self.assertEqual(len(ledger.list_trades()), 3)

    def test_schema_v3_migration_preserves_v2_trades(self):
        conn = sqlite3.connect(storage.DB_FILE)
        conn.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata (key, value) VALUES ('schema_version', '2');

            CREATE TABLE securities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                currency TEXT NOT NULL,
                industry TEXT NOT NULL DEFAULT '其他',
                industry_manual INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (market, code)
            );

            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                security_id INTEGER NOT NULL,
                trade_date TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                side TEXT NOT NULL,
                shares TEXT NOT NULL,
                price TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (trade_date, sequence)
            );

            CREATE TABLE opening_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                security_id INTEGER NOT NULL UNIQUE,
                start_date TEXT NOT NULL,
                shares TEXT NOT NULL,
                average_cost TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE daily_portfolio_snapshots (
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
            """
        )
        conn.execute(
            """
            INSERT INTO securities
                (market, code, name, currency, industry, created_at, updated_at)
            VALUES ('US', 'AAPL', 'Apple', 'USD', '消费电子',
                    '2026-01-01', '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO trades
                (security_id, trade_date, sequence, side, shares, price,
                 created_at, updated_at)
            VALUES (1, '2026-01-02', 1, 'BUY', '10', '100',
                    '2026-01-02', '2026-01-02')
            """
        )
        conn.execute(
            """
            INSERT INTO opening_positions
                (security_id, start_date, shares, average_cost, created_at)
            VALUES (1, '2026-01-01', '10', '90', '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO daily_portfolio_snapshots
                (snapshot_date, total_market_value_cny, daily_pnl_cny,
                 cumulative_pnl_cny, realized_pnl_cny, unrealized_pnl_cny,
                 buy_flow_cny, sell_flow_cny, status, is_final,
                 error_message, calculated_at)
            VALUES ('2026-01-02', '1000', NULL, '0', '0', '100',
                    '0', '0', 'ok', 1, NULL, '2026-01-02')
            """
        )
        conn.commit()
        conn.close()

        result = storage.ensure_database()

        self.assertTrue(Path(result["backup"]).exists())
        with storage.get_connection() as migrated:
            columns = {
                row["name"]
                for row in migrated.execute("PRAGMA table_info(trades)").fetchall()
            }
            row = migrated.execute("SELECT * FROM trades").fetchone()
            security_count = migrated.execute(
                "SELECT COUNT(*) AS n FROM securities"
            ).fetchone()["n"]
            opening_count = migrated.execute(
                "SELECT COUNT(*) AS n FROM opening_positions"
            ).fetchone()["n"]
            snapshot_count = migrated.execute(
                "SELECT COUNT(*) AS n FROM daily_portfolio_snapshots"
            ).fetchone()["n"]
            schema_version = migrated.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()["value"]

        self.assertIn("reason_category", columns)
        self.assertIn("note", columns)
        self.assertEqual(row["reason_category"], "")
        self.assertEqual(row["note"], "")
        self.assertEqual(security_count, 1)
        self.assertEqual(opening_count, 1)
        self.assertEqual(snapshot_count, 1)
        self.assertEqual(schema_version, "3")

    def test_trade_reason_and_note_can_be_saved_and_updated(self):
        storage.ensure_database()
        security_id = ledger.create_security("US", "MSFT", "Microsoft", "软件服务")
        trade_id = ledger.record_trade(
            security_id,
            "2026-01-02",
            "BUY",
            10,
            100,
            reason_category="建仓",
            note="首次买入",
        )

        trade = ledger.list_trades()[0]
        self.assertEqual(trade["reason_category"], "建仓")
        self.assertEqual(trade["note"], "首次买入")

        ledger.update_trade(
            trade_id,
            "2026-01-03",
            "BUY",
            10,
            101,
            reason_category="加仓",
            note="回调买入",
        )
        updated = ledger.list_trades()[0]
        self.assertEqual(updated["reason_category"], "加仓")
        self.assertEqual(updated["note"], "回调买入")

    def test_trade_csv_export_and_import_roundtrip(self):
        storage.ensure_database()
        security_id = ledger.create_security("A", "600000", "测试银行", "金融保险")
        ledger.record_trade(
            security_id,
            "2026-01-02",
            "BUY",
            10,
            12.3,
            reason_category="建仓",
            note="CSV 测试",
        )

        exported = csv_io.export_trades_csv()
        self.assertIn("reason_category", exported)
        self.assertIn("CSV 测试", exported)

        storage.DB_FILE = Path(self.temp_dir.name) / "imported.db"
        result = csv_io.import_trades_csv(exported)
        trades = ledger.list_trades()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["imported"], 1)
        self.assertEqual(trades[0]["code"], "600000")
        self.assertEqual(trades[0]["note"], "CSV 测试")

    def test_daily_pnl_removes_buy_cashflow(self):
        storage.ensure_database()
        security_id = ledger.create_security("A", "600000", "测试", "银行")
        ledger.record_trade(security_id, "2026-01-02", "BUY", 10, 100)
        self.seed_price(security_id, "2026-01-02", 110)
        first = valuation.backfill_snapshots(
            date(2026, 1, 2), date(2026, 1, 2)
        )
        self.assertEqual(first["status"], "ok")

        ledger.record_trade(security_id, "2026-01-05", "BUY", 10, 120)
        self.seed_price(security_id, "2026-01-05", 130)
        second = valuation.backfill_snapshots(
            date(2026, 1, 5), date(2026, 1, 5)
        )
        self.assertEqual(second["status"], "ok")
        rows = valuation.get_daily_returns()
        self.assertIsNone(rows[0]["daily_pnl_cny"])
        self.assertEqual(Decimal(rows[1]["daily_pnl_cny"]), Decimal("300"))
        valuation.backfill_snapshots(date(2026, 1, 5), date(2026, 1, 5))
        self.assertEqual(len(valuation.get_daily_returns()), 2)

    def test_missing_market_data_records_incomplete_status(self):
        storage.ensure_database()
        security_id = ledger.create_security("A", "600001", "缺行情测试", "银行")
        ledger.record_trade(security_id, "2026-01-02", "BUY", 10, 100)
        original_prices = valuation._market_data().ensure_price_history
        original_rates = valuation._market_data().ensure_rate_history
        valuation._market_data().ensure_price_history = lambda *args, **kwargs: None
        valuation._market_data().ensure_rate_history = lambda *args, **kwargs: None

        try:
            result = valuation.backfill_snapshots(
                date(2026, 1, 2), date(2026, 1, 2)
            )
        finally:
            valuation._market_data().ensure_price_history = original_prices
            valuation._market_data().ensure_rate_history = original_rates

        with storage.get_connection() as conn:
            snapshot = conn.execute(
                """
                SELECT status, error_message FROM daily_portfolio_snapshots
                WHERE snapshot_date = '2026-01-02'
                """
            ).fetchone()

        self.assertEqual(result["status"], "partial")
        self.assertEqual(snapshot["status"], "incomplete")
        self.assertIn("缺少", snapshot["error_message"])

    def test_industry_allocation_matches_total_value(self):
        rows = [
            {"industry": "科技", "market_value_cny": Decimal("300")},
            {"industry": "科技", "market_value_cny": Decimal("200")},
            {"industry": "消费", "market_value_cny": Decimal("500")},
        ]
        allocation = valuation.get_industry_allocation(rows)
        self.assertEqual(
            sum(item["market_value_cny"] for item in allocation),
            Decimal("1000"),
        )
        self.assertEqual(
            sum(item["position_pct"] for item in allocation),
            Decimal("100"),
        )

    def test_manual_industry_update_persists(self):
        storage.ensure_database()
        security_id = ledger.create_security("US", "NVDA", "NVIDIA", "")
        self.assertEqual(ledger.get_security(security_id)["industry"], "半导体")
        ledger.update_security_industry(security_id, "人工智能")
        updated = ledger.get_security(security_id)
        self.assertEqual(updated["industry"], "人工智能")
        self.assertEqual(updated["industry_manual"], 1)


if __name__ == "__main__":
    unittest.main()
