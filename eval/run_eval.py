#!/usr/bin/env python3
"""Score predictions against the held-out gold set.

Metrics (classification fields speaker_type and stance):
  * accuracy
  * per-class precision / recall / F1 (unresolved predictions count as errors)
  * macro-F1
  * confusion matrix (true rows x predicted columns)
Topic is scored as normalized exact-match agreement (extraction-style metric).

Ablation: pass both --pred-zero and --pred-three to get the 3-shot delta
automatically. All numbers are printed and dumped as JSON under out/;
eval/RESULTS.md stays a hand-filled skeleton and must never be auto-written.

Usage:
  python eval/run_eval.py --pred-zero out/rows_zero.jsonl
  python eval/run_eval.py --pred-zero out/rows_zero.jsonl \\
                          --pred-three out/rows_3shot.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.dataset import assert_no_leakage, load_fewshot_pool, load_segments  # noqa: E402

UNRESOLVED = "unresolved"
LABEL_FIELDS = ("speaker_type", "stance")


def load_gold(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def load_predictions(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[row["id"]] = row
    return rows


def _normalize(value: str | None) -> str:
    if value is None:
        return UNRESOLVED
    return " ".join(str(value).lower().split())


def prf_counts(gold_labels: list[str], pred_labels: list[str], classes: list[str]) -> dict:
    metrics = {}
    for cls in classes:
        tp = sum(g == cls and p == cls for g, p in zip(gold_labels, pred_labels))
        fp = sum(g != cls and p == cls for g, p in zip(gold_labels, pred_labels))
        fn = sum(g == cls and p != cls for g, p in zip(gold_labels, pred_labels))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        support = sum(g == cls for g in gold_labels)
        metrics[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
    return metrics


def confusion(gold_labels: list[str], pred_labels: list[str], classes: list[str]) -> "OrderedDict[str, dict[str, int]]":
    pred_classes = classes + ([UNRESOLVED] if UNRESOLVED in pred_labels else [])
    matrix: OrderedDict[str, dict[str, int]] = OrderedDict()
    for cls in classes:
        matrix[cls] = OrderedDict((pc, 0) for pc in pred_classes)
    for g, p in zip(gold_labels, pred_labels):
        matrix[g][p] += 1
    return matrix


def evaluate(gold: dict[str, dict[str, str]], preds: dict[str, dict], name: str) -> dict:
    ids = sorted(gold)
    missing = [i for i in ids if i not in preds]
    if missing:
        raise SystemExit(f"predictions missing gold ids: {missing}")

    result: dict = {"name": name, "n_gold": len(ids), "missing_predictions": 0}
    for field in LABEL_FIELDS:
        gold_labels = [gold[i][field] for i in ids]
        pred_labels = [_normalize(preds[i].get(field)) for i in ids]
        classes = sorted(set(gold_labels))
        correct = sum(g == p for g, p in zip(gold_labels, pred_labels))
        per_class = prf_counts(gold_labels, pred_labels, classes)
        macro_f1 = sum(m["f1"] for m in per_class.values()) / len(classes)
        result[field] = {
            "accuracy": round(correct / len(ids), 4),
            "macro_f1": round(macro_f1, 4),
            "per_class": per_class,
            "confusion_matrix": confusion(gold_labels, pred_labels, classes),
            "errors": [
                {"id": i, "gold": gold[i][field], "pred": preds[i].get(field) or UNRESOLVED}
                for i in ids
                if gold[i][field] != _normalize(preds[i].get(field))
            ],
        }

    # extraction-style topic metric: normalized exact match
    topic_gold = [_normalize(gold[i]["topic"]) for i in ids]
    topic_pred = [_normalize(preds[i].get("topic")) for i in ids]
    result["topic"] = {
        "normalized_exact_match": round(
            sum(g == p for g, p in zip(topic_gold, topic_pred)) / len(ids), 4
        ),
        "errors": [
            {"id": i, "gold": gold[i]["topic"], "pred": preds[i].get("topic") or UNRESOLVED}
            for i in ids
            if _normalize(gold[i]["topic"]) != _normalize(preds[i].get("topic"))
        ],
    }
    result["unresolved_rows"] = sum(
        1 for i in ids if preds[i].get("source") == UNRESOLVED
    )
    return result


def print_result(result: dict) -> None:
    print(f"\n=== {result['name']} (n={result['n_gold']}, unresolved={result['unresolved_rows']}) ===")
    for field in LABEL_FIELDS:
        r = result[field]
        print(f"\n[{field}] accuracy={r['accuracy']:.4f}  macro-F1={r['macro_f1']:.4f}")
        print(f"  {'class':<10} {'P':>7} {'R':>7} {'F1':>7} {'support':>8}")
        for cls, m in r["per_class"].items():
            print(f"  {cls:<10} {m['precision']:>7.4f} {m['recall']:>7.4f} {m['f1']:>7.4f} {m['support']:>8}")
        cols = list(next(iter(r["confusion_matrix"].values())).keys())
        print("  confusion matrix (rows=true, cols=pred):")
        print("    true\\pred " + " ".join(f"{c[:9]:>10}" for c in cols))
        for true_cls, row in r["confusion_matrix"].items():
            print(f"    {true_cls:<10} " + " ".join(f"{row[c]:>10}" for c in cols))
        if r["errors"]:
            print(f"  errors ({len(r['errors'])}): " + ", ".join(f"{e['id']}({e['gold']}->{e['pred']})" for e in r["errors"]))
    t = result["topic"]
    print(f"\n[topic] normalized exact-match={t['normalized_exact_match']:.4f}")
    if t["errors"]:
        print("  errors: " + ", ".join(f"{e['id']}({e['gold']}->{e['pred']})" for e in t["errors"]))


def ablation_delta(zero: dict, three: dict) -> dict:
    delta = {}
    for field in LABEL_FIELDS:
        delta[field] = {
            "accuracy_delta_3shot_minus_zero": round(
                three[field]["accuracy"] - zero[field]["accuracy"], 4
            ),
            "macro_f1_delta_3shot_minus_zero": round(
                three[field]["macro_f1"] - zero[field]["macro_f1"], 4
            ),
        }
    delta["topic"] = {
        "exact_match_delta_3shot_minus_zero": round(
            three["topic"]["normalized_exact_match"] - zero["topic"]["normalized_exact_match"], 4
        )
    }
    return delta


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Score extraction predictions vs gold.")
    p.add_argument("--gold", default=str(REPO_ROOT / "eval" / "gold.csv"))
    p.add_argument("--pred-zero", help="zero-shot prediction JSONL")
    p.add_argument("--pred-three", help="3-shot prediction JSONL")
    p.add_argument("--out-dir", default=str(REPO_ROOT / "out"), help="where metrics JSON is written")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.pred_zero and not args.pred_three:
        raise SystemExit("provide at least one of --pred-zero / --pred-three")

    # Held-out discipline is re-asserted at eval time too.
    segments = load_segments(REPO_ROOT / "data")
    fewshot = load_fewshot_pool(REPO_ROOT / "data")
    gold_rows = list(load_gold(Path(args.gold)).values())
    assert_no_leakage(segments, gold_rows, fewshot)

    gold = load_gold(Path(args.gold))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = {}

    if args.pred_zero:
        zero = evaluate(gold, load_predictions(Path(args.pred_zero)), "zero-shot")
        print_result(zero)
        bundle["zero_shot"] = zero
        with (out_dir / "metrics_zero_shot.json").open("w", encoding="utf-8") as f:
            json.dump(zero, f, indent=2, ensure_ascii=False)

    if args.pred_three:
        three = evaluate(gold, load_predictions(Path(args.pred_three)), "3-shot")
        print_result(three)
        bundle["three_shot"] = three
        with (out_dir / "metrics_3_shot.json").open("w", encoding="utf-8") as f:
            json.dump(three, f, indent=2, ensure_ascii=False)

    if args.pred_zero and args.pred_three:
        delta = ablation_delta(bundle["zero_shot"], bundle["three_shot"])
        bundle["ablation_delta_3shot_minus_zero"] = delta
        print("\n=== ablation delta (3-shot minus zero-shot) ===")
        print(json.dumps(delta, indent=2))

    if args.pred_zero and args.pred_three:
        with (out_dir / "metrics_ablation.json").open("w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)
    print(f"\nmetrics JSON written under {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
