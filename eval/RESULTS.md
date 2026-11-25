# Evaluation results

All figures in this file come from **real, non-mock API calls** (`--mock` off,
`source="openai-compatible"` on every row) executed on **2026-11-25** against
the 30 held-out gold rows in `eval/gold.csv`. Gold labels were never included
in any prompt; few-shot exemplars were drawn exclusively from the disjoint
5-item pool `data/fewshot_pool.jsonl` (`seg-031`..`seg-035`), with disjointness
re-asserted by `assert_no_leakage()` before each run and inside `eval/run_eval.py`.

Reproduce from the saved outputs:
```bash
python eval/run_eval.py --pred-zero out/rows_zero.jsonl \
                        --pred-three out/rows_three.jsonl
```

To re-run live against the gateway (credentials read from environment only;
never stored in the repo):
```bash
# Set OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL in your shell, plus
# OPENAI_TEMPERATURE=omit for providers that reject temperature=0
python src/run.py data/ -o out/rows_zero.jsonl  --shot 0
python src/run.py data/ -o out/rows_three.jsonl --shot 3
python eval/run_eval.py --pred-zero out/rows_zero.jsonl \
                        --pred-three out/rows_three.jsonl
```

## Run configuration (reproducibility)

| Item | Value |
|---|---|
| Run date (UTC) | `2026-11-25T08:15:28+00:00` (zero-shot) · `2026-11-25T08:17:13+00:00` (3-shot) |
| Endpoint id (`OPENAI_MODEL`) | `ep-20261026151823-95mxw` |
| Underlying model (returned in API `model` field) | `gpt-6-astra-2026-09-03` |
| Base URL (`OPENAI_BASE_URL`) | `https://ark-cn-beijing.bytedance.net/api/v3` (OpenAI-compatible internal Ark gateway) |
| Structured output enforcement | `response_format={"type": "json_schema", "json_schema": OPENAI_STRICT_SCHEMA}` (`strict: true`) |
| Temperature | **Omitted (`OPENAI_TEMPERATURE=omit` → server default `1`)** — see reproducibility note below |
| Prompt version | `css5120-v1.0.0` (`PROMPT_VERSION` in `src/extract.py`) |
| Schema version | `1.0.0` (`SCHEMA_VERSION` in `src/schema.py`) |
| Gold set | 30 hand-labelled rows in `eval/gold.csv` (`seg-001`..`seg-030`, held out, never shown to model) |
| Few-shot pool | 5 disjoint exemplars in `data/fewshot_pool.jsonl` (`seg-031`..`seg-035`; `--shot 3` uses the first 3: `seg-031`, `seg-032`, `seg-033`) |
| Wall-clock runtime (35 segments) | 101 s (zero-shot, ~2.9 s/item) · 91 s (3-shot, ~2.6 s/item) |

### Honest reproducibility caveat on temperature

The codebase defaults to `temperature=0.0`, which is the standard determinism
setting. However, `gpt-6-astra-2026-09-03` on this Ark endpoint rejects
`temperature=0` at the HTTP layer with:

```text
BadRequest / InvalidParameter: Unsupported value: 'temperature' does not
support 0 with this model. Only the default (1) value is supported.
```

Rather than hard-coding `1.0` or falsely claiming `temperature=0`, `src/extract.py`
supports `OPENAI_TEMPERATURE=omit`: the parameter is omitted from the request
payload, the server applies its only supported default (`1`), and `out/run_meta*.json`
records `"omitted (provider server default; OPENAI_TEMPERATURE=omit)"` verbatim.
Reproducibility is anchored by (1) the strict JSON Schema wire contract,
(2) the pinned endpoint and underlying model snapshot `gpt-6-astra-2026-09-03`,
(3) the versioned system prompt `css5120-v1.0.0`, (4) the logged UTC timestamps,
and (5) archiving the exact raw outputs `out/rows_zero.jsonl` and `out/rows_three.jsonl`.

### Why each metric matters for this task

