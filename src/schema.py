"""Structured-output schema for council-meeting segment extraction.

This module is the *codebook in code* for the project: every record produced by
the extractor (real API or deterministic mock) must validate against
``ExtractionRecord``.

Fields
------
speaker_type : enum  citizen | official | uncertain
topic        : str   short policy topic, non-empty
stance       : enum  support | oppose | neutral | mixed
confidence   : float in [0.0, 1.0]
evidence     : str   verbatim supporting quote from the source text, non-empty
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"


class SpeakerType(str, Enum):
    """Role of the person speaking in the meeting segment."""

    CITIZEN = "citizen"
    OFFICIAL = "official"
    UNCERTAIN = "uncertain"


class Stance(str, Enum):
    """Policy stance expressed towards the proposal under discussion."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class ExtractionRecord(BaseModel):
    """Validated 5-field extraction record.

    ``extra="forbid"`` makes any surprise field a hard validation error so the
    retry/repair path (see ``src/extract.py``) can catch it.
    """

    model_config = ConfigDict(extra="forbid")

    speaker_type: SpeakerType = Field(
        description="Role of the speaker: citizen, official, or uncertain."
    )
    topic: str = Field(
        min_length=1, description="Short policy topic, e.g. 'protected bike lane'."
    )
    stance: Stance = Field(
        description="Speaker stance: support, oppose, neutral, or mixed."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Extractor confidence between 0.0 and 1.0 inclusive.",
    )
    evidence: str = Field(
        min_length=1,
        description="Verbatim quote from the input text supporting the labels.",
    )

    @field_validator("topic", "evidence")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty or whitespace-only")
        return value

    @field_validator("evidence")
    @classmethod
    def _evidence_reasonable_length(cls, value: str) -> str:
        if len(value.strip()) < 5:
            raise ValueError("evidence quote is implausibly short")
        return value


# Hand-written OpenAI Structured Outputs schema (strict mode).
# We do NOT feed Pydantic's model_json_schema() directly: OpenAI strict mode has
# its own subset rules (all keys required, additionalProperties:false, no
# unsupported formats). Keeping this explicit also documents the wire contract.
# tests/test_schema.py asserts it stays in sync with ExtractionRecord.
OPENAI_STRICT_SCHEMA: dict = {
    "name": "extraction_record",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "speaker_type": {
                "type": "string",
                "enum": [s.value for s in SpeakerType],
                "description": "Role of the speaker: citizen, official, or uncertain.",
            },
            "topic": {
                "type": "string",
                "description": "Short policy topic, e.g. 'protected bike lane'.",
            },
            "stance": {
                "type": "string",
                "enum": [s.value for s in Stance],
                "description": "Speaker stance: support, oppose, neutral, or mixed.",
            },
            "confidence": {
                "type": "number",
                "description": "Extractor confidence between 0.0 and 1.0 inclusive.",
            },
            "evidence": {
                "type": "string",
                "description": "Verbatim quote from the input text supporting the labels.",
            },
        },
        "required": ["speaker_type", "topic", "stance", "confidence", "evidence"],
    },
}
