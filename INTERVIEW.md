# INTERVIEW.md — 15 canonical agent questions, my own answers

## Mechanics

### 1. Walk me through the agent loop. What is ReAct, and how is an agent different from a chatbot?

The agent loop is observe - reason - act - observe again, until the task is
done. ReAct makes that explicit by alternating a reasoning trace with a tool
call, feeding each tool result back into the next reasoning step. A chatbot
only maps a conversation to text; an agent can take actions in an environment
and is judged on whether those actions succeed. My project is a deliberately
narrow agent: its "act" is one structured-output API call (optionally preceded
by a read-only summarizer subagent for inputs >3,000 chars) plus a bounded
one-shot repair retry, because extraction is a closed schema-filling task
where open-ended autonomy mostly adds failure modes.

### 2. How does tool/function calling actually work? The model can only emit text — so how does it "run" anything?

The model never executes anything; it emits a structured message naming a
function and JSON arguments, and the client-side harness decides whether that
call is allowed and runs the real code. In my repo the analogous mechanism is
`response_format={"type": "json_schema", "json_schema": OPENAI_STRICT_SCHEMA}`:
`gpt-6-astra-2026-09-03` emits text constrained to my five-field schema, and
my Python harness parses and validates it through Pydantic before anything is
written to `out/`. If validation fails, the harness — not the model — controls
the retry. That split, where the model proposes and deterministic code
disposes, is the core safety property of any tool-calling system.

### 3. What is MCP and what problem does it solve? When would you add a tool vs not?

MCP is a standard protocol that lets a model client talk to external tools
and data sources, databases, drives, APIs, through one reusable interface
instead of bespoke integrations per app. You add an MCP tool when the agent
needs a capability the model genuinely lacks, like reading a live database or
creating a calendar event, and the permission boundary is worth defining
explicitly. I chose *not* to use MCP in this project because my only
sub-job, summarizing a long transcript, is a text transformation over data I
already hold. Standing up a server, auth and an audit surface for that would
be pure overhead; a subagent with an isolated prompt is the lighter-weight
correct choice.

### 4. How do you get reliable structured output? What do you do when the model returns invalid JSON or an extra field?

I defend at two layers. First, the request carries a strict JSON Schema
(`src/schema.py`, `strict: True`, `additionalProperties: False`), so the
endpoint guarantees parseable JSON with my exact five required keys, across
both 35-item real runs (zero-shot and 3-shot, 70 API calls total),
`gpt-6-astra-2026-09-03` produced 100% schema-valid records on the first
attempt (`attempts=1`, `unresolved=0`). Second, Pydantic re-validates
semantics — enums, confidence in `[0,1]`, non-empty evidence, and
`extra="forbid"` so an injected extra field is rejected. On failure
`src/extract.py` performs at most one repair retry that sends the literal
validation error back; if that also fails, the item is logged to
`logs/repair.log` and recorded as `unresolved` rather than crashing the batch.

### 5. When do subagents/multi-agent setups help, and when do they hurt? Explain context isolation and its tradeoff.

They help when a sub-job is read-heavy or has a different prompt shape from
the main loop: isolating it keeps the main context window small and focused,
and each agent's instructions can be tightly scoped. My summarizer
subagent (`src/summarizer.py`) is exactly this, inputs over 3,000 characters
get a separate read-only compression prompt before extraction. The tradeoff
is that isolation is also information loss: the subagent cannot see the full
conversation, errors can compound across handoffs, and debugging multi-hop
failures is harder. I mitigate the first point by requiring the summary to
preserve role cues, topic, stance words and a verbatim quotable sentence.

## Context & cost

### 6. What is the context window, and what happens as it fills? How does that affect quality and cost?

The context window is the token budget the model can attend to in one call;
as it fills, older content gets compressed or dropped, attention dilutes, and
both latency and price rise because you pay for input tokens every call. In
my pipeline the concrete mitigation is the 3,000-character threshold: long
segments are summarized first so the extraction prompt stays short and
stable, and few-shot exemplars are capped at three so prompt size never grows
unboundedly. In our real 35-segment runs, keeping prompts compact held end-to-end
wall-clock to 101s (zero-shot, ~2.9s/item) and 91s (3-shot, ~2.6s/item), while
the offline mock mode lets unit tests verify the over-long robustness case
at zero token cost.

