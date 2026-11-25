# CLAUDE.md — project memory for Council-Mining

## What this repo is

A structured-extraction agent for synthetic, de-identified city-council
meeting segments. One segment in, one validated 5-field record out:

| field | type | rule |
|---|---|---|
| `speaker_type` | enum | `citizen` \| `official` \| `uncertain` |
| `topic` | string | non-empty after strip; short policy topic |
| `stance` | enum | `support` \| `oppose` \| `neutral` \| `mixed` |
| `confidence` | float | inclusive `[0.0, 1.0]` |
| `evidence` | string | non-empty verbatim quote, min 5 chars |

The schema is the codebook: change `src/schema.py` and its hand-written
`OPENAI_STRICT_SCHEMA` together — `tests/test_schema.py` enforces that they
stay in sync.

## Hard rules (do not violate)

1. **No secrets in the repo.** Credentials are read only from
   `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`. `.env` is
   git-ignored; `.env.example` has empty values. Never print a key to logs.
2. **Gold stays held out.** `eval/gold.csv` (30 rows) and
   `data/fewshot_pool.jsonl` (5 rows) must have disjoint ids; `data/segments.jsonl`
   carries `id`/`text` only, never labels. `assert_no_leakage()` runs at
   startup in `src/run.py`, `eval/run_eval.py` and the test suite.
3. **Writes stay inside `out/`.** `src/paths.py::safe_output_path` is the only
   allowed way to build an output path; `..` traversal, absolute paths
   elsewhere and non-`.jsonl` suffixes are refused.
4. **Never weaken a test to make it pass.** If a threshold fails, diagnose the
   rule or fix under-specified fixture data; do not edit assertions or gold
   labels to fit predictions.
5. **`eval/RESULTS.md` accepts real API numbers only.** Mock output is a
   plumbing/regression tool, not evidence of model quality.
6. **Fail soft.** Per-segment errors become `unresolved` rows + `logs/repair.log`
   entries; a batch must never crash because one segment is malformed.

## Data dictionary & layout

* `data/segments.jsonl` — 35 inputs, 80–200 English words each, covering all
  12 speaker_type × stance cells (each ≥2 in gold), including 6 deliberately
  noisy transcripts (typos, all-caps, filler, bilingual, truncated, run-on).
* `data/fewshot_pool.jsonl` — 5 fully labelled exemplars used only with
  `--shot 3`; includes an `evidence` quote for the assistant turn.
* `eval/gold.csv` — columns `id,speaker_type,topic,stance`; confidence and
  evidence are model-output fields and are intentionally not gold-labelled.
* `robustness/inputs/dirty_segments.jsonl` — 10 adversarial/messy cases
  (empty, whitespace, null, truncated, wrong language, prompt injection,
  embedded JSON, >3000-char repetitive, all-caps, OCR garble + control chars).

## Coding scheme (annotation conventions)

* `uncertain` = anonymous/unnamed speaker, clerk-read letters, unverified
  comment cards, or no role cues at all. When in doubt, `uncertain`.
* `neutral` = explicitly no position, factual staff briefings, questions only.
* `mixed` = substantive positions on both sides, or conditional support
  ("support X, but cannot support this version without changes").
* `evidence` must be copied verbatim from the source text; never paraphrase.
* Confidence ≤ 0.6 when cues are weak; the mock backend follows the same rule.

## Commands

```bash
python src/run.py data/ -o out/rows.jsonl --mock      # offline pipeline
python -m pytest tests/ -v                            # full test suite
python robustness/run_robustness.py                   # dirty-input harness
python eval/run_eval.py --pred-zero out/rows_zero.jsonl
```

## Conventions

* Standard library only for eval and tests; Pydantic for validation; `openai`
  is imported lazily so mock mode works without the package or network.
* Determinism: mock RNG is seeded per segment id; temperature defaults to 0
  for API runs, or is omitted via `OPENAI_TEMPERATURE=omit` when a provider
  only allows its server default (logged verbatim in `run_meta.json`).
* Deliverables (`WRITEUP.md`, `INTERVIEW.md`, `demo/`, `AI_USE_NOTE.md`,
  `eval/RESULTS.md`) live alongside the code; they must stay factually
  consistent with the modules above and record only real-API evaluation
  numbers (executed on `2026-11-25` with `ep-20261026151823-95mxw` /
  `gpt-6-astra-2026-09-03`), never mock scores.
* The deck PDF is built from `demo/slides.md` via pandoc + WeasyPrint
  (see the build command in `README.md`); soffice is unusable in this
  environment. Regenerate the PDF and re-verify it is 5 pages after edits.
