"""Dataset loading and held-out leakage guards.

Layout convention
-----------------
* ``data/segments.jsonl``     - all 35 model inputs, text only, NO labels
* ``data/fewshot_pool.jsonl`` - 5 labelled exemplars (3-shot prompting only)
* ``eval/gold.csv``           - 30 hand-labelled held-out rows

The gold ids and few-shot ids must never overlap, otherwise the model would
effectively see gold answers during few-shot evaluation. Every entrypoint
(``run.py``, ``eval/run_eval.py`` and the test suite) calls
:func:`assert_no_leakage` before doing any work.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SEGMENTS_FILE = "segments.jsonl"
FEWSHOT_FILE = "fewshot_pool.jsonl"
GOLD_FILE = Path("eval") / "gold.csv"


class LeakageError(AssertionError):
    """Raised when held-out gold data leaks into few-shot exemplars."""


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def resolve_segments_file(input_path: str | Path) -> Path:
    """A folder input means the canonical segments.jsonl inside it."""
    p = Path(input_path)
    if p.is_dir():
        return p / SEGMENTS_FILE
    return p


def load_segments(input_path: str | Path) -> list[dict[str, str]]:
    path = resolve_segments_file(input_path)
    rows = load_jsonl(path)
    if not rows:
        raise ValueError(f"no segments found in {path}")
    for row in rows:
        if "id" not in row or "text" not in row:
            raise ValueError(f"segment missing required id/text fields: {row}")
    return rows


def load_fewshot_pool(data_dir: str | Path) -> list[dict[str, Any]]:
    return load_jsonl(Path(data_dir) / FEWSHOT_FILE)


def load_gold(gold_path: str | Path | None = None) -> list[dict[str, str]]:
    path = Path(gold_path) if gold_path else REPO_ROOT / GOLD_FILE
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def assert_no_leakage(
    segments: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    fewshot: list[dict[str, Any]],
) -> None:
    """Fail fast on any overlap between gold labels and few-shot exemplars."""
    segment_ids = {r["id"] for r in segments}
    gold_ids = {r["id"] for r in gold}
    fewshot_ids = {r["id"] for r in fewshot}

    overlap = gold_ids & fewshot_ids
    if overlap:
        raise LeakageError(f"gold ids overlap few-shot pool: {sorted(overlap)}")
    missing_gold = gold_ids - segment_ids
    if missing_gold:
        raise LeakageError(f"gold ids absent from segments.jsonl: {sorted(missing_gold)}")
    missing_fs = fewshot_ids - segment_ids
    if missing_fs:
        raise LeakageError(f"few-shot ids absent from segments.jsonl: {sorted(missing_fs)}")
    if len(gold_ids) != len(gold):
        raise LeakageError("duplicate ids in gold.csv")
    if len(fewshot_ids) != len(fewshot):
        raise LeakageError("duplicate ids in fewshot_pool.jsonl")
    # Labels must never ride along in the model-input file.
    for row in segments:
        labelled = set(row) - {"id", "text"}
        if labelled:
            raise LeakageError(
                f"segment {row.get('id')} carries label-like fields: {sorted(labelled)}"
            )
