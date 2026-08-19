# Next Codex Goal

## Objective

Complete `kis-daily-forward-causal-qualification-predicate-v1`: build one
offline, credential-free predicate that evaluates the existing QQQ/SPY KIS
Paper D1 forward cache against its fixed causal-input conditions separately.
It must distinguish a fully qualified synthetic fixture from the present
unqualified cache and write one immutable, source-safe external receipt for
the present cache. This improves the data-to-research loop; it does not create
a strategy result, candidate, model, GPU job, Paper action, or live behavior.

## Boundaries

- Read only the existing local QQQ/SPY D1 forward cache plus its source-safe
  external receipts. Do not read `.env` or credentials, construct a KIS client,
  call KIS or any network, invoke Docker or a scheduler, submit a broker order,
  or use GPU.
- Keep raw bars and cache bytes under `D:\market_data`; write only canonical
  aggregate qualification facts under
  `D:\thericher-v2\model-artifacts\data\kis-daily-forward-causal-qualification-v1`.
  Never write raw rows, prices, account facts, order identifiers, credentials,
  model parameters, predictions, or fitted artifacts.
- The frozen condition set must separately identify source/pair identity,
  complete-bar and calendar-continuity evidence, a named clock/session rule,
  a non-overlapping chronological boundary, decision-time availability, and
  provider finality. A condition that is not evidenced must remain
  `not_observed`; do not infer it from cache timestamps, task exit codes, or a
  receipt hash.
- `qualified` is an input classification only. It cannot itself authorize
  training, a replay, ranking, an ensemble, KIS Paper behavior, or live use.

## Required Work

1. Reuse existing forward-cache loaders and source-safe receipt readers where
   their semantics match. Add the smallest Data-owned module and script needed
   to produce the predicate and immutable receipt.
2. Freeze explicit condition identifiers and a fail-closed aggregate result.
   Emit current-cache evidence only after verifying every parent identity and
   output path stays external to Git.
3. Add focused tests with one fully qualified synthetic fixture and one
   single-condition ablation per condition. Each ablation must become
   `input_unavailable` and name the missing condition. Add isolation tests
   proving no credential, KIS client, network, Docker, scheduler, broker, GPU,
   raw row, or repository artifact access is required.
4. Run the one current-cache predicate exactly once with a new external label;
   reattach only its source-safe condition verdicts, receipt hash, and output
   pointer. The expected current outcome may be `input_unavailable`.
5. Refresh Data, Engine Research, Execution, Research Steward, orchestration,
   `HANDOFF.md`, and `RUNBOOK.md`; then run required verification, commit,
   push, replace this file with exactly one next company objective, and
   continue.

## Completion Evidence

- A source-safe immutable external receipt discriminates a complete synthetic
  fixture from every one-condition ablation and classifies the real current
  cache without raw data.
- Strongest kill test: if any single-condition ablation still produces
  `qualified`, close the objective as non-discriminating with no receipt,
  promotion, or downstream handoff.
- Also close without retry or consumer change if the predicate reads `.env`,
  constructs a KIS client, reaches a network/Docker/scheduler/broker path,
  writes outside the artifact root, or emits `qualified` when decision-time
  availability or provider finality is `not_observed`.
