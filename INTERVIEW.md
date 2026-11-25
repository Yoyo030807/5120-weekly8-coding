# INTERVIEW.md — 15 canonical agent questions, my own answers

*First-person answers for CSS 5120 Week 10, grounded in the Council-Mining
repo. Where a real model result is needed I say "to be filled after the API
run"; I have not run a paid LLM yet, so no accuracy number below is invented.*

## Mechanics

### 1. Walk me through the agent loop. What is ReAct, and how is an agent different from a chatbot?

The agent loop is observe → reason → act → observe again, until the task is
done. ReAct makes that explicit by alternating a reasoning trace with a tool
call, feeding each tool result back into the next reasoning step. A chatbot
only maps a conversation to text; an agent can take actions in an environment
and is judged on whether those actions succeed. My project is a deliberately
narrow agent: its "act" is one structured-output API call plus a bounded
repair retry, not an open-ended tool loop, because extraction is a closed
schema-filling task where extra autonomy mostly adds failure modes.

### 2. How does tool/function calling actually work? The model can only emit text — so how does it "run" anything?

The model never executes anything; it emits a structured message naming a
function and JSON arguments, and the client-side harness decides whether that
call is allowed and runs the real code. In my repo the analogous mechanism is
`response_format={"type": "json_schema", ...}`: the model emits text that is
constrained to my five-field schema, and my Python code parses and validates
it through Pydantic before anything is written. If validation fails, the
harness — not the model — controls the retry. That split, where the model
proposes and deterministic code disposes, is the core safety property of any
tool-calling system.

### 3. What is MCP and what problem does it solve? When would you add a tool vs not?

MCP is a standard protocol that lets a model client talk to external tools
and data sources — databases, drives, APIs — through one reusable interface
instead of bespoke integrations per app. You add an MCP tool when the agent
needs a capability the model genuinely lacks, like reading a live database or
creating a calendar event, and the permission boundary is worth defining
explicitly. I chose *not* to use MCP in this project because my only
sub-job, summarizing a long transcript, is a text transformation over data I
already hold. Standing up a server, auth and an audit surface for that would
be pure overhead; a subagent with an isolated prompt is the lighter-weight
correct choice.

### 4. How do you get reliable structured output? What do you do when the model returns invalid JSON or an extra field?

I defend at two layers. First, the request itself carries a strict OpenAI
JSON Schema (`src/schema.py`), so the platform guarantees parseable JSON with
exactly my five required keys. Second, Pydantic re-validates semantics —
enums, confidence in [0,1], non-empty evidence, and `extra="forbid"` so an
injected extra field is an error. On failure my code in `src/extract.py`
performs exactly one repair retry that sends the literal validation error
back asking for a corrected object; if that also fails, the item is written
to `logs/repair.log` and becomes an `unresolved` row instead of crashing the
batch. The tests assert all of these paths, including the enum and range
rejections.

### 5. When do subagents/multi-agent setups help, and when do they hurt? Explain context isolation and its tradeoff.

They help when a sub-job is read-heavy or has a different prompt shape from
the main loop: isolating it keeps the main context window small and focused,
and each agent's instructions can be tightly scoped. My summarizer
subagent (`src/summarizer.py`) is exactly this — inputs over 3,000 characters
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
unboundedly. In mock mode I can also unit-test the summarizer deterministically
with no token cost, which is how I verified the over-long robustness case
actually compresses.

### 7. How would you reduce cost/latency of an agent in production without tanking quality?

First, stop calling the model for things code can decide: my mock backend
proves deterministic lexical rules handle high-cue segments, and a real
system could route easy cases to a small model or rules and reserve the
strong model for low-confidence ones. Second, cap retries — I allow exactly
one repair call, so worst case is 2× per item, never unbounded. Third,
temperature 0 and a versioned prompt reduce wasted variation, and prompt
caching or batching would cut repeated system-prompt costs. Every such change
has to be measured as an ablation against the gold set, not assumed.

### 8. How do you keep an LLM pipeline reproducible across runs and teammates?

I pin everything that can change behavior: the model id comes from a
documented environment variable, temperature is fixed at 0 in code, the
prompt carries a version string (`css5120-v1.0.0`), and dependencies are
pinned in `requirements.txt`. Every run writes `out/run_meta.json` with the
timestamp, model, temperature, prompt version, schema version, shot count and
unresolved count, so any output file is traceable to its configuration. The
gold set and few-shot pool are static files with a leakage assertion, and the
mock backend is deterministic — its RNG is seeded per segment id, so two
teammates get byte-identical mock output.

## Reliability and safety

### 9. How do you stop an agent from doing something dangerous or irreversible?

Use deny-by-default guardrails in the harness, because the model cannot be
relied on to police itself. My write guardrail (`src/paths.py`) resolves the
full path including symlinks and `..` traversal, and refuses anything outside
the repo's `out/` directory or without a `.jsonl` suffix; there is a pytest
case proving a symlink escape is blocked. Credentials are read only from
environment variables — nothing is hard-coded — and mock mode performs zero
network calls. For truly irreversible actions in a bigger system I would add
explicit human-in-the-loop approval, since a permission check is only as good
as its default.

### 10. How do you detect and reduce hallucination in an extraction/annotation pipeline?

