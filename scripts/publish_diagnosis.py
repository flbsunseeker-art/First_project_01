"""Scan the dated ledger, or publish a verified analysis into the local archive."""

import argparse
from datetime import date
import json
from pathlib import Path

from apps.api.services import diagnosis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cutoff", type=date.fromisoformat, help="北京时间周日，格式 YYYY-MM-DD")
    parser.add_argument("--analysis", type=Path, help="待发布的证据和分析 JSON 文件")
    parser.add_argument("--keep-snapshot", action="store_true", help="修订已有周报正文，使用该期归档估值")
    args = parser.parse_args()
    if args.analysis is None:
        if args.keep_snapshot:
            parser.error("--keep-snapshot 需同时指定 --analysis")
        result = diagnosis.scan_week(args.cutoff)
        editions = diagnosis.read_report()["editions"]
        previous = next((e for e in editions if e["cutoff"] < args.cutoff.isoformat()), None)
        if previous:
            report = diagnosis.read_report(date.fromisoformat(previous["cutoff"]))["report"]
            result["previous_review"] = {
                "cutoff": previous["cutoff"],
                "findings": report["analysis"]["findings"],
                "strategies": report["analysis"]["strategies"],
                "outside": report["analysis"]["outside"],
            }
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    analysis = diagnosis.Analysis.model_validate_json(args.analysis.read_text(encoding="utf-8"))
    diagnosis.publish(args.cutoff, analysis, keep_snapshot=args.keep_snapshot)
    print(f"已发布周报 · {args.cutoff.isoformat()}")


if __name__ == "__main__":
    main()