### 7. How would you reduce cost/latency of an agent in production without tanking quality?

First, route easy cases to a cheaper model or deterministic rules: our mock
backend handles explicit cue phrases (`"As a homeowner..."`, `"Chair moves..."`),
and in production a small model could handle high-confidence segments while
reserving `gpt-6-astra-2026-09-03` for ambiguous ones. Second, cap retries —
I allow at most one repair call, bounding worst-case cost at 2× per item.
Third, batch requests and enable prefix caching for the shared system prompt
and 3-shot exemplars. Every cost lever must be validated as an ablation on the
held-out gold set so we verify `speaker_type` and `stance` macro-F1 stay at
`1.0000` before shipping.

### 8. How do you keep an LLM pipeline reproducible across runs and teammates?

I pin everything under our control and log every deviation honestly: the model
endpoint (`ep-20261026151823-95mxw` → `gpt-6-astra-2026-09-03`), prompt version
(`css5120-v1.0.0`), schema version (`1.0.0`), and dependencies in
`requirements.txt`. When we ran the real evaluation, the Ark endpoint rejected
`temperature=0` (only server default `1` is allowed); rather than pretending
temperature was zero, I added `OPENAI_TEMPERATURE=omit` and logged
`"omitted (provider server default; OPENAI_TEMPERATURE=omit)"` verbatim in
`out/run_meta*.json` and `eval/RESULTS.md`. The 30 gold items and 5 few-shot
exemplars are static files guarded by a runtime disjointness assertion, so any
teammate can re-run the exact same script and audit the metadata trail.

## Reliability and safety

### 9. How do you stop an agent from doing something dangerous or irreversible?

Use deny-by-default guardrails in the harness, because the model cannot be
relied on to police itself. My write guardrail (`src/paths.py`) resolves the
full path including symlinks and `..` traversal, and refuses anything outside
the repo's `out/` directory or without a `.jsonl` suffix; a pytest case
proves symlink escapes are blocked. API credentials are loaded strictly from
external environment variables (`~/.config/ark/cred.env`, `chmod 600`) and
never touch the repo or git history. For irreversible actions in a broader
system, I require explicit human-in-the-loop confirmation before execution.

### 10. How do you detect and reduce hallucination in an extraction/annotation pipeline?

My primary defense is the mandatory `evidence` field: no label is accepted
without a verbatim supporting quote from the transcript, and the system prompt
explicitly marks segments as untrusted data to block prompt-injection
hallucinations. Schema validation blocks structurally invented fields, and the
`uncertain` speaker class provides an honest abstain channel when identity cues
are absent. On our 30-item real evaluation, we verified programmatically that
**30/30 (100%)** of `gpt-6-astra-2026-09-03`'s `evidence` quotes in both
zero-shot and 3-shot runs are exact character-for-character substrings of the
source segments — zero fabricated or paraphrased quotes.

### 11. An agent "passed the test" by weakening the test. How do you catch this, and what does it teach you?

You catch it by keeping evaluation artifacts immutable and auditing diffs on
test files separately from implementation files. During development, two mock
fixture items failed because the fixtures lacked speaker cues so the code
rightly returned `uncertain`; I fixed the fixture text rather than lowering
the accuracy threshold, and kept the fixture set strictly separate from
`eval/gold.csv`. Structurally, `tests/test_leakage.py` asserts `gold.csv` and
`fewshot_pool.jsonl` never share IDs (including a negative test that plants a
leaked ID and proves the guard fires). The lesson is that tests and benchmarks
are measurement instruments — if an agent can edit the ruler, the metric is
meaningless.

## Science & evaluation

### 12. How do you evaluate an agent? Design an eval for your task from scratch.

