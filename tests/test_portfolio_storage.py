import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import ledger
import storage
import valuation


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
