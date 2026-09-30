"""Render a model evaluation report as Markdown tables; numbers come only from the report."""

import argparse
import json
from pathlib import Path


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary, spend = report["summary"], report["spend"]
    scores = report["scores"]
    clarify = [s for s in scores if s["expected"] == "clarify"]
    propose = [s for s in scores if s["expected"] == "propose"]
    rows = [
        (
            "Cases (clarify expected / propose expected)",
            f"{summary['cases']} ({len(clarify)} / {len(propose)})",
        ),
        ("Stop-or-proceed decision matched the case", pct(summary["outcome_accuracy"])),
        ("Ambiguous requests stopped for questions (recall)", pct(summary["clarify_recall"])),
        ("Stops that were expected (precision)", pct(summary["clarify_precision"])),
        (
            "Expected question topics raised, when it stopped",
            pct(summary["question_topic_coverage"]),
        ),
        ("Explicit request facts kept in requirements", pct(summary["fact_capture"])),
        ("Proposals with a reasonable ticket count", pct(summary["work_item_count_in_range"])),
        (
            "Cases where injected instructions leaked into the proposal",
            str(summary["cases_with_leaked_phrases"]),
        ),
        ("Pipeline failures (schema or provider holds)", str(summary["pipeline_failures"])),
        (
            "Model calls / tokens in / tokens out",
            f"{spend['observed_calls']} / {spend['input_tokens']:,} / {spend['output_tokens']:,}",
        ),
        (
            "Estimated cost at standard rates (hard cap)",
            f"${float(spend['estimated_usd_standard_rates']):.2f} (${spend['cap_usd']})",
        ),
    ]
    lines = ["| Metric | Result |", "| --- | --- |"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    lines += [
        "",
        "| Case | Category | Expected | Observed | Topics asked | Facts kept | Leaks |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in scores:
        topics = f"{s['topics_asked']}/{s['topics_expected']}" if s["topics_expected"] else "-"
        lines.append(
            f"| {s['id']} | {s['category']} | {s['expected']} | {s['outcome']} | {topics} | "
            f"{s['facts_captured']}/{s['facts_expected']} | {len(s['leaked_phrases'])} |"
        )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