* **`speaker_type` per-class recall (especially `citizen` and `uncertain`)** — In civic-input analysis, false negatives on `citizen` erase public testimony from summaries read by council staff, while collapsing `uncertain` (anonymous voicemails, unsigned cards) into `citizen` or `official` fabricates demographic attribution where none exists.
* **`stance` macro-F1 across all four classes** — Council agendas are not binary roll calls: staff briefings are `neutral` by rule, and conditional amendments ("I support the goal, not this draft") are `mixed`. Macro-F1 weights the minority/nuanced classes (`mixed`, `oppse` n=7 each) equally with `support`/`neutral` (n=8 each).
* **`topic` normalized exact-match** — Open-ended strings cannot be scored with a fixed confusion matrix; exact match after lowercasing and whitespace normalization is a deliberately strict lower bound that exposes granularity and phrasing drift between the model and the codebook's short canonical labels.
* **`evidence` verbatim-substring rate** — Checks hallucination directly: every extracted quote must appear character-for-character inside the source segment.

---

## Zero-shot metrics (`out/rows_zero.jsonl`, n = 30 gold)

### `speaker_type`

| class | precision | recall | F1 | support | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| citizen | 1.0000 | 1.0000 | 1.0000 | 11 | 11 | 0 | 0 |
| official | 1.0000 | 1.0000 | 1.0000 | 10 | 10 | 0 | 0 |
| uncertain | 1.0000 | 1.0000 | 1.0000 | 9 | 9 | 0 | 0 |
| **accuracy** | | | **1.0000** | 30 | | | |
| **macro-F1** | | | **1.0000** | | | | |

Confusion matrix (rows = gold, cols = prediction):

| true \ pred | citizen | official | uncertain | unresolved |
|---|---:|---:|---:|---:|
| citizen | 11 | 0 | 0 | 0 |
| official | 0 | 10 | 0 | 0 |
| uncertain | 0 | 0 | 9 | 0 |

### `stance`

| class | precision | recall | F1 | support | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| support | 1.0000 | 1.0000 | 1.0000 | 8 | 8 | 0 | 0 |
| oppose | 1.0000 | 1.0000 | 1.0000 | 7 | 7 | 0 | 0 |
| neutral | 1.0000 | 1.0000 | 1.0000 | 8 | 8 | 0 | 0 |
| mixed | 1.0000 | 1.0000 | 1.0000 | 7 | 7 | 0 | 0 |
| **accuracy** | | | **1.0000** | 30 | | | |
| **macro-F1** | | | **1.0000** | | | | |

Confusion matrix (rows = gold, cols = prediction):

| true \ pred | support | oppose | neutral | mixed | unresolved |
|---|---:|---:|---:|---:|---:|
| support | 8 | 0 | 0 | 0 | 0 |
| oppose | 0 | 7 | 0 | 0 | 0 |
| neutral | 0 | 0 | 8 | 0 | 0 |
| mixed | 0 | 0 | 0 | 7 | 0 |

### `topic` and `evidence` (extraction fields)

| metric | value | count |
|---|---:|---:|
| `topic` normalized exact-match | **0.1667** | 5 / 30 (`seg-009`, `seg-017`, `seg-021`, `seg-029`, `seg-030`) |
| `evidence` exact verbatim substring of source text | **1.0000** | 30 / 30 (zero paraphrased or invented quotes) |

---

## 3-shot metrics (`out/rows_three.jsonl`, n = 30 gold)

Exemplars passed in prompt: `seg-031` (`topic="library hours"`), `seg-032`
(`topic="sole-source camera contract"`), `seg-033` (`topic="parking meters"`).

### `speaker_type`

| class | precision | recall | F1 | support | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| citizen | 1.0000 | 1.0000 | 1.0000 | 11 | 11 | 0 | 0 |
| official | 1.0000 | 1.0000 | 1.0000 | 10 | 10 | 0 | 0 |
| uncertain | 1.0000 | 1.0000 | 1.0000 | 9 | 9 | 0 | 0 |
| **accuracy** | | | **1.0000** | 30 | | | |
| **macro-F1** | | | **1.0000** | | | | |

Confusion matrix: identical to zero-shot (11 / 10 / 9 on the diagonal, 0 off-diagonal, 0 unresolved).

### `stance`

| class | precision | recall | F1 | support | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| support | 1.0000 | 1.0000 | 1.0000 | 8 | 8 | 0 | 0 |
| oppose | 1.0000 | 1.0000 | 1.0000 | 7 | 7 | 0 | 0 |
| neutral | 1.0000 | 1.0000 | 1.0000 | 8 | 8 | 0 | 0 |
| mixed | 1.0000 | 1.0000 | 1.0000 | 7 | 7 | 0 | 0 |
| **accuracy** | | | **1.0000** | 30 | | | |
| **macro-F1** | | | **1.0000** | | | | |

