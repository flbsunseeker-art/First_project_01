import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from apps.api.domain import ledger
from apps.api.adapters import market_data
from apps.api.repositories import storage
from apps.api.services import diagnosis, valuation, weekly


class WeeklyReviewTests(unittest.TestCase):
    def test_new_diagnosis_archive_starts_fresh_and_rejects_future_evidence(self):
        cutoff = date(2026, 11, 22)
        source = diagnosis.Evidence(
            title="测试公告", url="https://example.com/report", published_on=cutoff
        )
        analysis = diagnosis.Analysis(
            summary="组合观察", strategy_summary="维持", outside_summary="暂无",
            findings=[], strategies=[], outside=[], evidence={"filing": source},
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(storage, "DB_FILE", Path(tmp) / "ledger.db"),
            patch.object(diagnosis, "scan_week", return_value={"assets": []}),
        ):
            with weekly.archive() as conn:
                conn.execute("INSERT INTO editions VALUES ('2026-11-13', 1, '{}', '2026-11-15')")
            self.assertIsNone(diagnosis.read_report()["report"])
            with self.assertRaisesRegex(ValueError, "披露日期"):
                diagnosis.publish(cutoff, analysis)
            analysis.evidence.clear()
            diagnosis.publish(cutoff, analysis)
            diagnosis.publish(cutoff, analysis)
            result = diagnosis.read_report()
            self.assertEqual([item["cutoff"] for item in result["editions"]], ["2026-11-22"])
            self.assertEqual(result["report"]["number"], 1)
            self.assertEqual(result["report"]["analysis"]["summary"], "组合观察")
            self.assertEqual(result["report"]["snapshot"]["stock_ranks"], {"gains": [], "losses": []})

    def test_editorial_revision_reuses_snapshot_and_validates_deferred_sources(self):
        cutoff = date(2026, 11, 22)
        analysis = diagnosis.Analysis(
            summary="初稿", strategy_summary="", outside_summary="",
            findings=[], strategies=[], outside=[], evidence={},
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(storage, "DB_FILE", Path(tmp) / "ledger.db"),
            patch.object(diagnosis, "scan_week", return_value={"assets": [], "total_cny": "100.01"}) as scan,
        ):
            with self.assertRaisesRegex(ValueError, "找不到"):
                diagnosis.publish(cutoff, analysis, keep_snapshot=True)
            diagnosis.publish(cutoff, analysis)
            scan.side_effect = AssertionError("修订正文不应重算历史持仓")
            analysis.summary = "修订稿"
            analysis.deferred.append(diagnosis.DeferredCandidate(title="备选行业", reason="仍待验证", evidence=["filing"]))
            with self.assertRaisesRegex(ValueError, "引用不存在"):
                diagnosis.publish(cutoff, analysis, keep_snapshot=True)
            self.assertEqual(diagnosis.read_report()["report"]["analysis"]["summary"], "初稿")
            analysis.evidence["filing"] = diagnosis.Evidence(
                title="公告", url="https://example.com/filing", published_on=date(2026, 11, 20),
            )
            diagnosis.publish(cutoff, analysis, keep_snapshot=True)
            report = diagnosis.read_report()["report"]
            self.assertEqual(report["snapshot"]["total_cny"], "100.01")
            self.assertEqual(report["analysis"]["deferred"][0]["title"], "备选行业")
            scan.assert_called_once_with(cutoff)

    def test_diagnosis_rankings_use_only_stocks_and_order_by_signed_floating_pnl(self):
        amounts = {
            "A:GAIN": "30", "US:GAIN": "200", "HK:GAIN": "50", "A:FLAT": "0",
            "A:LOSS1": "-15", "US:LOSS2": "-12", "A:LOSS3": "-9", "HK:LOSS4": "-1",
            "A:LOSS5": "-200", "A:LOSS6": "-30", "FUND:GAIN": "500", "A:ETF": "-300",
        }
        assets = [{"key": key, "floating_pnl_cny": amount} for key, amount in amounts.items()]
        ranks = diagnosis._stock_ranks(assets, amounts.keys() - {"FUND:GAIN", "A:ETF"})
        self.assertEqual(ranks["gains"], ["US:GAIN", "HK:GAIN", "A:GAIN"])
        self.assertEqual(ranks["losses"], ["A:LOSS5", "A:LOSS6", "A:LOSS1", "US:LOSS2", "A:LOSS3"])

    def test_nav_pagination_reads_past_first_page(self):
        with patch.object(market_data.requests, "get") as fetch:
            fetch.return_value.json.side_effect = [
                {
                    "TotalCount": 2,
                    "Data": {"LSJZList": [{"FSRQ": "2026-11-13", "DWJZ": "1.23"}]},
                },
                {
                    "TotalCount": 2,
                    "Data": {"LSJZList": [{"FSRQ": "2026-11-12", "DWJZ": "1.22"}]},
                },
            ]
            rows = market_data._fund_nav_history(
                "018043", date(2026, 11, 12), date(2026, 11, 13)
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(fetch.call_args.kwargs["params"]["pageIndex"], 2)

    def test_profitable_growing_business_with_negative_cash_requires_review(self):
        stock = {"market": "A", "code": "000001", "industry": "家电制造", "price": "15"}
        filing = dict(
            period="2026-06-30",
            available="2026-08-18",
            label="2026年中报",
            sales="8",
            earnings="10",
            profit="100",
            bps="10",
            eps="2",
            cash_ps="-1",
        )
        weekly.assess(stock, [filing], "2026-09-18")
        self.assertEqual(stock["direction"], "优先复核回款")
        self.assertIn("1.50", stock["valuation"])
        self.assertIn("-0.50", stock["reason"])

    def test_historical_archive_flows_ranking_and_cutoff(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(storage, "DB_FILE", Path(tmp) / "ledger.db"),
            patch.object(weekly, "evidence", return_value=[]),
        ):
            storage.ensure_database()
            stock = ledger.create_security("A", "600000", "股票", "银行")
            fund = ledger.create_security(
                "FUND", "000001", "基金", asset_type="MUTUAL_FUND"
            )
            ledger.record_trade(stock, "2026-09-11", "BUY", 10, 100)
            ledger.record_trade(fund, "2026-09-18", "BUY", 100, 1)
            for day, prices in [
                ("2026-09-11", [(stock, 100)]),
                ("2026-09-18", [(stock, 110), (fund, 1)]),
            ]:
                with storage.get_connection() as conn:
                    for sid, price in prices:
                        conn.execute(
                            "INSERT INTO market_prices VALUES (?,?,?,'test','ok',?)",
                            (sid, day, str(price), day),
                        )
                valuation._save_snapshot(
                    valuation.value_portfolio(date.fromisoformat(day))
                )
            week = date(2026, 9, 18)
            result = weekly.report(week)
            self.assertEqual(weekly.D(result["profit"]), 100)
            self.assertEqual(weekly.D(result["flow"]), 100)
            self.assertEqual([s["name"] for s in result["gain"]], ["股票"])
            self.assertFalse(result["loss"])
            self.assertEqual(result["gain"][0]["direction"], "等待证据")
            self.assertEqual(weekly.report(week)["revision"], 1)
            self.assertEqual(weekly.report(week, 1)["profit"], result["profit"])
            card = result["gain"][0]
            weekly.assess(
                card,
                [{"period": "2026-06-30", "available": "2026-09-19"}],
                "2026-09-18",
            )
            self.assertIsNone(card["report"])
