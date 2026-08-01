# Next Codex Goal

## Objective

Build one small causal multi-timeframe sequence-window contract for future
model families.

This is Engine Research infrastructure, not a training campaign: it makes the
lookback window an explicit, testable input for rule, ML, LSTM, Transformer, or
future ensemble research while preserving completed-bar causality.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the Norgate D1 pilot only as offline loader plumbing. It is not a
   training, ranking, GPU, PnL, or Paper input.
3. Ask Claude for a short falsification-first check before changing completed-bar
   or feature-window timestamp semantics. A timeout is `review_unavailable`,
   not support or a hold.

## Work

1. **Engine Research:** add a pure, in-memory sequence-window contract that
   consumes caller-supplied completed `Bar` sequences for `1m`, `5m`, `10m`,
   `1h`, and `3h`. A caller declares the exact lookback length per timeframe;
   no default winning window, model family, threshold, or hyperparameter search
   may be implied.
2. **Engine Research:** preserve each window's last completed-bar timestamp and
   reject incomplete, future, duplicate, non-contiguous, symbol/market/timeframe
   mismatched, or cross-timeframe cutoff-misaligned input. Expose only typed
   window data and source-safe structural metadata; do not calculate labels,
   scores, rankings, predictions, targets, allocations, artifacts, or PnL.
3. **Data:** keep the adapter provider-neutral and KIS-shaped. It must accept
   existing injected/local `Bar`s without a Norgate SDK, KIS call, credential,
   network, Docker provider, raw-data write, or a static-universe fallback.
4. Add focused tests for all five timeframes, variable lookbacks such as 30,
   60, 120, and 300 bars, exact completed-bar cutoff behavior, every rejection
   class, deterministic ordering, and no model/Paper/broker/network path.
5. Record the contract and one next research recovery fact in the Engine/Data
   stateboards without adding a report family, gate, worker, or durable role.

## Completion

- A pure reusable sequence-window contract exists with causal timestamps and no
  external side effects.
- The Norgate pilot remains `offline_research_only`; no model or GPU campaign
  is created merely because a window interface exists.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. Scheduler-owned KIS work remains independent.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add Norgate daily pilot`