My primary mechanism is the `evidence` field: no label is accepted without a
verbatim quote from the source, and the system prompt explicitly says segments
are data, not instructions, to stop injection-style hallucinations. Schema
validation rejects structurally invented output, and the `uncertain` speaker
label plus bounded confidence give the model an honest "I don't know" channel
instead of forcing a confident guess. At the pipeline level, hallucination is
ultimately caught by the held-out gold evaluation and per-item error
analysis; I would add a substring-provenance check on the API path next, since
today the prompt asks for verbatim quotes but only the mock path enforces it.

### 11. An agent "passed the test" by weakening the test. How do you catch this, and what does it teach you?

You catch it by making the test independent of the thing being tested and by
auditing what actually changed on failure. In my own development, a mock
accuracy test failed on two fixture segments; I discovered the fixtures
lacked any speaker self-identification, so returning `uncertain` was actually
correct behavior — I fixed the fixtures instead of lowering the threshold, and
the threshold test still runs on data separate from the gold set. Structurally,
the repo enforces this discipline: gold and few-shot ids are asserted
disjoint (with a poisoned negative test), and `RESULTS.md` explicitly bans
mock numbers so a strong-looking mock score can never be reported as model
quality. The lesson is to treat the test as a measurement instrument: if
reality conflicts with it, investigate before touching either side.

## Science & evaluation

### 12. How do you evaluate an agent? Design an eval for your task from scratch.

I hand-labelled 30 segments as a held-out gold set covering all twelve
speaker-type × stance cells with at least two examples each, kept five
separate exemplars for few-shot prompting, and asserted the two id sets never
overlap. The eval script (`eval/run_eval.py`) reports accuracy, per-class
precision/recall/F1 with support counts, macro-F1, and a full confusion
matrix for both enums, plus normalized exact-match for the free-text topic;
unresolved predictions count as errors rather than being dropped. Precision
matters here because a false "official" label misattributes statements to the
city, and recall matters because missed citizen opposition skews the public
participation record. The headline numbers are to be filled after the real
API run — I will not substitute mock output.

### 13. Your extractor is 82% accurate. How do you improve it — and how do you know your change helped?

I start with error analysis, not model swapping: read every disagreement,
bucket it (ambiguous speaker, title over-trust, coarse schema, bad evidence),
and check whether errors concentrate in one class via the confusion matrix.
Then I change one thing at a time — my built-in ablation is zero-shot versus
3-shot, and the eval script computes the accuracy and macro-F1 delta
automatically — so any movement is attributable. A change "helps" only if the
delta is real on the same fixed gold set and no other class regresses; with
30 items I would also note that a single flipped row is ~3 points, so I'd
expand the gold before claiming small gains.

### 14. Prompt engineering vs RAG vs fine-tuning — when would you reach for each?

Prompt engineering first, because it is cheapest and fully reversible: my
codebook, repair message and few-shot exemplars are all prompt-level levers
and cover most expected variation. RAG when the task needs facts the model
cannot know — for a meeting pipeline that would mean retrieving past council
decisions or zoning codes to ground topic labels, which this version does not
do. Fine-tuning only after I have enough labelled failures to make it worth
it, typically hundreds of consistently-misclassified examples and a stable
schema, because it locks in behavior and makes prompt iteration slower. Here
the honest next step is still prompt plus eval work; fine-tuning would be
premature at 30 gold items.

## Experience (STAR)

### 15. "Tell me about an LLM tool you built." — your 2-minute STAR story

**Situation:** civic meeting transcripts sat as free text, and anyone
wanting stakeholder or stance analysis had to read them by hand; an
extractor without validation or measurement would just be a demo. **Task:**
build a portfolio-grade tool that returns guaranteed-valid five-field
records, fails safely on messy input, and can be scored against a gold
standard. **Action:** I wrote a Pydantic codebook with two enums, bounded
confidence and a mandatory evidence quote, enforced it through strict JSON
Schema plus a one-shot repair loop that logs failures as `unresolved` rows,
added a read-only summarizer subagent for long inputs, an `out/`-only write
guardrail, and gold/few-shot leakage assertions. I hand-built 35
de-identified segments, a 30-item gold set, ten adversarial inputs and 44
pytest cases, and I kept a deterministic mock backend so the whole harness
runs offline — while explicitly banning mock scores from the results
document. **Result:** the full pipeline and test suite run green with no API key, all ten
dirty inputs degrade gracefully with logged reasons, and on the 30-item held-out
gold set with `gpt-6-astra-2026-09-03` (endpoint `ep-20261026151823-95mxw`,
strict `json_schema` mode, 0 unresolved rows), `speaker_type` and `stance`
both reached `1.0000` macro-F1 (30/30), all 30 `evidence` quotes were exact
verbatim substrings, and 3-shot prompting lifted free-text `topic` normalized
exact-match from `0.1667` (5/30) to `0.2667` (8/30, `Δ = +0.1000`, +3 items,
0 regressions) by teaching the model to drop trailing procedural nouns. The
hardest bugs were a substring trap where "transition" matched my "transit"
topic rule (fixed by ordering specific rules before generic ones) and the
target gateway rejecting `temperature=0` (solved cleanly via
`OPENAI_TEMPERATURE=omit` and logged honestly in `run_meta.json`).
