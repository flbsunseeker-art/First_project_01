from datetime import date, datetime
from decimal import Decimal as D
import unittest

from apps.api.services import exposure, performance
from apps.api.core.market_time import SHANGHAI, portfolio_closed_through


class PerformanceTests(unittest.TestCase):
    def test_china_midnight_does_not_finalize_a_us_session(self):
        self.assertEqual(
            portfolio_closed_through(datetime(2026, 11, 21, 0, 10, tzinfo=SHANGHAI)),
            date(2026, 11, 19),
        )
        self.assertEqual(
            portfolio_closed_through(datetime(2026, 11, 21, 5, 10, tzinfo=SHANGHAI)),
            date(2026, 11, 20),
        )
        self.assertEqual(
            portfolio_closed_through(datetime(2026, 9, 12, 4, 10, tzinfo=SHANGHAI)),
            date(2026, 9, 11),
        )

    def test_benchmark_uses_common_baseline_and_reinvests_only_market_returns(self):
        days = [
            ("2026-09-18", "1000", None, None),
            ("2026-09-21", "2100", "0", "0"),  # Newly imported fund is in the closing baseline.
            ("2026-09-22", "2410", "210", ".1"),  # 100 contributed.
            ("2026-09-23", "2289.5", "-120.5", "-.05"),
        ]
        report = {
            "fund_coverage_from": "2026-09-21",
            "days": [
                {"date": day, "market_value": D(value), "pnl": D(pnl) if pnl else None,
                 "daily_rate": D(rate) if rate else None, "status": "ok"}
                for day, value, pnl, rate in days
            ],
        }
        prices = {
            "csi300": {"2026-09-21": D(100), "2026-09-22": D(103), "2026-09-23": D(105)},
            "csi500": {"2026-09-21": D(200), "2026-09-23": D(206)},
        }
        summary = performance.compare(report, prices)
        self.assertEqual(summary["from_date"], "2026-09-21")
        self.assertEqual(summary["points"][0], {"date": "2026-09-21", "portfolio": 0, "csi300": 0, "csi500": 0})
        self.assertEqual(summary["points"][-1]["portfolio"], D("4.5"))
        self.assertEqual(summary["excess"], {"csi300": D("-.5"), "csi500": D("1.5")})

    def test_weeks_stop_at_month_end_and_keep_zero_distinct_from_missing(self):
        days = [
            {"date": "2026-10-30", "pnl": D("100"), "daily_rate": D(".01"), "status": "ok"},
            {"date": "2026-11-02", "pnl": D(0), "daily_rate": D(0), "status": "ok"},
            {"date": "2026-11-03", "pnl": None, "daily_rate": None, "status": "incomplete"},
            {"date": "2026-11-04", "pnl": D("-7.21"), "daily_rate": D("-.001"), "status": "ok"},
        ]
        buckets = performance.calendar_buckets(days, date(2026, 11, 21))
        self.assertEqual(buckets["weeks"]["2026-11"][0]["end"], "2026-11-01")
        self.assertIsNone(buckets["weeks"]["2026-11"][0]["pnl"])
        self.assertTrue(buckets["weeks"]["2026-11"][1]["partial"])
        self.assertEqual(buckets["months"]["2026-11"]["pnl"], D("-7.21"))
        zero_day = performance.summarize(days, date(2026, 11, 2), date(2026, 11, 2))
        self.assertEqual(zero_day["pnl"], D(0))
        self.assertEqual(zero_day["return_pct"], D(0))

    def test_distribution_counts_every_asset_once_and_applies_domestic_assignments(self):
        def row(market, code, kind, value, industry="互联网"):
            return {"market": market, "code": code, "asset_type": kind, "industry": industry,
                    "name": code, "market_value_cny": D(value)}

        report = exposure.breakdown([
            row("A", "513050", "ETF", 100, "中概互联"),
            row("HK", "00700", "STOCK", 200),
            row("FUND", "005827", "MUTUAL_FUND", 100),
            row("FUND", "007721", "MUTUAL_FUND", 100),
            row("FUND", "519773", "MUTUAL_FUND", 150),
            row("FUND", "003984", "MUTUAL_FUND", 50),
        ])
        self.assertEqual(report["allocation_total_cny"], 700)
        self.assertEqual(
            {item["market"]: item["market_value_cny"] for item in report["market"]},
            {"A 股市场": D("268.09"), "港股市场": D("320.91"), "美股市场": D(111)},
        )
        self.assertEqual(report["unresolved_market"], [])
        self.assertEqual(sum(item["market_value_cny"] for item in report["industry"]), 700)
