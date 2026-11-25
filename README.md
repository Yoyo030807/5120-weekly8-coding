# Council-Mining — structured extraction for city-council meeting segments

**What:** one-command tool that turns de-identified council-meeting transcript
segments into validated 5-field records
(`speaker_type`, `topic`, `stance`, `confidence`, `evidence`).
**Why:** civic-comment analysis needs queryable structure instead of free-text
transcripts, and an extractor is only trustworthy if its schema is enforced,
its failures are logged, and its accuracy is measured against a held-out gold
set — not eyeballed.

## Run

```bash
pip install -r requirements.txt

# Offline end-to-end with deterministic rules (no API key, no network):
python src/run.py data/ -o out/rows.jsonl --mock

# Real OpenAI-compatible API (credentials come ONLY from environment variables):
cp .env.example .env        # fill in the three values
set -a; source .env; set +a
python src/run.py data/ -o out/rows_zero.jsonl  --shot 0
python src/run.py data/ -o out/rows_three.jsonl --shot 3

# Evaluation against the 30-item held-out gold set (+ automatic ablation):
python eval/run_eval.py --pred-zero out/rows_zero.jsonl \
                        --pred-three out/rows_three.jsonl

# Track A: tests and the 10-input robustness harness
python -m pytest tests/ -v
python robustness/run_robustness.py
```

### What `--mock` is (and is not)

`--mock` replaces the LLM with deterministic, id-seeded lexical rules
(`src/extract.py::mock_extract`) that emit the **same Pydantic schema**, tagged
`source="mock-rules"`. It exists so the pipeline, tests and robustness harness
run anywhere with no key. **Mock numbers are not model results and must never
be copied into `eval/RESULTS.md`** — that file accepts real API runs only.

## Design (one paragraph)

The codebook is a Pydantic model (`src/schema.py`) with two enums
(`citizen|official|uncertain`, `support|oppose|neutral|mixed`), a bounded
confidence and a non-empty verbatim evidence quote; a hand-written strict
JSON Schema is sent through `response_format={"type": "json_schema", ...}` so
the API response is guaranteed parseable, and Pydantic re-validates the wire
payload with `extra="forbid"`. Off-schema or failed parses trigger exactly one
repair retry that feeds the validation error back to the model; a second
failure is logged to `logs/repair.log` and becomes an `unresolved` row instead
of crashing the batch. The one extension is a **subagent**, not an MCP tool:
inputs over 3,000 characters first pass through a read-only summarizer
(`src/summarizer.py`) with its own isolated prompt, because the sub-job is a
text transformation over data we already hold — no external DB/drive/API
surface would justify standing up an MCP server (full trade-off in
`WRITEUP.md` §4). A write-path guardrail (`src/paths.py`) refuses any
output outside `out/`, and every entrypoint asserts that gold and few-shot ids
never overlap.

## Repository map

```
Yao-YU-225030227/
├── src/
│   ├── schema.py        # Pydantic codebook + OpenAI strict JSON Schema
│   ├── extract.py       # API client, retry/repair, deterministic mock backend
│   ├── summarizer.py    # subagent-style read-only summarization (>3000 chars)
│   ├── dataset.py       # JSONL/CSV loading + gold leakage assertions
│   ├── paths.py         # out/-only write guardrail
│   └── run.py           # one-command batch runner
├── data/
│   ├── segments.jsonl       # 35 synthetic de-identified inputs (text only)
│   └── fewshot_pool.jsonl   # 5 labelled exemplars (disjoint from gold)
├── eval/
│   ├── gold.csv         # 30 hand-labelled held-out rows
│   ├── run_eval.py      # accuracy, per-class P/R/F1, confusion matrix, ablation
│   └── RESULTS.md       # skeleton; real-API numbers only (mock banned)
├── tests/               # pytest: schema, guardrail, mock regression, leakage
├── robustness/          # 10 dirty inputs + graceful-degradation harness
├── demo/                # 5-slide deck: slides.md, slides.css, slides.pdf
├── WRITEUP.md           # ~2-page design doc (Part 3)
├── INTERVIEW.md         # first-person answers to the 15 agent questions
├── AI_USE_NOTE.md       # how AI assistance was used, with signature line
├── SHA256SUMS           # checksums for every delivered file
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

## Docs and demo build

The design doc (`WRITEUP.md`), interview answers (`INTERVIEW.md`) and AI-use
note are plain Markdown. The 5-slide deck is Markdown-first and rendered to
PDF with pandoc + WeasyPrint (LibreOffice/soffice failed to load any source
file in the build environment, so WeasyPrint is the recorded route):

```bash
cd demo
pandoc slides.md -f markdown -t html5 --standalone --self-contained \
       --css slides.css -o /tmp/slides_build.html
