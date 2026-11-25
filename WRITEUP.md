# WRITEUP — Council-Mining design doc

**Course:** CSS 5120 (Week 10, the coding agent harness)
**Student:** Yao YU (225030227)
**Status:** complete design doc with real-API evaluation results (`2026-11-25`,
endpoint `ep-20261026151823-95mxw` / `gpt-6-astra-2026-09-03` on the 30-item
held-out gold set; full tables in `eval/RESULTS.md`). Deterministic `--mock`
numbers remain clearly separated as offline plumbing/regression checks.

## 1. Problem

City councils publish meeting transcripts as free text. To answer questions
like "which stakeholder groups oppose the warehouse variance" or "how often
do officials take a neutral, briefing-only stance", someone has to convert
that text into queryable structure. The task is a per-segment extraction:
each transcript segment (80–200 words) becomes exactly one record with five
fields — speaker type, topic, stance, confidence, and a supporting quote.
The engineering problem is not the classification itself; it is building a
pipeline whose output is *guaranteed schema-valid*, whose failures are
*logged and recoverable*, and whose quality can be *measured honestly*
against a held-out gold set instead of judged by vibes.

## 2. Schema and why it looks like this

The codebook lives in one place, `src/schema.py`, as a Pydantic model; a
hand-written OpenAI strict JSON Schema is kept next to it and a test asserts
the two stay in sync.

| field | type | design reason |
|---|---|---|
| `speaker_type` | enum `citizen \| official \| uncertain` | Fixed categories remove the "is a pastor speaking at public comment a citizen?" drift between annotators and runs. `uncertain` is a first-class label, not an error bucket: anonymous letters and clerk-read cards are common in this domain, and forcing a guess would silently corrupt the data. |
| `topic` | non-empty string | Free text is deliberate: the 30-item gold spans 30 distinct policy issues, too many to enumerate up front. Normalized exact-match against gold keeps scoring strict. |
| `stance` | enum `support \| oppose \| neutral \| mixed` | Four values, not two. `neutral` captures factual staff briefings and question-only comments; `mixed` captures the common "I support the goal but not this version" pattern. Collapsing either into support/oppose would mislabel roughly half the corpus. |
| `confidence` | float in [0, 1] | A calibrated uncertainty signal lets a downstream consumer route low-confidence rows to human review. Bounds are validated at the schema level (`ge=0, le=1`), so an out-of-range number is a hard error, not a bad row. |
| `evidence` | non-empty verbatim quote, min 5 chars | The anti-hallucination anchor: every label must point at a sentence actually present in the source. The system prompt forbids paraphrase or invented quotes, and the mock backend only ever returns source substrings. |

`extra="forbid"` means an additional key (including an injected one) fails
validation rather than being silently ignored.

## 3. Architecture

```
 segments.jsonl (id, text only — no labels)
        │
        ▼
 ┌──────────────────────┐   gold/few-shot id-disjoint assertion runs first
 │  dataset loader      │──► assert_no_leakage()  (fails fast on any overlap)
 └──────────────────────┘
        │
        ▼
 ┌──────────────────────┐   output path validated BEFORE any write
 │  write guardrail     │──► safe_output_path(): only repo out/, .jsonl only
 └──────────────────────┘
        │  per segment
        ▼
 ┌──────────────────────┐
 │ len(text) > 3000 ?   │── yes ─► read-only summarizer subagent
 └──────────────────────┘            (isolated prompt; mock = extractive)
        │ no (or summarized text)
        ▼
 ┌──────────────────────┐
 │ structured API call  │   response_format = json_schema (strict), temp 0
 │  or --mock rules      │   mock: deterministic, id-seeded lexical scoring
 └──────────────────────┘
        │
        ▼
 ┌──────────────────────┐
 │ Pydantic validation  │── invalid / unparseable ─► one repair retry with
 └──────────────────────┘                              the exact error fed back
        │                          second failure ─► logs/repair.log
        ▼                                             + "unresolved" row
 rows.jsonl  (+ run_meta.json: model, temp, prompt version, shot, timestamp)
```

## 4. Key decisions and trade-offs

