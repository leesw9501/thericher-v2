# Next Codex Goal

## Objective

Build `task-owned-kis-intraday-causal-evidence-refresh-v1`.

Classify one later caller-selected `thericher-kis-paper-intraday-head`
completed-session result for the QQQ/NAS and SPY/AMS M1 causal input. This
advances data collection and frozen-research readiness only; it does not create
a prediction, GPU appointment, new Paper route, new broker order behavior, or
live feature. The existing task-owned QQQ observed/provisional Paper observation
remains separate execution evidence and cannot promote a model or claim PnL.

## Hard Boundaries

- Only the installed intraday-head task may read `KIS_PAPER_*` or call its
  existing KIS market-data path. Do not manually invoke its task, Docker
  service, KIS client, or a replacement collector. Never read, reference,
  route, log, or persist `KIS_LIVE_*`.
- Do not touch, stage, invoke, or reconcile the untracked alternate IWM
  collector work in the shared worktree. It remains rejected until separately
  assigned and independently reviewed.
- Keep raw market data in `D:\market_data` and source-safe receipts/artifacts
  in `D:\thericher-v2\model-artifacts`; never put raw rows, credentials,
  account facts, private request/response bodies, or private intent files in
  Git, stateboards, or reviewer prompts.
- Do not widen the existing schedule, add a parallel collector, foreground-wait
  for its `next_due`, or turn an unqualified result into an approval hold.

## Required Work

1. Run a concise Throughput Review and reattest task ownership, current
   `next_due`, exact consumers, active GPU ownership, and independent
   Execution work.
2. The requested falsification-first review returned `uncertain`. Treat the
   causal/finality conditions as necessary, default-deny conditions rather
   than proof that a self-consistent local receipt chain establishes provider
   origin. Before any future `qualified` designation, retain the named clock
   authority, timezone/DST session rule, and a non-overlapping chronological
   boundary. This is a scoped evidence limit, not a new provider, approval, or
   collection block.
3. After the existing task creates a caller-selected later terminal/capture/
   prospective evidence chain, use only offline readers to verify its exact
   identities, hashes, completed-bar/session geometry, chronological split, and
   retained decision-time availability/finality facts. The smallest offline
   default-deny reader extension is complete: it accepts an optional
   SHA-256-bound causal-condition attestation at a fixed external artifact
   location and verifies its exact capture, availability, and pair identities.
   No installed task writes that binding yet, so do not add another reader,
   attestation writer, task, collector, or scheduler in this objective.
   The existing QQQ loop/session/validator already carries its reattested v5
   `observed_provisional` grade; do not create a duplicate Paper route or
   evidence layer for it.
4. Mark the input `qualified` only if every predeclared condition is evidenced.
   Otherwise write the narrow `input_unavailable` or recovery fact with its
   exact missing condition and leave the next attempt to the installed task.
5. Only if qualified, have Engine Research freeze one existing candidate's
   dataset, target, chronological split, fixed 30/60/90-minute window matrix,
   cost band, naive baseline, replay-parity dependency, artifact root, and
   strongest kill test. Do not train or allocate GPU in this objective.
6. Refresh Data, Engine Research, Execution, orchestration, HANDOFF, and
   RUNBOOK with current source-safe facts. At the goal boundary, verify, commit,
   push, and replace this file with exactly one next company objective.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Record intraday causal input qualification`
