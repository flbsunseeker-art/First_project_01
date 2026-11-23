"""One market refresh at startup, with an explicit retry and read-only status."""

from datetime import date, datetime
import logging
from threading import Lock, Thread

from apps.api.core.config import settings
from apps.api.core.market_time import portfolio_closed_through
from apps.api.domain import ledger
from apps.api.services import funds, valuation
from apps.api.services.overview import valuation_overview


logger = logging.getLogger(__name__)
_lock = Lock()
_state = {"status": "idle", "phase": None, "finished_at": None, "warnings": []}


def status() -> dict:
    with _lock:
        state = _state.copy()
    current = valuation.latest_current_valuation()
    state["overview"] = valuation_overview(current) if current and not current["missing"] else None
    return state


def start() -> dict:
    with _lock:
        if _state["status"] != "running":
            _state.update(status="running", phase="quotes", warnings=[], finished_at=None)
            Thread(target=_run, name="stockpilot-market-refresh", daemon=True).start()
    return status()


def _finish(result: str, warnings: list[str]) -> None:
    with _lock:
        _state.update(
            status=result, phase=None, warnings=warnings,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


def _run() -> None:
    if settings.offline_mode:
        _finish("offline", [])
        return
    warnings: list[str] = []
    try:
        from apps.api.adapters import market_data

        positions = ledger.calculate_positions(date.today())
        ids = {key for key, position in positions.items() if position.shares > 0}
        ids.update(plan["security_id"] for plan in funds.list_plans(active_only=True))
        nav_errors = market_data.refresh_fund_navs(
            [item for item in ledger.list_securities() if item["id"] in ids],
            force=True, primary_only=True,
        )
        if nav_errors:
            logger.warning("Fund NAV refresh issues: %s", "; ".join(nav_errors))
            warnings.append(f"{len(nav_errors)} 只基金未能核对最新净值")
        installment_sync = funds.sync_recurring_investments(refresh_navs=False)
        current = valuation.current_valuation(refresh_funds=False, force_refresh=True)
        warnings.extend(current["warnings"])
        if current["missing"]:
            warnings.append(f"缺少估值所需数据：{'、'.join(current['missing'])}")
        with _lock:
            _state.update(phase="history", warnings=warnings.copy())
        if installment_sync["earliest_date"]:
            result = valuation.backfill_snapshots(
                date.fromisoformat(installment_sync["earliest_date"]),
                portfolio_closed_through(),
            )
        else:
            result = valuation.auto_backfill(repair_history=False)
        if result["status"] != "ok":
            warnings.append("收盘快照暂未补齐")
    except Exception:
        logger.exception("Portfolio refresh failed")
        _finish("failed", [*warnings, "本次刷新未完成"])
        return
    _finish("failed" if current["missing"] else "partial" if warnings else "ok", warnings)