I hand-labelled a 30-item held-out gold set (`eval/gold.csv`) balanced across
speaker types (`11 citizen / 10 official / 9 uncertain`) and stances
(`8 support / 7 oppose / 8 neutral / 7 mixed`) over 30 distinct municipal
topics, kept 5 separate segments (`seg-031..035`) for few-shot prompting, and
enforced zero ID overlap at runtime. `eval/run_eval.py` computes accuracy,
per-class precision/recall/F1, macro-F1, and full confusion matrices for both
enums, plus normalized exact-match for free-text `topic`. On `gpt-6-astra-2026-09-03`,
both zero-shot and 3-shot achieved **`1.0000` accuracy and `1.0000` macro-F1**
on `speaker_type` (30/30) and `stance` (30/30), while 3-shot improved `topic`
exact-match from **`0.1667` (5/30) to `0.2667` (8/30, `Δ = +0.1000`)**.

### 13. Your extractor is 82% accurate. How do you improve it — and how do you know your change helped?

Start with granular error analysis before touching the model or prompt: inspect
every disagreement and categorize the failure modes. In our real evaluation,
enum classification hit 100%, so the real bottleneck was free-text `topic`
exact-match (25/30 misses in zero-shot). Reading all 25 disagreements showed
100% were on-topic granularity differences, which I bucketed into five modes:
trailing procedural nouns (M1, 8 cases), street/applicant proper-noun
over-specificity (M2, 6), compound-topic scope (M3, 6), synonym/dropped
modifier (M4, 3), and hyphen/plural surface form (M5, 2). Adding 3 concise
exemplars (`--shots 3`) directly attacked M1 — cutting procedural-noun misses
from 8 to 5 (`seg-018`, `seg-024`, `seg-026` fixed, 0 regressions) and lifting
exact-match by `+10.0` percentage points on the identical 30-item gold set.

### 14. Prompt engineering vs RAG vs fine-tuning — when would you reach for each?

Prompt engineering comes first because it is fast, transparent, and reversible:
our 3-shot ablation gained `+10.0` percentage points on `topic` exact-match and
our error analysis showed two more prompt/validator fixes (banning trailing
process nouns and capping `uncertain` confidence at `<=0.6` to fix the ~0.97
meta-confidence miscalibration) can be shipped in minutes. RAG is the right
next step when labels must align with an external canonical taxonomy — e.g.,
retrieving the city clerk's official agenda-item list so `topic` selects a
canonical phrase instead of free-generating. Fine-tuning only makes sense once
schema and taxonomy are frozen and we need a smaller, cheaper model to match
`gpt-6-astra-2026-09-03` at high volume.

## Experience (STAR)

### 15. "Tell me about an LLM tool you built." — your 2-minute STAR story

**Situation:** Municipal council transcripts are published as unstructured text,
making it hard to audit citizen vs. official stances across agenda topics.
**Task:** Build a reproducible extraction agent that outputs guaranteed-valid
5-field records, degrades safely on adversarial inputs, and is evaluated
against a held-out gold standard. **Action:** I encoded the codebook in
Pydantic (`speaker_type`, `topic`, `stance`, `confidence`, `evidence`), enforced
it via strict `json_schema` mode plus a single-retry repair loop logging to
`logs/repair.log`, added a read-only summarizer subagent for >3,000-char inputs,
an `out/`-only path guardrail, and runtime gold/few-shot leakage checks, backed
by 44 pytest cases and a 10-case robustness harness. **Result:** Evaluated on 30
held-out gold segments with `gpt-6-astra-2026-09-03`, the agent achieved
`1.0000` macro-F1 on both `speaker_type` (30/30) and `stance` (30/30) with
30/30 verbatim `evidence` substrings and 0 unresolved rows; a 0-shot vs. 3-shot
ablation lifted `topic` normalized exact-match from `0.1667` to `0.2667`
(`+10.0` pp, 0 regressions), and full error analysis uncovered a subtle
meta-confidence calibration bug (`~0.97` confidence on `uncertain` speakers)
with a concrete validator fix.
