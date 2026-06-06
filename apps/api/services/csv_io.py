"""CSV import/export for manual trade records."""

from __future__ import annotations

import csv
import io

from apps.api.domain import ledger


EXPORT_FIELDS = [
    "id",
    "security_id",
    "market",
    "code",
    "name",
    "industry",
    "trade_date",
    "side",
    "shares",
    "price",
    "reason_category",
    "note",
]


def export_trades_csv() -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for trade in ledger.list_trades():
        writer.writerow(trade)
    return output.getvalue()


def _security_id_from_row(row: dict[str, str]) -> int:
    if row.get("security_id"):
        try:
            security = ledger.get_security(int(row["security_id"]))
            return int(security["id"])
        except ledger.LedgerError:
            pass
    market = (row.get("market") or "").strip().upper()
    code = (row.get("code") or "").strip().upper()
    name = (row.get("name") or "").strip()
    industry = (row.get("industry") or "其他").strip()
    existing = ledger.find_security(market, code)
    if existing:
        return int(existing["id"])
    return ledger.create_security(market, code, name, industry)


def import_trades_csv(content: str) -> dict:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return {"status": "failed", "imported": 0, "errors": ["CSV 缺少表头"]}

    imported = 0
    earliest_date: str | None = None
    errors: list[str] = []
    for index, row in enumerate(reader, start=2):
        try:
            security_id = _security_id_from_row(row)
            trade_date = row["trade_date"]
            ledger.record_trade(
                security_id=security_id,
                trade_date=trade_date,
                side=row["side"],
                shares=row["shares"],
                price=row["price"],
                reason_category=row.get("reason_category") or "",
                note=row.get("note") or "",
            )
            earliest_date = trade_date if earliest_date is None else min(earliest_date, trade_date)
            imported += 1
        except Exception as exc:
            errors.append(f"第 {index} 行: {exc}")

    return {
        "status": "partial" if errors else "ok",
        "imported": imported,
        "earliest_date": earliest_date,
        "errors": errors,
    }
