# Next Codex Goal

## Objective

Build `task-owned-kis-intraday-causal-observation-qualification-v1`.

Turn one new task-owned `thericher-kis-paper-intraday-head` completed-session
result into a source-safe qualification decision for the QQQ/NAS and SPY/AMS
M1 input. This advances data collection and frozen-research readiness only. It
does not create a prediction, GPU appointment, Paper intent, broker order, or
live feature.

## Hard Boundaries

- Only the installed intraday-head task may read `KIS_PAPER_*` or call its
  existing KIS market-data path. Do not manually invoke its task, Docker
  service, KIS client, or a replacement collector. Never read, reference,
  route, log, or persist `KIS_LIVE_*`.
- Do not touch, stage, invoke, or reconcile the untracked alternate IWM
  collector work in the shared worktree. It remains rejected until a separately
  assigned, independently reviewed repair.
- Keep raw market data in `D:\market_data` and source-safe receipts/artifacts
  in `D:\thericher-v2\model-artifacts`; never put raw rows, credentials,
  account facts, or private request/response bodies in Git, stateboards, or
  Claude prompts.
- Preserve the current source-local 21-session caches as non-promoting. Do not
  infer decision-time availability, provider finality, or historical reach from
  a scheduler result, a cache timestamp, or a single terminal page.
- Do not widen the existing schedule, add a parallel collector, foreground-wait
  for its `next_due`, or turn an unqualified result into an approval hold. A
  lane-local result remains scoped while ready Execution and preparation work
  continues.

## Required Work

1. Run a concise Throughput Review. Reattest the existing task ownership,
   current `next_due`, and the exact-data consumers that a qualification could
   enable; keep unrelated KIS Paper observer and Execution work independent.
2. Before a promotion decision, ask Claude for a short falsification-first
   challenge of the causal/finality rule. A limit, timeout, or unavailable
   review is `review_unavailable`, not agreement and not a block on collection.
3. When the existing task produces a caller-selected exact terminal/capture/
   prospective evidence chain, use only offline readers to verify its bound
   identities, hashes, completed-bar/session geometry, and any retained
   decision-time availability or finality facts. Add the smallest missing
   source-safe reader or contract test only when the existing chain cannot make
   that decision reproducibly.
4. Classify the exact input as `qualified` only when every predeclared causal,
   completed-bar, temporal-split, and finality/availability requirement is
   evidenced. Otherwise record a narrow `input_unavailable` or recovery result
   with the exact missing fact and let the existing task own the next attempt.
5. If and only if the input is qualified, have Engine Research freeze one
   existing candidate's dataset, target, chronological split, fixed 30/60/90m
   window matrix, cost band, naive baseline, replay-parity dependency, artifact
   root, and strongest kill test. This freezes a future campaign contract; it
   does not train or allocate GPU in this objective.
6. Refresh Data, Engine Research, orchestration, HANDOFF, and RUNBOOK with only
   current source-safe facts. At the goal boundary, verify, commit, push, and
   replace this file with one material next objective.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Qualify task-owned intraday input`