Confusion matrix: identical to zero-shot (8 / 7 / 8 / 7 on the diagonal, 0 off-diagonal, 0 unresolved).

### `topic` and `evidence` (extraction fields)

| metric | value | count |
|---|---:|---:|
| `topic` normalized exact-match | **0.2667** | 8 / 30 (kept all 5 zero-shot matches + gained `seg-018`, `seg-024`, `seg-026`; lost 0) |
| `evidence` exact verbatim substring of source text | **1.0000** | 30 / 30 |

---

## Ablation: 3-shot minus zero-shot

| field | zero-shot | 3-shot | Δ (3-shot − zero-shot) |
|---|---:|---:|---:|
| `speaker_type` accuracy | 1.0000 | 1.0000 | **+0.0000** |
| `speaker_type` macro-F1 | 1.0000 | 1.0000 | **+0.0000** |
| `stance` accuracy | 1.0000 | 1.0000 | **+0.0000** |
| `stance` macro-F1 | 1.0000 | 1.0000 | **+0.0000** |
| `topic` normalized exact-match | 0.1667 (5/30) | 0.2667 (8/30) | **+0.1000 (+3 items, 0 regressions)** |
| `evidence` verbatim-substring rate | 1.0000 (30/30) | 1.0000 (30/30) | **+0.0000** |

**Interpretation.** On the two closed-vocabulary enums (`speaker_type` and `stance`),
zero-shot performance is already at the ceiling (30/30) because the system
prompt's codebook definitions are explicit and the synthetic segments — while
containing realistic noise such as typos, hedges and bureaucratic phrasing —
still carry unambiguous role and stance cues for a frontier-class model
(`gpt-6-astra-2026-09-03`). Where 3-shot prompting measurably moves the needle
is the **unconstrained `topic` string (+10.0 percentage points, from 5/30 to
8/30 exact match, with zero regressions)**. In zero-shot mode the prompt only
says *"a short policy topic phrase"*, leaving noun-phrase length under-specified;
showing three concise 2–3 word exemplars (`"library hours"`, `"sole-source camera contract"`,
`"parking meters"`) teaches the model to trim trailing policy-process nouns,
converting `"public mural program funding"` → `"public mural program"` (`seg-018`),
`"stormwater fee equity"` → `"stormwater fee"` (`seg-024`), and
`"ambulance service contract award"` → `"ambulance service contract"` (`seg-026`).
It also tightens several near-misses (e.g. `seg-010` from `"electric vehicle charging in public parking facilities"`
to `"public electric vehicle charging buildout"` against gold `"EV charging buildout"`).
Exemplars cannot, however, tell the model whether gold prefers generic vs.
site-specific naming (`"dog park"` vs. `"Riverside dog park proposal"`), which
explains why 22/30 items still differ under strict string equality despite
100% semantic relevance.

---

## Error analysis (every disagreement examined)

* **`speaker_type` disagreements:** 0 / 30 in both zero-shot and 3-shot.
* **`stance` disagreements:** 0 / 30 in both zero-shot and 3-shot.
* **`evidence` non-verbatim quotes:** 0 / 30 in both runs (every quote is an exact substring of its segment).
* **`topic` exact-match disagreements:** **25 / 30 in zero-shot, reduced to 22 / 30 in 3-shot.** Every single disagreement is a **granularity, modifier or surface-form difference on a semantically correct topic** — the model never hallucinated an unrelated policy domain.

### Summary taxonomy of the 25 zero-shot `topic` disagreements

