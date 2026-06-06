"""Generate a standalone HTML portfolio report."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import valuation


BASE_DIR = Path(__file__).resolve().parent


def generate_report(output_dir: str | Path | None = None) -> str:
    output = Path(output_dir) if output_dir else BASE_DIR
    output.mkdir(parents=True, exist_ok=True)
    current = valuation.current_valuation()
    industry = valuation.get_industry_allocation(current["rows"])
    market: dict[str, float] = {}
    for row in current["rows"]:
        market[row["market"]] = market.get(row["market"], 0) + float(
            row["market_value_cny"]
        )

    env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
    template = env.get_template("report.html")
    html = template.render(
        generated_at=current["updated_at"],
        summary=current,
        holdings=current["rows"],
        industry=industry,
        market=market,
        scope_note="收益不包含现金、手续费和分红",
    )
    path = output / f"report_{date.today().isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    print(generate_report())
