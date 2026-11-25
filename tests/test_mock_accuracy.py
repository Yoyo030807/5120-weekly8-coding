"""Track A regression gate: mock extractor on a tiny hand-checked fixture.

Thresholds are intentionally modest (0.8) and run on an independent fixture,
not on eval/gold.csv, so the gate measures rule health without overfitting.
"""

import json
from pathlib import Path

import pytest

from src.extract import MOCK_SOURCE, mock_extract, to_output_row
from src.schema import ExtractionRecord

FIXTURE = Path(__file__).parent / "fixtures" / "mock_fixture.jsonl"
ACCURACY_THRESHOLD = 0.8


@pytest.fixture(scope="module")
def fixture_rows():
    with FIXTURE.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_mock_meets_speaker_and_stance_accuracy_threshold(fixture_rows):
    speaker_ok = stance_ok = 0
    for row in fixture_rows:
        result = mock_extract(row["text"], row["id"])
        assert result.ok, f"mock should resolve clean inputs: {row['id']}"
        assert result.source == MOCK_SOURCE
        if result.record.speaker_type.value == row["exp_speaker_type"]:
            speaker_ok += 1
        if result.record.stance.value == row["exp_stance"]:
            stance_ok += 1
    speaker_acc = speaker_ok / len(fixture_rows)
    stance_acc = stance_ok / len(fixture_rows)
    assert speaker_acc >= ACCURACY_THRESHOLD, f"speaker accuracy {speaker_acc}"
    assert stance_acc >= ACCURACY_THRESHOLD, f"stance accuracy {stance_acc}"


def test_mock_output_validates_against_schema(fixture_rows):
    for row in fixture_rows:
        result = mock_extract(row["text"], row["id"])
        # re-validating the dumped payload proves wire-level schema compliance
        ExtractionRecord.model_validate(result.record.model_dump())
        envelope = to_output_row(row["id"], result)
        assert envelope["source"] == MOCK_SOURCE
        assert set(envelope) >= {
            "id", "source", "speaker_type", "topic", "stance", "confidence", "evidence"
        }
        assert 0.0 <= envelope["confidence"] <= 1.0
        assert envelope["evidence"] and envelope["evidence"] in row["text"]


def test_mock_is_deterministic_across_runs(fixture_rows):
    first = mock_extract(fixture_rows[0]["text"], fixture_rows[0]["id"])
    second = mock_extract(fixture_rows[0]["text"], fixture_rows[0]["id"])
    assert first.record.model_dump() == second.record.model_dump()


@pytest.mark.parametrize("bad_text", ["", "   \n\t  ", "12345 !!! ???", None])
def test_mock_degrades_to_unresolved_on_unusable_input(bad_text):
    result = mock_extract(bad_text, "dirty-id")
    assert not result.ok
    assert result.source == "unresolved"
    assert result.error
    envelope = to_output_row("dirty-id", result)
    assert envelope["speaker_type"] is None and envelope["error"]
