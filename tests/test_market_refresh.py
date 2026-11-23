import threading
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import requests

from apps.api.adapters import fetcher, market_data
from apps.api.services import market_refresh


class MarketRefreshTests(unittest.TestCase):
    def test_startup_nav_retries_transient_timeout_once(self):
        security = {"id": 1, "code": "000001"}
        day = date(2026, 11, 23)
        rows = [(day.isoformat(), Decimal("1.04"))]
        with (
            patch.object(market_data, "_fund_nav_history", side_effect=[requests.Timeout(), rows]) as fetch,
            patch.object(market_data, "_upsert_prices") as save,
        ):
            market_data._refresh_primary_nav(security, day, day)
        self.assertEqual(fetch.call_count, 2)
        save.assert_called_once_with(1, rows, "eastmoney-fund-nav")

    def test_refresh_requests_share_running_job(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def refresh():
            started.set()
            release.wait(timeout=2)
            market_refresh._finish("ok", [])
            finished.set()

        initial = {"status": "idle", "phase": None, "warnings": [], "finished_at": None}
        with (
            patch.object(market_refresh, "_state", initial),
            patch.object(market_refresh, "_run", side_effect=refresh) as worker,
            patch.object(market_refresh.valuation, "latest_current_valuation", return_value=None),
        ):
            self.assertEqual(market_refresh.start()["status"], "running")
            try:
                self.assertTrue(started.wait(timeout=2))
                self.assertEqual(market_refresh.start()["status"], "running")
                self.assertEqual(worker.call_count, 1)
            finally:
                release.set()
                self.assertTrue(finished.wait(timeout=2))
            self.assertEqual(market_refresh.status()["status"], "ok")

    def test_sina_us_quote_retains_new_york_session_date(self):
        fields = [""] * 27
        fields[0], fields[1], fields[3], fields[26] = (
            "TEST", "110", "2026-11-21 04:59:59", "100",
        )
        response = SimpleNamespace(text='var hq_str_gb_test="' + ",".join(fields) + '";')
        with patch.object(fetcher._session, "get", return_value=response):
            quote = fetcher.get_us_stock_price("TEST")
        self.assertEqual(quote["price_date"], "2026-11-20")

    def test_older_provider_quote_cannot_replace_newer_cached_price(self):
        security = {"id": 1, "market": "A", "code": "600001", "currency": "CNY"}
        reply = {"price": 10, "price_date": "2026-10-09"}
        cached = {"close_price": "11", "price_date": "2026-10-12", "status": "ok"}
        warnings = []
        with (
            patch.object(market_data, "settings", SimpleNamespace(offline_mode=False)),
            patch.object(market_data, "fetch_stock_price", return_value=reply),
            patch.object(market_data, "get_cached_price_record", return_value=cached),
        ):
            prices, _ = market_data.get_live_prices([security], refresh_navs=False, warnings=warnings)
        self.assertEqual(prices[1]["price_date"], "2026-10-12")
        self.assertEqual(prices[1]["status"], "cached")
        self.assertEqual(warnings, ["600001 行情沿用缓存"])