| Mode | Count (0-shot → 3-shot) | Segment IDs | Failure mechanism | Concrete fix |
|---|---:|---|---|---|
| **M1 · Trailing policy-process / aspect noun** | 8 → **5** *(3 fixed by 3-shot)* | `seg-001`, `seg-005`, `seg-006`, `seg-007`, `seg-018`✓, `seg-024`✓, `seg-026`✓, `seg-027` | Model appends a procedural head noun (`reform`, `adjustment`, `proposal`, `project`/`alignment`, `funding`, `equity`, `award`, `program`) to the core 2–3 word topic. | Add a codebook rule in `_system_prompt()`: *"Name the policy object in 2–3 words; omit generic suffixes like proposal, reform, program, adjustment, project, award, or funding unless part of the official title."* |
| **M2 · Site / proper-noun over-specificity** | 6 → 6 | `seg-002`, `seg-003`, `seg-013`, `seg-016`, `seg-019`, `seg-020` | Transcript names a specific street or applicant (`Maple Street`, `Linden Logistics`, `Elm Street corridor`, `Riverside`, `Fifth and Grove`, `Oakwood Avenue`); gold sometimes strips the proper noun (`dog park`, `roundabout`) and sometimes keeps it (`Elm Street traffic study`). | Specify the abstraction rule in the codebook (either *"drop street/applicant proper nouns"* or *"keep named corridors"*) and include one positive + one negative exemplar in `fewshot_pool.jsonl`. |
| **M3 · Scope expansion / multi-aspect phrasing** | 6 → 6 | `seg-004`, `seg-010`, `seg-015`, `seg-022`, `seg-025`, `seg-028` | Segment discusses two linked facets (e.g. library budget *and* Sunday hours; rezoning *and* school capacity; EV charging *in public parking facilities*); model either joins both facets or picks the other facet (`rezoning and neighborhood impacts` / `rezoning`). | Replace free-text `topic` with a controlled agenda-item enum when the meeting packet is available, or score `topic` with token-level F1 / character n-gram overlap alongside exact match. |
| **M4 · Lexical synonym / dropped modifier** | 3 → 3 | `seg-008`, `seg-012`, `seg-014` | Model uses the speaker's surface phrasing (`proposed navigation center`, `camera expansion ordinance`, `first-quarter revenue report`) where gold uses a domain label (`homeless navigation center`, `surveillance camera expansion`, `quarterly city revenues`). | Provide the meeting agenda header as an input field or evaluate with embedding/token-overlap similarity in addition to exact match. |
| **M5 · Hyphenation / singular–plural surface** | 2 → 2 | `seg-011`, `seg-023` | `food-truck ordinance` vs. `food truck ordinance` (hyphen copied from transcript) and `transit operating subsidy cut` (singular + modifier) vs. `transit subsidy cuts`. | Normalize hyphens/punctuation and lemmatize plurals in `eval/run_eval.py::_normalize()`. |

### Full item-by-item table of all 25 `topic` disagreements

