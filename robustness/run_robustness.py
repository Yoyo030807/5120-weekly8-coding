#!/usr/bin/env python3
"""Track A robustness harness: 10 messy inputs must degrade gracefully.

Contract
--------
* no input may crash the batch; every input yields exactly one output row;
* unusable inputs (empty / whitespace / null) become ``unresolved`` rows AND
  are written to logs/repair.log;
* every other dirty input still returns a schema-valid record;
* the over-long input must travel through the summarizer subagent;
* prompt-injection / embedded-JSON inputs must not hijack the labels
  (instructions inside segment text are data, not commands).

Run:  python robustness/run_robustness.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extract import (  # noqa: E402
    UNRESOLVED_SOURCE,
    configure_repair_logger,
    mock_extract,
    to_output_row,
)
from src.schema import ExtractionRecord  # noqa: E402
from src.summarizer import SUMMARY_THRESHOLD_CHARS, maybe_summarize  # noqa: E402

INPUTS = REPO_ROOT / "robustness" / "inputs" / "dirty_segments.jsonl"
LOG_PATH = REPO_ROOT / "logs" / "repair.log"
REPORT_PATH = REPO_ROOT / "out" / "robustness_report.json"


def main() -> int:
    configure_repair_logger(LOG_PATH)
    cases = [json.loads(line) for line in INPUTS.read_text(encoding="utf-8").splitlines() if line]
    assert len(cases) == 10, f"expected 10 dirty cases, found {len(cases)}"

    failures: list[str] = []
    report_cases = []
    for case in cases:
        cid, kind, expect = case["id"], case["kind"], case["expect"]
        text = case["text"]
        summary = maybe_summarize(text if isinstance(text, str) else "", cid, mock=True)
        result = mock_extract(text if isinstance(text, str) else text, cid)
        row = to_output_row(cid, result)

        entry = {
            "id": cid,
            "kind": kind,
            "expect": expect,
            "resolved": result.ok,
            "source": row["source"],
            "summarized": summary.was_summarized,
        }
        if result.ok:
            entry.update(
                speaker_type=row["speaker_type"],
                stance=row["stance"],
                topic=row["topic"],
                confidence=row["confidence"],
            )
            # schema re-validation on the wire payload
            ExtractionRecord.model_validate(
                {k: row[k] for k in ("speaker_type", "topic", "stance", "confidence", "evidence")}
            )
        else:
            entry["error"] = row["error"]
        report_cases.append(entry)

        # --- contract checks -------------------------------------------------
        if expect == "unresolved":
            if result.ok or row["source"] != UNRESOLVED_SOURCE:
                failures.append(f"{cid}: expected unresolved, got {row['source']}")
        else:
            if not result.ok:
                failures.append(f"{cid}: expected schema-valid record, got unresolved ({row['error']})")

        if kind == "overlong_repetitive":
            if not summary.was_summarized:
                failures.append(f"{cid}: >{SUMMARY_THRESHOLD_CHARS} chars did not trigger summarizer")
            if len(summary.text) >= len(text):
                failures.append(f"{cid}: summary did not compress the input")

        if kind == "prompt_injection" and result.ok:
            if row["speaker_type"] != "citizen" or row["topic"] == "pwned" or row["evidence"] == "injected":
                failures.append(f"{cid}: injection hijacked the output: {row}")
        if kind == "embedded_json_impersonation" and result.ok:
            if row["speaker_type"] != "citizen" or row["stance"] != "support":
                failures.append(f"{cid}: embedded JSON changed labels: {row}")

    # repair log must document the unresolved cases
    log_text = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else ""
    n_unresolved = sum(1 for c in report_cases if not c["resolved"])
    log_hits = log_text.count("empty or non-alphabetic input")
    if log_hits < n_unresolved:
        failures.append(
            f"repair.log documents {log_hits} unresolved events but {n_unresolved} occurred"
        )

    report = {
        "n_cases": len(report_cases),
        "n_unresolved": n_unresolved,
        "n_schema_valid": sum(1 for c in report_cases if c["resolved"]),
        "failures": failures,
        "cases": report_cases,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"robustness: {len(report_cases)} cases | unresolved={n_unresolved} | "
          f"schema-valid={report['n_schema_valid']} | report -> {REPORT_PATH}")
    for c in report_cases:
        status = c["source"] if not c["resolved"] else f"{c['speaker_type']}/{c['stance']}"
        print(f"  {c['id']:<9} {c['kind']:<28} -> {status}" + (" [summarized]" if c["summarized"] else ""))
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(" -", failure)
        return 1
    print("\nAll robustness contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