python -c "from weasyprint import HTML; HTML(filename='/tmp/slides_build.html').write_pdf('slides.pdf')"
# verified output: exactly 5 PDF pages
```

## Results

Measured on **2026-11-25** against the **30-item held-out gold set**
(`eval/gold.csv`, disjoint from `data/fewshot_pool.jsonl`) using the real
OpenAI-compatible endpoint `ep-20261026151823-95mxw` (underlying model
`gpt-6-astra-2026-09-03`, strict `json_schema` mode, 0 unresolved rows, 0
repair retries):

* **`speaker_type` (3 classes: citizen / official / uncertain):** accuracy
  **1.0000** (30/30), macro-F1 **1.0000** (per-class P = R = F1 = 1.0000) in
  both zero-shot and 3-shot.
* **`stance` (4 classes: support / oppose / neutral / mixed):** accuracy
  **1.0000** (30/30), macro-F1 **1.0000** in both zero-shot and 3-shot.
* **`evidence` verbatim quote fidelity:** **1.0000** (30/30 exact substrings of
  the source segment; zero hallucinated or paraphrased quotes).
* **Best lever (ablation — 3-shot minus zero-shot):** free-text `topic`
  normalized exact-match rose from **0.1667 (5/30)** in zero-shot to
  **0.2667 (8/30)** in 3-shot (**Δ = +0.1000**, +3 items `seg-018`, `seg-024`,
  `seg-026`, 0 regressions), because the 2–3 word exemplars taught the model to
  drop trailing procedural nouns (`"funding"`, `"equity"`, `"award"`).
* **Top failure mode:** all 25 zero-shot (22 3-shot) `topic` misses are
  granularity/modifier drift on semantically correct topics (trailing process
  nouns, street/applicant proper nouns, or compound facets); plus a calibration
  finding where `uncertain` speakers receive mean confidence 0.974 (high
  meta-confidence in anonymity rather than low epistemic certainty). Full
  tables, confusion matrices and the 25-row error taxonomy are in
  `eval/RESULTS.md`.

## Reproducibility

* prompt versioned (`css5120-v1.0.0`) in `src/extract.py`; schema versioned
  (`1.0.0`) in `src/schema.py`;
* default temperature is `0.0` in code; because `gpt-6-astra-2026-09-03` on the
  internal Ark endpoint rejects `temperature=0` (only the server default `1` is
  accepted), the real evaluation was run with `OPENAI_TEMPERATURE=omit` (no
  temperature parameter sent) and this is recorded verbatim in
  `out/run_meta*.json` and `eval/RESULTS.md` — never falsely claimed as `0`;
* every run writes `out/run_meta.json` with model id, temperature policy,
  prompt version, shot count, UTC timestamp and unresolved count;
* mock output is deterministic: RNG seeded per segment id, labels are pure
  functions of text.

## Limitations & next steps

* 35 synthetic segments are enough to exercise the harness but not to estimate
  real-world precision; scale gold toward 40+ with a second human annotator
  (Track B inter-rater reliability).
* Lexical mock rules encode English cues only; non-English inputs degrade to
  `uncertain` by design (see robustness case `dirty-05`).
* Evidence is only checked for presence/length today; a stage-2 check should
  verify the quote is a true substring of the source on the API path too.
* No token/latency cost instrumentation yet — the remaining Track A option.
