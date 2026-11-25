#!/usr/bin/env python3
"""Batch runner: a folder of meeting segments -> one validated JSONL file.

Usage
-----
    python src/run.py data/ -o out/rows.jsonl --mock
    python src/run.py data/ -o out/rows_3shot.jsonl --shot 3

Safety
------
* output paths are validated by src.paths.safe_output_path (out/ only);
* gold/few-shot leakage is asserted before any extraction runs;
* per-segment failures become ``unresolved`` rows, never hard crashes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python src/run.py ...` from the repo root as well as -m invocation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.dataset import (  # noqa: E402
    assert_no_leakage,
    load_fewshot_pool,
    load_gold,
    load_segments,
    resolve_segments_file,
)
from src.extract import (  # noqa: E402
    ApiConfig,
    MOCK_SOURCE,
    PROMPT_VERSION,
    configure_repair_logger,
    extract,
    resolve_temperature,
    to_output_row,
)
from src.paths import REPO_ROOT as ROOT  # noqa: E402
from src.paths import UnsafeOutputPathError, safe_output_path  # noqa: E402
from src.schema import SCHEMA_VERSION  # noqa: E402
from src.summarizer import maybe_summarize  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured 5-field records from council-meeting segments."
    )
    parser.add_argument("input", help="folder containing segments.jsonl (or a .jsonl file)")
    parser.add_argument("-o", "--output", default="out/rows.jsonl", help="output .jsonl path (must be inside out/)")
    parser.add_argument("--mock", action="store_true", help="use deterministic offline rules instead of the API")
    parser.add_argument("--shot", type=int, choices=(0, 3), default=0, help="few-shot exemplars (0 or 3); mock mode ignores exemplars")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # --- logging (repair trail) -------------------------------------------
    configure_repair_logger(ROOT / "logs" / "repair.log")

    # --- load data and enforce held-out discipline ------------------------
    segments = load_segments(args.input)
    seg_file = resolve_segments_file(args.input)
    data_dir = seg_file.parent
    fewshot = load_fewshot_pool(data_dir)
    gold = load_gold()
    assert_no_leakage(segments, gold, fewshot)
    print(
        f"[init] leakage check OK: {len(gold)} gold / {len(fewshot)} few-shot / "
        f"{len(segments)} segments, disjoint ids"
    )

    # --- write-path guardrail ---------------------------------------------
    try:
        out_path = safe_output_path(args.output)
    except UnsafeOutputPathError as exc:
        print(f"[guardrail] {exc}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- fail fast on missing API configuration ---------------------------
    config = None
    model_label = MOCK_SOURCE
    if not args.mock:
        try:
            config = ApiConfig.from_env()
        except RuntimeError as exc:
            print(f"[config] {exc}", file=sys.stderr)
            return 2
        model_label = config.model
    elif args.shot == 3:
        print("[init] --mock --shot 3: mock rules are exemplar-independent; exemplars loaded only for the leakage check")

    # --- batch extraction --------------------------------------------------
    rows = []
    n_unresolved = 0
    n_summarized = 0
    for segment in segments:
        seg_id, text = segment["id"], segment["text"]
        summary = maybe_summarize(text, seg_id, mock=args.mock, config=config)
        if summary.was_summarized:
            n_summarized += 1
        result = extract(
            summary.text,
            seg_id,
            mock=args.mock,
            config=config,
            fewshot=fewshot,
            shot=args.shot,
        )
        if not result.ok:
            n_unresolved += 1
        rows.append(to_output_row(seg_id, result))

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # --- reproducibility metadata (lives next to the rows, inside out/) ---
    effective_temperature = resolve_temperature()
    meta = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mock": args.mock,
        "model": model_label,
        # None means the parameter was deliberately omitted (provider server
        # default); never pretend a 0.0 was sent when it was not.
        "temperature": (
            effective_temperature
            if effective_temperature is not None
            else "omitted (provider server default; OPENAI_TEMPERATURE=omit)"
        ),
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "shot": args.shot,
        "input_file": str(seg_file),
        "output_file": str(out_path),
        "segments_processed": len(rows),
        "segments_summarized": n_summarized,
        "unresolved": n_unresolved,
    }
    meta_path = out_path.parent / "run_meta.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(
        f"[done] wrote {len(rows)} rows -> {out_path} "
        f"(unresolved={n_unresolved}, summarized={n_summarized}, meta={meta_path})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
