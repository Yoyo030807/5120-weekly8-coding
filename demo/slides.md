# Council-Mining
### Structured extraction for city-council meeting segments
CSS 5120 · Week 10 portfolio · Yao YU (225030227)

## 1 · Problem

- City councils publish meetings as **free-text transcripts** — impossible to query systematically.
- Goal: one transcript segment (80–200 words) → one validated **5-field record**:

| field | type |
|---|---|
| `speaker_type` | enum: citizen / official / uncertain |
| `topic` | non-empty string |
| `stance` | enum: support / oppose / neutral / mixed |
| `confidence` | float in [0, 1] |
| `evidence` | verbatim supporting quote |

- Engineering bar: **guaranteed schema-valid output, logged failures, measured accuracy** — not a prompt-and-pray demo.
- 35 synthetic, de-identified segments; 30 hand-labelled gold rows held out; 5 disjoint few-shot exemplars.

## 2 · Architecture and live run

```
segments.jsonl → leakage assertion → write guardrail (out/ only)
   → [if >3000 chars] read-only summarizer subagent
   → strict json_schema API call (or deterministic --mock rules)
   → Pydantic validation → one repair retry on failure
   → rows.jsonl + run_meta.json ; second failure → repair.log + unresolved row
```

Live commands (real Ark `gpt-6-astra-2026-09-03` run + offline `--mock` regression gate):

```bash
$ OPENAI_TEMPERATURE=omit python src/run.py data/ -o out/rows_three.jsonl --shots 3
[init] leakage check OK: 30 gold / 5 few-shot / 35 segments, disjoint ids
[done] wrote 35 rows -> out/rows_three.jsonl (source=openai-compatible, unresolved=0, attempts=1)
$ python eval/run_eval.py --pred out/rows_three.jsonl --baseline out/rows_zero.jsonl
speaker_type acc=1.0000 macro_F1=1.0000 | stance acc=1.0000 macro_F1=1.0000 | topic_EM=0.2667 (Δ=+0.1000)
```

## 3 · Real-API evaluation (`gpt-6-astra-2026-09-03`, n = 30 gold)

- Held-out **30-item gold set** (`eval/gold.csv`), disjoint from the 5-item few-shot pool; leakage asserted before every run.
- Endpoint `ep-20261026151823-95mxw` (`gpt-6-astra-2026-09-03`), strict `json_schema` mode, run on `2026-11-25`.

| metric | zero-shot | 3-shot | Δ (3-shot − 0-shot) |
|---|---:|---:|---:|
| `speaker_type` acc / macro-F1 | **1.0000 / 1.0000** | **1.0000 / 1.0000** | +0.0000 |
| `stance` acc / macro-F1 | **1.0000 / 1.0000** | **1.0000 / 1.0000** | +0.0000 |
| `topic` normalized exact-match | 0.1667 (5/30) | **0.2667 (8/30)** | **+0.1000 (+3 items, 0 lost)** |
| `evidence` verbatim substring | **1.0000 (30/30)** | **1.0000 (30/30)** | +0.0000 |
| unresolved rows / repair retries | **0 / 0** | **0 / 0** | 0 |

- **Why 3-shot helped `topic` (+10 pp):** concise 2–3 word exemplars taught the model to drop trailing procedural nouns (`"funding"`, `"equity"`, `"award"` on `seg-018/024/026`).
- **Honest temperature note:** endpoint rejects `temperature=0` (only server default `1` allowed); run used `OPENAI_TEMPERATURE=omit` and logged that omission verbatim in `run_meta.json`.

## 4 · A real robustness failure (handled, not hidden)

Dirty input `dirty-01` = empty string. The extractor refuses to invent a record:

```text
robustness harness, 10 messy inputs:
  dirty-01  empty               -> unresolved
  dirty-02  whitespace_only     -> unresolved
  dirty-03  null_text           -> unresolved
  ... 7 further cases return schema-valid records (injection not hijacked)
```

Actual `logs/repair.log` line:

```text
2026-11-18 04:42:32 | ERROR | segment=dirty-01 UNRESOLVED in mock mode:
empty or non-alphabetic input: nothing to extract
```

- Contract: **no input crashes the batch**; every input yields exactly one row; failures are auditable in the log.
- Prompt-injection case verified: embedded "ignore previous instructions" JSON does **not** override the labels.

## 5 · Limitations and next steps

- **35 synthetic English segments** — exercises every label cell and 6 noise styles, but real-world precision needs a larger organic transcript sample.
- **Topic granularity & confidence calibration findings:** all 22 remaining 3-shot `topic` misses are modifier/proper-noun granularity differences on semantically correct topics; `uncertain` speakers get ~0.97 meta-confidence in anonymity rather than the `<=0.6` epistemic cap.
- **Temperature constraint:** internal Ark endpoint only accepts server default `1` (`OPENAI_TEMPERATURE=omit` logged honestly).
- **Next steps:** tighten the 2–3 word `topic` rule + add token-overlap F1; enforce `uncertain => confidence <= 0.6` in Pydantic; assert `evidence in source_text` inside the repair loop; 2nd annotator + Cohen's κ; token/latency budget.
- Repo ships with 44 pytest cases, an `out/`-only write guardrail, and gold/few-shot leakage assertions.