| id | mode | gold `topic` | zero-shot prediction | 3-shot prediction | 3-shot status & specific cause |
|---|---|---|---|---|---|
| `seg-001` | M1 | `missing-middle zoning` | `missing-middle zoning reform` | `missing-middle zoning reform` | Unchanged — transcript says *"missing-middle zoning reform"*; model keeps trailing `"reform"`. |
| `seg-002` | M2 | `community garden` | `Maple Street community garden` | `Maple Street community garden` | Unchanged — model retains street name `"Maple Street"`. |
| `seg-003` | M2 | `warehouse development` | `Linden Logistics warehouse variance` | `Linden Logistics warehouse variance` | Unchanged — model uses applicant name + `"variance"` instead of generic `"development"`. |
| `seg-004` | M3 | `short-term rentals` | `Citywide legalization of whole-home short-term rentals` | `citywide whole-home short-term rental legalization` | Tightened (7 → 6 words) but still includes policy action (`"citywide whole-home ... legalization"`). |
| `seg-005` | M1 | `water rates` | `water rate adjustment` | `water rate adjustment` | Unchanged — singular `"rate"` + procedural noun `"adjustment"`. |
| `seg-006` | M1 | `municipal broadband` | `municipal broadband proposal` | `municipal broadband proposal` | Unchanged — trailing `"proposal"`. |
| `seg-007` | M1 | `protected bike lane` | `protected bike lane project` | `protected bike lane alignment` | Unchanged — trailing `"project"` / `"alignment"`. |
| `seg-008` | M4 | `homeless navigation center` | `proposed navigation center` | `proposed navigation center` | Unchanged — transcript calls it *"the proposed navigation center"* without the word *"homeless"*. |
| `seg-010` | M3 | `EV charging buildout` | `electric vehicle charging in public parking facilities` | `public electric vehicle charging buildout` | Closer in 3-shot (adopts `"buildout"`), but expands acronym `"EV"` → `"electric vehicle"` + `"public"`. |
| `seg-011` | M5 | `transit subsidy cuts` | `transit operating subsidy cut` | `transit operating subsidy cut` | Unchanged — inserts `"operating"` from transcript and uses singular `"cut"`. |
| `seg-012` | M4 | `surveillance camera expansion` | `camera expansion ordinance` | `camera expansion ordinance` | Unchanged — drops `"surveillance"` and adds `"ordinance"`. |
| `seg-013` | M2 | `Elm Street traffic study` | `Elm Street corridor traffic study` | `Elm Street corridor traffic study` | Unchanged — keeps `"corridor"` from *"Elm Street corridor traffic study"*. |
| `seg-014` | M4 | `quarterly city revenues` | `first-quarter revenue report` | `first-quarter revenue report` | Unchanged — copies document title *"first-quarter revenue report"* from speech. |
| `seg-015` | M3 | `industrial rezoning` | `industrial-to-residential rezoning` | `industrial-to-residential rezoning` | Unchanged — specifies target zone (`"-to-residential"`). |
| `seg-016` | M2 | `dog park` | `Riverside dog park proposal` | `Riverside dog park proposal` | Unchanged — retains park name `"Riverside"` + `"proposal"`. |
| `seg-018` | M1 | `public mural program` | `public mural program funding` | **`public mural program`** | **FIXED in 3-shot** — exemplars taught 3-word noun-phrase length; trailing `"funding"` dropped. |
| `seg-019` | M2 | `roundabout` | `roundabout at Fifth and Grove` | `roundabout at Fifth and Grove` | Unchanged — retains intersection location. |
| `seg-020` | M2 | `cannabis dispensary permit` | `Oakwood Avenue cannabis dispensary special-use permit` | `cannabis dispensary special-use permit` | Closer in 3-shot (drops street `"Oakwood Avenue"`), still keeps `"special-use"`. |
| `seg-022` | M3 | `library budget` | `library budget and operating hours` | `library budget and hours` | Tightened (5 → 4 words), still conjoins second facet `"and hours"`. |
| `seg-023` | M5 | `food truck ordinance` | `food-truck ordinance` | `food-truck ordinance` | Unchanged — single hyphen difference (`"food-truck"` in source text). |
| `seg-024` | M1 | `stormwater fee` | `stormwater fee equity` | **`stormwater fee`** | **FIXED in 3-shot** — trailing aspect noun `"equity"` dropped. |
| `seg-025` | M3 | `rezoning and school capacity` | `rezoning and neighborhood impacts` | `rezoning` | Unchanged (miss in both) — 3-shot over-shortens compound topic to `"rezoning"`. |
| `seg-026` | M1 | `ambulance service contract` | `ambulance service contract award` | **`ambulance service contract`** | **FIXED in 3-shot** — trailing procedural noun `"award"` dropped. |
| `seg-027` | M1 | `rental inspections` | `rental inspection program` | `rental inspection program` | Unchanged — singular + trailing `"program"`. |
| `seg-028` | M3 | `street flooding and drainage` | `drainage project and flooding documentation` | `drainage project` | Unchanged (miss in both) — reorders/truncates compound topic. |

### Secondary finding: confidence calibration on `uncertain` speakers

The system prompt instructs: *"use <=0.6 when cues are weak."* However, across
the 9 `uncertain` gold segments, the model emitted mean confidence **0.974**
(zero-shot, range 0.94–0.98) and **0.969** (3-shot, range 0.95–0.98), vs.
0.988 on `citizen` and 0.989 on `official`. Inspection shows why: segments
like `seg-003` (*"The speaker asked that their name be withheld"*) or `seg-006`
(*"Submitted via the online portal with no name attached"*) provide **strong,
unambiguous cues that the speaker's identity is unknown**. The model is
reporting high *meta-confidence in the `uncertain` label*, whereas the codebook
intended low *epistemic certainty about who the speaker is*. **Proposed fix:**
decouple the two in the prompt (*"If `speaker_type` is `'uncertain'`, cap
`confidence` at `0.60` regardless of how clearly the transcript states that the
speaker is anonymous"*) or enforce the cap in a Pydantic `@model_validator`.

---

## Unresolved / repair events

| run | segments processed | unresolved rows | retry/repair attempts (`attempts == 2`) | `logs/repair.log` entries from this run | notes |
|---|---:|---:|---:|---:|---|
| zero-shot (`out/rows_zero.jsonl`) | 35 | **0** | **0** | **0** | All 35 segments passed strict `json_schema` + Pydantic validation on attempt 1 (`segments_summarized = 0`; max segment length is 848 chars < 3,000 threshold). |
| 3-shot (`out/rows_three.jsonl`) | 35 | **0** | **0** | **0** | All 35 segments passed on attempt 1 (`segments_summarized = 0`). Existing lines in `logs/repair.log` are from the offline robustness harness (`dirty-01..03`). |
