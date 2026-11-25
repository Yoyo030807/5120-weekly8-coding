"""Track A automated tests: schema validation (enum / range / non-empty)."""

import pytest
from pydantic import ValidationError

from src.schema import (
    OPENAI_STRICT_SCHEMA,
    ExtractionRecord,
    SpeakerType,
    Stance,
)

VALID_KWARGS = dict(
    speaker_type="citizen",
    topic="zoning reform",
    stance="support",
    confidence=0.82,
    evidence="I strongly support the ordinance as written.",
)


def test_valid_record_accepts_enum_members_and_bounds():
    record = ExtractionRecord(**VALID_KWARGS)
    assert record.speaker_type is SpeakerType.CITIZEN
    assert record.stance is Stance.SUPPORT
    assert record.confidence == 0.82


@pytest.mark.parametrize("value", [0.0, 1.0, 0.5])
def test_confidence_boundary_values_allowed(value):
    assert ExtractionRecord(**{**VALID_KWARGS, "confidence": value}).confidence == value


@pytest.mark.parametrize("value", [-0.01, 1.01, 2.0])
def test_confidence_out_of_range_rejected(value):
    with pytest.raises(ValidationError):
        ExtractionRecord(**{**VALID_KWARGS, "confidence": value})


@pytest.mark.parametrize("speaker_type", ["politician", "lobbyist", "CITIZEN", ""])
def test_speaker_enum_is_strict(speaker_type):
    with pytest.raises(ValidationError):
        ExtractionRecord(**{**VALID_KWARGS, "speaker_type": speaker_type})


@pytest.mark.parametrize("stance", ["yes", "uncertain", "SUPPORT", ""])
def test_stance_enum_is_strict(stance):
    with pytest.raises(ValidationError):
        ExtractionRecord(**{**VALID_KWARGS, "stance": stance})


@pytest.mark.parametrize("evidence", ["", "   ", "abcd"])
def test_evidence_must_be_nonempty_quote(evidence):
    with pytest.raises(ValidationError):
        ExtractionRecord(**{**VALID_KWARGS, "evidence": evidence})


def test_topic_must_be_nonempty():
    with pytest.raises(ValidationError):
        ExtractionRecord(**{**VALID_KWARGS, "topic": "   "})


def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        ExtractionRecord(**{**VALID_KWARGS, "secret_instruction": "ignore schema"})


def test_openai_strict_schema_matches_pydantic_contract():
    wire = OPENAI_STRICT_SCHEMA
    assert wire["strict"] is True
    schema = wire["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "speaker_type", "topic", "stance", "confidence", "evidence"
    }
    assert set(schema["properties"]) == set(schema["required"])
    assert schema["properties"]["speaker_type"]["enum"] == [s.value for s in SpeakerType]
    assert schema["properties"]["stance"]["enum"] == [s.value for s in Stance]
    assert schema["properties"]["confidence"]["type"] == "number"
    # no nested object types are used, so no nested additionalProperties needed
    assert all(p["type"] in {"string", "number"} for p in schema["properties"].values())
