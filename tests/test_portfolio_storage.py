import json

import portfolio


def _use_temp_storage(tmp_path):
    portfolio.PORTFOLIO_FILE = tmp_path / "portfolio.json"
    portfolio.PORTFOLIO_DB_FILE = tmp_path / "portfolio.db"


def test_migrates_json_to_sqlite_once(tmp_path):
    _use_temp_storage(tmp_path)
    portfolio.PORTFOLIO_FILE.write_text(
        json.dumps({
            "holdings": [
                {
                    "market": "A",
                    "name": "测试股票",
                    "code": "600519",
                    "cost_price": 100.0,
                    "shares": 10,
                    "currency": "CNY",
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    data = portfolio.load_portfolio()

    assert data["holdings"] == [
        {
            "market": "A",
            "name": "测试股票",
            "code": "600519",
            "cost_price": 100.0,
            "shares": 10,
            "currency": "CNY",
            "industry": "食品饮料",
        }
    ]


def test_add_update_and_remove_holding(tmp_path):
    _use_temp_storage(tmp_path)

    portfolio.add_holding("US", "Apple", "AAPL", 150.0, 5)
    data = portfolio.load_portfolio()
    data["holdings"][0]["shares"] = 6
    portfolio.save_portfolio(data)
    portfolio.remove_holding(0)

    assert portfolio.load_portfolio() == {"holdings": []}


def test_empty_database_does_not_reimport_after_delete(tmp_path):
    _use_temp_storage(tmp_path)
    portfolio.PORTFOLIO_FILE.write_text(
        json.dumps({
            "holdings": [
                {
                    "market": "HK",
                    "name": "测试港股",
                    "code": "00700",
                    "cost_price": 20.0,
                    "shares": 100,
                    "currency": "HKD",
                    "industry": "互联网",
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    assert len(portfolio.load_portfolio()["holdings"]) == 1
    portfolio.save_portfolio({"holdings": []})

    assert portfolio.load_portfolio() == {"holdings": []}
