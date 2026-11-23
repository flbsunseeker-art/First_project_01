import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from apps.api.adapters import market_data
from apps.api.domain import ledger
from apps.api.repositories import storage
from apps.api.routers import v1
from apps.api.services import csv_io, funds, valuation


class PortfolioTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = storage.DB_FILE
        storage.DB_FILE = Path(self.temp_dir.name) / "portfolio.db"
        valuation.invalidate_caches()
        market_data._fund_nav_refresh_at.clear()

    def tearDown(self):
        valuation.invalidate_caches()
        market_data._fund_nav_refresh_at.clear()
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

    def test_current_schema_migration_preserves_v2_trades(self):
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
        self.assertEqual(schema_version, "5")

    def test_mutual_fund_opening_position_preserves_exact_cost(self):
        storage.ensure_database()
        security_id = ledger.create_security(
            "FUND",
            "000001",
            "测试指数基金",
            asset_type="MUTUAL_FUND",
            fund_category="指数基金",
        )
        ledger.upsert_opening_position(
            security_id,
            "2026-09-19",
            "2468.13",
            "5321.47",
            baseline_value_cny="4987.23",
        )

        security = ledger.get_security(security_id)
        opening = ledger.list_opening_positions()[0]

        self.assertEqual(security["market"], "FUND")
        self.assertEqual(security["asset_type"], "MUTUAL_FUND")
        self.assertEqual(Decimal(opening["cost_amount"]), Decimal("5321.47"))
        self.assertEqual(
            Decimal(opening["average_cost"]),
            Decimal("5321.47") / Decimal("2468.13"),
        )

    def test_daily_fund_plan_creates_idempotent_trades_from_nav_dates(self):
        storage.ensure_database()
        security_id = ledger.create_security(
            "FUND", "007721", "天弘标普500", asset_type="MUTUAL_FUND"
        )
        plan_id = funds.upsert_plan(security_id, "100", "2026-09-17")
        self.seed_price(security_id, "2026-09-17", "2")
        self.seed_price(security_id, "2026-09-18", "2.5")

        first = funds.sync_recurring_investments(refresh_navs=False)
        second = funds.sync_recurring_investments(refresh_navs=False)

        self.assertEqual(first["created"], 2)
        self.assertEqual(second["created"], 0)
        self.assertEqual(len(ledger.list_trades()), 2)
        position = ledger.calculate_positions("2026-09-18")[security_id]
        self.assertEqual(position.shares, Decimal("90"))
        with storage.get_connection() as conn:
            executions = conn.execute(
                "SELECT COUNT(*) AS n FROM fund_plan_executions WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()["n"]
        self.assertEqual(executions, 2)

    def test_refreshing_one_fund_does_not_suppress_other_fund_navs(self):
        first_id = ledger.create_security("FUND", "003547", "鹏华丰禄债券")
        second_id = ledger.create_security("FUND", "007721", "天弘标普 500")
        first, second = ledger.get_security(first_id), ledger.get_security(second_id)
        with patch.object(market_data, "fetch_historical_prices") as fetch:
            self.assertEqual(market_data.refresh_fund_navs([first]), [])
            self.assertEqual(market_data.refresh_fund_navs([first, second]), [])
        self.assertEqual([call.args[0]["id"] for call in fetch.call_args_list], [first_id, second_id])

    def test_fund_plan_waits_for_next_trading_nav_and_rebooks_pending_trade_once(self):
        fund_id = ledger.create_security("FUND", "003547", "鹏华丰禄债券")
        paused_id = ledger.create_security("FUND", "007721", "天弘标普500")
        plan_id = funds.upsert_plan(fund_id, "100", "2026-09-18")
        funds.upsert_plan(paused_id, "100", "2026-09-18", active=False)
        self.seed_price(fund_id, "2026-09-18", "1.25")
        self.seed_price(paused_id, "2026-09-18", "2")
        with patch.object(funds, "date", wraps=date) as clock:
            clock.today.return_value = date(2026, 9, 18)
            self.assertEqual(funds.sync_recurring_investments(False)["created"], 1)
            trade_id = ledger.list_trades()[0]["id"]
            with storage.get_connection() as conn:
                conn.execute(
                    "UPDATE fund_investment_plans SET confirm_on_next_nav = 1 WHERE id = ?",
                    (plan_id,),
                )
                conn.execute(
                    "INSERT INTO voided_trades VALUES (?, '待确认', '2026-09-18')",
                    (trade_id,),
                )
                conn.commit()
            self.seed_price(fund_id, "2026-09-19", "1.30")
            self.seed_price(fund_id, "2026-09-21", "1.50")
            clock.today.return_value = date(2026, 9, 20)
            self.assertEqual(funds.sync_recurring_investments(False)["created"], 0)
            clock.today.return_value = date(2026, 9, 21)
            self.assertEqual(funds.sync_recurring_investments(False)["created"], 1)
            self.assertEqual(funds.sync_recurring_investments(False)["created"], 0)

        trades = ledger.list_trades()
        self.assertEqual([(t["code"], t["trade_date"]) for t in trades], [("003547", "2026-09-21")])
        self.assertEqual(Decimal(trades[0]["shares"]), Decimal("80"))
        self.assertEqual(ledger.calculate_positions("2026-09-18"), {})

    def test_reconciliation_preserves_history_and_excludes_quantity_change_from_profit(self):
        stock_id = ledger.create_security("A", "600000", "测试股票")
        ledger.upsert_opening_position(stock_id, "2026-09-17", 10, 800)
        invalid = ledger.record_trade(stock_id, "2026-09-18", "BUY", 1, 90)
        self.seed_price(stock_id, "2026-09-17", 90)
        self.seed_price(stock_id, "2026-09-18", 100)
        valuation._save_snapshot(valuation.value_portfolio(date(2026, 9, 17)))
        with storage.get_connection() as conn:
            conn.execute(
                "INSERT INTO voided_trades VALUES (?, '未成交', '2026-09-18')", (invalid,)
            )
            conn.execute(
                """INSERT INTO position_reconciliations
                   (security_id, effective_date, shares, cost_amount, source_note, after_trade_sequence)
                   VALUES (?, '2026-09-18', '12', '1020', '对账', 1)""",
                (stock_id,),
            )
            conn.commit()

        self.assertEqual(ledger.calculate_positions("2026-09-17")[stock_id].shares, 10)
        snapshot = valuation.value_portfolio(date(2026, 9, 18))
        self.assertEqual(snapshot["details"][0]["shares"], 12)
        self.assertEqual(snapshot["total_cost_cny"], 1020)
        self.assertEqual(snapshot["external_flow_cny"], 200)
        self.assertEqual(snapshot["buy_flow_cny"], 0)
        self.assertEqual(snapshot["daily_pnl_cny"], 100)

        ledger.record_trade(stock_id, "2026-09-18", "SELL", 2, 110)
        self.assertEqual(ledger.calculate_positions("2026-09-18")[stock_id].shares, 10)
        self.assertEqual(ledger.realized_events("2026-09-18")[0]["realized_pnl_native"], 50)

    def test_new_fund_baseline_is_not_counted_as_daily_profit(self):
        storage.ensure_database()
        stock_id = ledger.create_security("A", "600000", "测试股票", "银行")
        ledger.record_trade(stock_id, "2026-09-18", "BUY", 10, 100)
        self.seed_price(stock_id, "2026-09-18", 100)
        valuation._save_snapshot(valuation.value_portfolio(date(2026, 9, 18)))

        fund_id = ledger.create_security(
            "FUND", "003547", "鹏华丰禄债券", asset_type="MUTUAL_FUND"
        )
        ledger.upsert_opening_position(
            fund_id,
            "2026-09-19",
            400,
            450,
            baseline_value_cny=500,
        )
        self.seed_price(stock_id, "2026-09-21", 100)
        self.seed_price(fund_id, "2026-09-21", "1.25")

        snapshot = valuation.value_portfolio(date(2026, 9, 21))

        self.assertEqual(snapshot["total_market_value_cny"], Decimal("1500.00"))
        self.assertEqual(snapshot["external_flow_cny"], Decimal("500"))
        self.assertEqual(snapshot["daily_pnl_cny"], Decimal("0.00"))

    def test_asset_value_trends_keep_stocks_and_funds_separate(self):
        storage.ensure_database()
        stock_id = ledger.create_security("A", "600000", "测试股票", "银行")
        fund_id = ledger.create_security(
            "FUND", "003547", "鹏华丰禄债券", asset_type="MUTUAL_FUND"
        )
        ledger.upsert_opening_position(stock_id, "2026-09-18", 10, 100)
        ledger.upsert_opening_position(fund_id, "2026-09-18", 400, "1.2")
        self.seed_price(stock_id, "2026-09-18", 100)
        self.seed_price(fund_id, "2026-09-18", "1.25")
        valuation._save_snapshot(valuation.value_portfolio(date(2026, 9, 18)))

        stock_trend = valuation.get_asset_value_trend(
            "stocks", date(2026, 9, 18), date(2026, 9, 18)
        )
        fund_trend = valuation.get_asset_value_trend(
            "funds", date(2026, 9, 18), date(2026, 9, 18)
        )

        self.assertEqual(stock_trend[0]["total_market_value_cny"], Decimal("1000"))
        self.assertEqual(fund_trend[0]["total_market_value_cny"], Decimal("500.00"))

    def test_overview_snapshot_reads_without_waiting_on_market_data(self):
        stock_id = ledger.create_security("A", "600000", "测试股票", "银行")
        ledger.upsert_opening_position(stock_id, "2026-09-18", 10, 1000)
        self.seed_price(stock_id, "2026-09-18", 120)
        valuation._save_snapshot(valuation.value_portfolio(date(2026, 9, 18)))
        valuation._record_incomplete(date(2026, 9, 21), "行情缺失")

        with (
            patch.object(v1, "_current") as current,
            patch.object(valuation, "auto_backfill") as backfill,
        ):
            overview = v1.get_overview(snapshot_only=True)
            self.assertEqual(v1.get_overview(), overview)
            trend = v1.get_value_trend(asset_group="stocks", snapshot_only=True)
            current.assert_not_called()
            backfill.assert_not_called()

        self.assertEqual(overview["status"], "snapshot")
        self.assertEqual(overview["snapshot_date"], "2026-09-18")
        self.assertEqual(overview["latest_snapshot"]["snapshot_date"], "2026-09-21")
        self.assertEqual(overview["total_market_value_cny"], "1200")
        self.assertEqual(overview["total_cost_cny"], "1000")
        self.assertEqual(Decimal(overview["total_pnl_pct"]), Decimal("20"))
        self.assertNotIn("today_pnl_cny", overview)
        self.assertEqual([row["total_market_value_cny"] for row in trend], ["1200"])

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

    def test_short_history_gap_triggers_price_and_rate_refresh(self):
        storage.ensure_database()
        security_id = ledger.create_security("US", "AAPL", "Apple", "消费电子")
        self.seed_price(security_id, "2026-01-02", 100)
        self.seed_price(security_id, "2026-01-08", 101)
        with storage.get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO exchange_rates
                    (currency, rate_date, cny_rate, source, status, fetched_at)
                VALUES ('USD', ?, '7.2', 'test', 'ok', '2026-01-01T00:00:00')
                """,
                [("2026-01-02",), ("2026-01-08",)],
            )
            conn.commit()

        price_calls = []
        rate_calls = []
        original_price_fetch = market_data.fetch_historical_prices
        original_rate_fetch = market_data.fetch_historical_rates
        market_data.fetch_historical_prices = (
            lambda security, start, end: price_calls.append((security["id"], start, end))
        )
        market_data.fetch_historical_rates = (
            lambda currency, start, end: rate_calls.append((currency, start, end))
        )
        try:
            security = ledger.get_security(security_id)
            market_data.ensure_price_history(
                [security], date(2026, 1, 2), date(2026, 1, 9)
            )
            market_data.ensure_rate_history(
                {"USD"}, date(2026, 1, 2), date(2026, 1, 9)
            )
        finally:
            market_data.fetch_historical_prices = original_price_fetch
            market_data.fetch_historical_rates = original_rate_fetch

        self.assertEqual(price_calls[0][2], date(2026, 1, 9))
        self.assertEqual(rate_calls[0][2], date(2026, 1, 9))

    def test_a_share_etf_history_uses_etf_specific_source(self):
        import akshare as ak

        original_etf_history = ak.fund_etf_hist_sina
        original_stock_history = ak.stock_zh_a_hist
        ak.fund_etf_hist_sina = lambda symbol: market_data.pd.DataFrame(
            [
                {"date": "2026-01-01", "close": 1.20},
                {"date": "2026-01-02", "close": 1.23},
                {"date": "2026-01-03", "close": 1.25},
            ]
        )
        ak.stock_zh_a_hist = lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("ETF 不应使用普通 A 股历史行情接口")
        )
        try:
            rows = market_data._akshare_history(
                {"market": "A", "code": "510300"},
                date(2026, 1, 2),
                date(2026, 1, 2),
            )
        finally:
            ak.fund_etf_hist_sina = original_etf_history
            ak.stock_zh_a_hist = original_stock_history

        self.assertEqual(rows, [("2026-01-02", Decimal("1.23"))])

    def test_mutual_fund_history_uses_nav_source(self):
        import akshare as ak

        original_fund_history = ak.fund_open_fund_info_em
        ak.fund_open_fund_info_em = lambda **kwargs: market_data.pd.DataFrame(
            [
                {"净值日期": "2026-09-17", "单位净值": 2.1},
                {"净值日期": "2026-09-18", "单位净值": 2.2},
            ]
        )
        try:
            rows = market_data._akshare_history(
                {
                    "market": "FUND",
                    "asset_type": "MUTUAL_FUND",
                    "code": "007721",
                },
                date(2026, 9, 18),
                date(2026, 9, 18),
            )
        finally:
            ak.fund_open_fund_info_em = original_fund_history

        self.assertEqual(rows, [("2026-09-18", Decimal("2.2"))])

    def test_live_valuation_uses_cached_rates_when_rate_fetch_falls_back(self):
        storage.ensure_database()
        security_id = ledger.create_security("US", "AAPL", "Apple", "消费电子")
        self.seed_price(security_id, "2026-01-09", 100)
        with storage.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO exchange_rates
                    (currency, rate_date, cny_rate, source, status, fetched_at)
                VALUES ('USD', '2026-01-09', '7.2', 'test', 'ok',
                        '2026-01-09T00:00:00')
                """
            )
            conn.commit()

        original_rate_fetch = market_data.get_exchange_rates
        original_price_fetch = market_data.fetch_stock_price
        market_data.get_exchange_rates = lambda: {
            "USD_CNY": 7.25,
            "HKD_CNY": 0.93,
            "_status": "fallback",
        }
        market_data.fetch_stock_price = lambda *args, **kwargs: None
        try:
            _, rates = market_data.get_live_prices([ledger.get_security(security_id)])
        finally:
            market_data.get_exchange_rates = original_rate_fetch
            market_data.fetch_stock_price = original_price_fetch

        self.assertEqual(rates["USD"], Decimal("7.2"))

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
