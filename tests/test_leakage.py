"""Held-out discipline: gold/few-shot leakage, counts, word lengths, coverage."""

import csv
import json
from pathlib import Path

import pytest

from src.dataset import LeakageError, assert_no_leakage, load_fewshot_pool, load_segments, load_gold

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bundle():
    segments = load_segments(REPO / "data")
    fewshot = load_fewshot_pool(REPO / "data")
    gold = load_gold(REPO / "eval" / "gold.csv")
    return segments, fewshot, gold


def test_expected_counts(bundle):
    segments, fewshot, gold = bundle
    assert len(segments) == 35
    assert len(fewshot) == 5
    assert len(gold) == 30


def test_gold_and_fewshot_ids_are_disjoint(bundle):
    segments, fewshot, gold = bundle
    gold_ids = {r["id"] for r in gold}
    fewshot_ids = {r["id"] for r in fewshot}
    assert gold_ids.isdisjoint(fewshot_ids)
    # the shared runtime assertion must accept the real data
    assert_no_leakage(segments, gold, fewshot)


def test_leakage_assertion_detects_injected_overlap(bundle):
    segments, fewshot, gold = bundle
    poisoned_gold = gold + [dict(gold[0])]
    poisoned_gold[-1]["id"] = fewshot[0]["id"]
    with pytest.raises(LeakageError):
        assert_no_leakage(segments, poisoned_gold, fewshot)


def test_segments_file_carries_no_labels(bundle):
    segments, _, _ = bundle
    for row in segments:
        assert set(row) == {"id", "text"}


def test_segment_word_counts_within_brief(bundle):
    segments, _, _ = bundle
    for row in segments:
        n_words = len(row["text"].split())
        assert 80 <= n_words <= 200, f"{row['id']} has {n_words} words"


def test_gold_covers_all_twelve_speaker_stance_cells_twice(bundle):
    _, _, gold = bundle
    cells = {(r["speaker_type"], r["stance"]) for r in gold}
    expected = {
        (sp, st)
        for sp in ("citizen", "official", "uncertain")
        for st in ("support", "oppose", "neutral", "mixed")
    }
    assert cells == expected
    for cell in expected:
        assert sum(1 for r in gold if (r["speaker_type"], r["stance"]) == cell) >= 2


def test_gold_csv_header_and_enum_values(bundle):
    _, _, gold = bundle
    assert set(gold[0]) == {"id", "speaker_type", "topic", "stance"}
    for row in gold:
        assert row["speaker_type"] in {"citizen", "official", "uncertain"}
        assert row["stance"] in {"support", "oppose", "neutral", "mixed"}
        assert row["topic"].strip()
