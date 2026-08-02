# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run `injected-multitimeframe-local-paper-replay-seam-v1`.

This Engine/Execution-owned objective closes one concrete integration gap: a
caller-injected, hermetic replay must traverse the existing causal
multi-timeframe window contract, existing completed-bar momentum prediction,
existing target-position policy, immutable research receipt, existing local
paper intent bridge, local-paper fill/replay, and the existing next-bar
backtest timing harness.

It is engine plumbing for later qualified model data. It is not a new scoring
framework, predictive study, strategy evaluation, or a reason to wait for a
data scheduler.

## Frozen Scope

- Use only deterministic in-memory synthetic completed `Bar` fixtures and
  test-owned temporary local-paper state. Do not read `D:\market_data`, Norgate,
  Tiingo, KIS caches, `.env`, credentials, accounts, or external artifacts.
- Reuse, rather than duplicate, these existing paths:
  - `build_causal_multitimeframe_sequence_window`,
  - `MomentumModel` / existing `ModelPrediction`,
  - `propose_target_exposure`,
  - `receipt_from_target_exposure_proposal`,
  - `prepare_local_paper_intent`,
  - existing local-paper fill/replay behavior, and
  - `run_next_bar_backtest`.
- Add at most one small pure replay module and one focused test module. Do not
  add a new score/prediction/decision/intent dataclass, a generic plugin
  framework, a queue, scheduler, dashboard, provider, persistent report, or
  model registry.
- The only scorer is the already implemented fixed momentum model over caller
  supplied completed windows. Do not train, tune, compare models, run GPU,
  load public weights, use a sealed holdout, create PnL/profitability metrics,
  rank symbols, create an ensemble, or persist model artifacts.
- Keep all fills `source: local_paper`. Do not invoke KIS, read KIS credentials,
  prepare a KIS Paper decision, submit/modify/cancel an order, enable live
  behavior, or expose a public endpoint.
- A test-local `EventStore`/emergency file is permitted solely to exercise the
  existing local-paper fill and replay behavior. It must contain no raw market
  source, credentials, or external account state and must not become an
  artifact or a runtime dependency.
- Do not use the current-listing Norgate broad panel or KIS broad panel. They
  remain non-PIT and non-model-eligible. Do not revisit the closed fixed-trio
  GBT, fixed-trio momentum, KIS D1 candle-noise, or exhausted intraday families.

## Required Work

1. Engine: implement the smallest caller-injected replay helper using existing
   domain types. It must construct all five `1m/5m/10m/1h/3h` causal windows at
   one UTC cutoff, derive existing momentum predictions, produce an eligible
   target-exposure proposal, narrow it to an immutable receipt, prepare a
   local-paper intent, fill it at the next bar, and replay the same fill.
2. Backtest: invoke the existing next-bar backtest harness on the same injected
   1m sequence as a timing assertion only. Do not interpret its numerical
   result as PnL or performance evidence.
3. Tests: prove a fixture-injected run is deterministic across two independent
   local-paper stores; all required timeframes, cutoff/window availability,
   decision-to-intent identity, next-bar timing, `source: local_paper`, and
   replay identity hold. Monkeypatch sentinels around the named existing paths
   and prove the helper traverses each one. Deny socket, URL, environment,
   provider/cache, KIS, and credential access. Reject incomplete/future/stale
   inputs without minting an intent.
4. Keep any returned or printed result source-safe: only opaque identities,
   categorical status, timeframe counts, and replay facts; never OHLCV values,
   raw timestamps, raw paths, account fields, or secrets.
5. Update Engine Research, Execution, orchestration, handoff, and decision
   stateboards with the bounded seam result. State explicitly that it is not a
   predictive/model-quality/PnL/Paper/KIS/GPU result and name the next data
   qualification needed before a trained model can consume it.

## Claude Review

Claude's falsification-first verdict is `supported-with-limits`.

It found the individual components already exist. The only justified work is
the injected-bar seam, not a duplicate architecture. Its strongest failure mode
is a parallel score/decision/intent path that bypasses the existing modules.
The required kill test is sentinel coverage for every named existing path plus
two byte-stable logical replay projections. If the implementation can pass
without traversing any named path, stop and remove the duplicate seam.

## Verification

Run focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper precondition is still blocked by its known interrupted
run roots, do not delete, rename, or bypass them. Record that scoped recovery
fact and run the helper's independent fresh-root mode plus the remaining
verification commands.

## Completion

Report focused and full verification, Claude result, exactly which existing
paths were traversed, and why no model/GPU/data/KIS/Paper/PnL work was added.
Commit and push completion evidence before replacing this file with exactly one
next objective and continuing.