**Enforced structured output, not prompt-and-pray.** The API call carries a
strict `json_schema`, so the platform guarantees parseable JSON; Pydantic
then re-validates semantics (ranges, non-empty strings, forbidden extras).
The cost is schema rigidity — adding a field means changing model and wire
schema together — but that is exactly the property a codebook needs.

**One repair retry, then fail soft.** On the first off-schema response the
exact validation error is sent back for a corrected object. A second failure
is logged to `logs/repair.log` and emitted as an `unresolved` row; the batch
never crashes, and every dropped item is auditable. The trade-off is a
bounded latency cost (one extra call maximum) in exchange for no silent data
loss.

**Mock and real API share one schema but are separate code paths.**
`--mock` runs deterministic lexical rules with an RNG seeded per segment id,
so tests, the robustness harness and CI need no key or network, and runs are
bit-stable. The rule backend is deliberately simple and can score
artificially well on data written with recognizable cues — which is why
`eval/RESULTS.md` is hard-banned from containing mock numbers. Honesty about
what each number means is part of the design.

**Few-shot pool is physically isolated from gold.** 30 hand-labelled rows in
`eval/gold.csv` versus 5 exemplars in `data/fewshot_pool.jsonl`, with
disjoint ids asserted at startup, at eval time, and in the test suite
(including a deliberately poisoned negative test). The model-input file
contains no label fields at all.

**Subagent, not MCP.** The only extension is a read-only summarizer for
inputs over 3,000 characters. The sub-job is a text transformation over data
we already hold; a subagent gives context isolation with no new server, auth
or permission surface, whereas an MCP tool exists to reach external systems
(DB/Drive/API) that this pipeline does not have.

## 5. Honest limitations

1. **Small synthetic corpus.** 35 segments (30 gold + 5 few-shot), authored
   by me, de-identified and English-only. They exercise every label cell and
   six noise styles, but cannot estimate real-world accuracy.
2. **Enum ceiling vs. free-text granularity gap (real API finding).** On the
   real run (`gpt-6-astra-2026-09-03`), both enums reached `1.0000` macro-F1
   (30/30) and all 30 `evidence` quotes were exact verbatim substrings, but
   free-text `topic` normalized exact-match was `0.1667` (5/30) zero-shot and
   `0.2667` (8/30) 3-shot (`Δ = +0.1000`). All 25 zero-shot misses are
   semantically on-topic but differ in trailing procedural nouns, street/applicant
   proper nouns, or compound facets; additionally, the model assigns high
   meta-confidence (~0.97) to `uncertain` speakers rather than the `<=0.6`
   epistemic cap requested in the prompt.
3. **Temperature lock limitation on the target endpoint.** The internal Ark
   endpoint rejects `temperature=0` (only the server default `1` is allowed).
   We set `OPENAI_TEMPERATURE=omit` and log that omission honestly in
   `run_meta.json` and `eval/RESULTS.md` rather than pretending `0` was sent.
4. **Evidence provenance is verified post-hoc, not in the schema validator.**
   All 30 real API quotes were verified to be exact substrings during
   evaluation, but `ExtractionRecord` itself only checks non-empty length >= 5.
5. **No inter-rater κ or token-cost budget yet.** A single annotator (me)
   labelled the 30 gold rows, and per-item token counts are not yet logged.

## 6. What I would do with one more week

1. Tighten the `topic` codebook rule (*"2–3 words, drop generic suffixes like
   proposal/reform/program/funding and street proper nouns"*) and add a
   token-overlap / soft metric alongside strict exact-match.
2. Enforce the `speaker_type == "uncertain" => confidence <= 0.60` calibration
   rule directly in a Pydantic `@model_validator` so meta-confidence in
   anonymity cannot masquerade as high speaker certainty.
3. Pass `source_text` into validation context to assert `evidence in source_text`
   inside the retry/repair loop, turning quote provenance into a hard gate.
4. Expand gold to 40+ real (non-synthetic) segments with a second human coder
   to report Cohen's κ against human–model agreement.
5. Log `usage.prompt_tokens` / `completion_tokens` per item and benchmark a
   two-tier router (small model on high-cue segments, frontier model on the rest).
