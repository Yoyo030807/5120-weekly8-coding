# AI-use note

**Course:** CSS 5120 · Week 10 homework (Build · Evaluate · Explain an AI Agent)
**Student:** Yao YU (SID 225030227)
**Date:** 2026-11-18

## How AI assistance was used

An AI coding assistant was used in the following ways while producing this
repository:

1. **Code generation and refactoring.** I used the assistant to draft and
   refactor Python modules (Pydantic schema, extraction client, guardrail,
   eval script, pytest cases, robustness harness), then reviewed, ran, and
   edited every file myself.
2. **Test and fixture authoring.** The assistant helped generate parametrized
   test cases and the 10 dirty-input scenarios. I defined the thresholds and
   hand-checked the expected labels; where a test failed, the cause was
   diagnosed before any change, and the test/assertions were never weakened to
   force a pass.
3. **Synthetic data drafting.** The 35 meeting segments and 5 few-shot
   exemplars were drafted interactively with AI assistance. I wrote and
   verified the annotation conventions (the codebook in `CLAUDE.md`),
   hand-labelled all 30 gold rows, and ran automated checks for word counts,
   cell coverage and gold/few-shot id leakage.
4. **Documentation drafting.** `WRITEUP.md`, `INTERVIEW.md`, `README.md`,
   `CLAUDE.md` and this note were drafted with AI assistance and revised by me
   so that every technical claim matches the actual code.
5. **Build tooling.** The PDF deck was rendered from Markdown with
   pandoc + WeasyPrint using commands the assistant suggested; I inspected all
   five rendered pages before accepting the output.

## What I did not delegate

- I made every design decision: the five-field schema, enum granularity,
  retry-once-then-log policy, `out/`-only write guardrail, and the choice of a
  subagent over an MCP tool.
- I hand-labelled the gold set and accept responsibility for every label.
- I personally ran the full verification (44 pytest cases, mock end-to-end
  pipeline, robustness harness, leakage assertions, checksum audit) and
  confirmed the outputs recorded in this repo.
- All metrics in `eval/RESULTS.md` come from real, non-mock API calls executed
  on `2026-11-25` against `ep-20261026151823-95mxw` (`gpt-6-astra-2026-09-03`)
  over the 30 held-out gold rows; no mock-rule or fabricated number is
  reported as model performance, and the endpoint's temperature constraint
  (`OPENAI_TEMPERATURE=omit` → server default `1`) is disclosed verbatim.

## Responsibility statement

I understand that AI assistance does not replace my own understanding. I can
explain every module, test and design trade-off in this repository, and I take
full responsibility for the code's correctness, the annotations' accuracy,
and the honesty of the evaluation. Any errors are my own.

Signature: ______________________________

Name (print): Yao YU

Date: ______________________________
