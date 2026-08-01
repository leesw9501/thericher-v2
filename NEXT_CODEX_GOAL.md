# Next Codex Goal

## Objective

Advance the QQQ KIS Paper lifecycle and the first bounded intraday
window-sensitivity research package **in parallel**.

The installed freshness-gated QQQ scheduler remains the sole owner of its next
Paper lifecycle. The independent offline 1m window-sensitivity preflight has
already removed the fixed-90-bar blind spot for this small cache and closed
`no_structure`; it selected no window and qualified no CUDA work. While the
scheduler awaits a fresh session, Engine Research must continue with a separate
fresh/disjoint preparation package. Neither lane is an approval gate for the
other.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect the existing Task Scheduler state and current source-safe QQQ
   head-cache/session receipts. Do not manually start, stop, duplicate, or
   modify the Data collector or installed intraday-head task.
3. Reattest the existing QQQ route's pre-submit and recovery invariants without
   changing its decision table, sizing, freshness budget, or strategy.
4. Reattest the completed independent Research preflight below, then dispatch
   the next separately bounded Research preparation package. Both are offline
   cache consumers and must not read `.env`, KIS credentials, account facts,
   broker state, or `KIS_LIVE_*`.

## Parallel Work Packages

1. **Execution:** let the installed QQQ fresh-session path own the first new
   eligible Paper lifecycle. Reconcile an exact unknown outcome only through
   the existing read-only path.
2. **Data:** preserve the independent QQQ head-cache/currentness contract and
   publish only its source-safe ready/stale/no-intent facts. A stale receipt
   does not cause a manual collector launch or stop Research.
3. **Engine Research:** preserve the completed bounded QQQ 1m
   window-sensitivity CPU preflight as immutable `no_structure` evidence. Then
   prepare the next independent campaign without reusing that family's spent
   comparison sessions. It writes artifacts only below
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
4. **Research Steward:** do not allocate CUDA to the completed window family.
   Allocate the GPU only when a separate frozen campaign is actually eligible;
   `no_structure` is useful evidence, not a reason to manufacture training.
5. **Temporary Validation:** independently test the new preflight's causal
   session boundary, development-only normalization, block permutation,
   artifact isolation, and no-broker/no-credential envelope. It does not tune
   or select a window.

## Window-Sensitivity Contract

- Freeze the initial 1m cells before reading outcomes: `30`, `60`, `90`, `120`,
  and `180` completed bars. This first package does not claim a 5m, 10m, 1h,
  or 3h result; those remain later explicit cells or families.
- Use the existing chronological `10 development / 1 purge / 9 comparison`
  regular-session geometry. Every history and target resets within its session;
  a missing or cross-session input is `input_unavailable`, never silently
  trimmed or backfilled.
- Normalize using development data only. Count independent support by sessions
  or blocks, not overlapping bar windows. Each cell declares the same complete
  session minimum and its actual causal observation count.
- The CPU preflight uses one frozen lightweight model capacity per cell and a
  deterministic session-block label-permuted null replicate. Normalize model
  capacity by the same fixed optimizer-step count per cell, rather than
  allowing short windows more updates simply because they have more rows.
- Before materializing the real result, freeze the shared family budget,
  cell count, target, split, feature schema, naive reference, and
  `1.0x/1.5x/2.0x` cost-sensitivity declaration. Report aggregate metric
  distributions only; never rank a cell, select a winner, or fit an ensemble.
- The completed matrix's real cross-window statistic did not exceed the
  session-block null threshold, so it is `no_structure`; there is no LSTM,
  causal-TCN, compact-attention, or CUDA continuation under this family.
- This family is descriptive only. It may not create a profitability claim,
  sealed evaluation, model promotion, ensemble input, QQQ decision change,
  or Paper order. A later candidate needs a new later/disjoint replication
  family and fresh evaluation custody.

## Paper Contract

- Only the existing KIS Paper virtual route may read `KIS_PAPER_*`, and only
  after its own fresh eligible receipt passes its current regular-session and
  execution-control checks. Never read or route `KIS_LIVE_*`.
- Preserve the existing QQQ target resolution and one-share behavior. Do not
  add a Paper symbol, decision rule, model, ensemble, price rule, size rule,
  or retry rule.
- Persist the exact durable intent before a broker side effect. An ambiguous
  outcome pauses replacement of that exact intent until existing read-only
  reconciliation resolves it; it never becomes a global hold.
- Persist and report only source-safe lifecycle categories, intent/run hashes,
  route mode, and reconciliation status. Do not persist or output credentials,
  account identifiers, balances, prices, broker bodies, fill values, or PnL.

## Completion

- The Engine Research preflight has immutable external `no_structure` evidence
  and its focused tests prove the stated isolation and causal invariants. The
  next separate Research package has a frozen scope and its own bounded
  completion evidence.
- A new source-safe QQQ session reaches `canary_completed` with matching
  terminal/reconciliation evidence, or an exact technical failure is preserved
  and recovered without duplicate submit.
- No live route, manual duplicate scheduler, secret output, broad historical
  D1 dependency, unbounded grid, ranked window result, or Paper authority gate
  is introduced.
- Refresh stateboards, replace this file with one next company objective,
  verify, commit, push, and continue. A scheduler-owned QQQ wait is never a
  reason to leave the independent Research package idle.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add intraday window sensitivity preflight`
