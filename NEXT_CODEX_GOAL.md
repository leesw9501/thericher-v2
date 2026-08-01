# Next Codex Goal

## Objective

Close the interpretation of the first fixed QQQ multi-timeframe consensus
replay without retuning it.

The completed `qqq-20260623-20260721-consensus-r1` baseline proved the causal
model-to-`local_paper` product path, but it entered only two of twenty sessions.
Its all-session always-long total is not an equal-count selection comparator.
Build one bounded CPU-only equal-count session-subset null diagnostic while the
installed QQQ KIS Paper scheduler continues as its own independent lane.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   stateboards.
2. Reattach the immutable consensus baseline summary under
   `D:\thericher-v2\model-artifacts\research\kis-intraday-multitimeframe-consensus-replay-v1`.
   Do not rewrite it or use its outcome to alter a parameter.
3. Inspect the existing scheduler state only. Do not manually start, stop,
   duplicate, or modify its Data collector or intraday-head task.

## Work

1. Freeze a new external precommit before calculating results. Bind the exact
   completed 20-session QQQ KIS-private 1m catalog, the immutable baseline
   contract identity, observed fixed entry count, one-share local-paper cost
   semantics, and the equal-count null method.
2. Reproduce only the already-frozen decision mask and time-matched
   always-long round-trip outcomes. Compare the selected subset against the
   complete enumerated or deterministic-permuted distribution of equally sized
   session subsets. Keep all per-session prices, fills, masks, and PnL in
   memory; write aggregate source-safe diagnostics only.
3. The result may classify `selection_unqualified`, `input_unavailable`, or a
   descriptive null statistic. It may not select/tune a model, change any
   consensus expert, create an ensemble, allocate GPU, open a sealed holdout,
   claim profitability, or affect KIS Paper scheduling or behavior.
4. Preserve QQQ Data/Execution ownership: a scheduler-owned wait or source
   issue cannot defer the diagnostic, and the diagnostic cannot trigger a
   collector or broker call.
5. If the result appears materially stronger than its equal-count null, ask
   Claude for a short falsification-first challenge before recording a
   follow-up. A timeout is `review_unavailable`, never support or a global
   hold.

## Completion

- One immutable external precommit and aggregate-only summary exist outside
  Git, with no raw data, raw fills, credentials, network, KIS, broker, or GPU
  activity.
- Focused tests prove causal masking, equal-count null cardinality, local-paper
  replay parity, artifact isolation, and no credential/network/broker path.
- The stateboards record the bounded conclusion and a later/disjoint
  replication requirement rather than a new gate.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. The scheduler remains independent.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add intraday consensus replay baseline`
