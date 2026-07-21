from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation import (  # noqa: E402
    analyze_session,
    apply_human_ratings,
    compare_reports,
    load_json,
    rating_template,
    render_comparison_markdown,
    render_report_markdown,
    save_json,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Evaluate an Academic Roundtable JSON export without calling an LLM provider."
    )
    subcommands = result.add_subparsers(dest="command", required=True)

    evaluate = subcommands.add_parser("evaluate", help="Create diagnostics and a human rating worksheet")
    evaluate.add_argument("session", type=Path, help="Session JSON exported from the closeout page")
    evaluate.add_argument("--ratings", type=Path, help="Completed ratings JSON from a prior run")
    evaluate.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "results")
    evaluate.add_argument("--label", help="Stable output label; defaults to the session id")

    compare = subcommands.add_parser("compare", help="Compare baseline and candidate evaluation reports")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "comparison.json")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "compare":
        comparison = compare_reports(load_json(args.baseline), load_json(args.candidate))
        save_json(args.output, comparison)
        markdown_output = args.output.with_suffix(".md")
        markdown_output.write_text(render_comparison_markdown(comparison), encoding="utf-8")
        print(f"Comparison: {args.output}")
        print(f"Readable comparison: {markdown_output}")
        print(f"Decision: {comparison['decision']}")
        return 0

    session = load_json(args.session)
    report = analyze_session(session)
    if args.ratings:
        report = apply_human_ratings(report, load_json(args.ratings))
    label = args.label or str(session.get("id") or args.session.stem)
    output_dir = args.output_dir
    report_path = output_dir / f"{label}.evaluation.json"
    markdown_path = output_dir / f"{label}.evaluation.md"
    ratings_path = output_dir / f"{label}.ratings.json"
    save_json(report_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_report_markdown(report), encoding="utf-8")
    if not args.ratings or not ratings_path.exists():
        save_json(ratings_path, rating_template(session))
    print(f"Evaluation: {report_path}")
    print(f"Readable report: {markdown_path}")
    print(f"Human ratings: {ratings_path}")
    if report["warnings"]:
        print("Gate warnings: " + ", ".join(report["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
