# Next Codex Goal

## Objective

Build and run one frozen, CPU-only QQQ/SPY D1 relative-regime falsification
control against the existing hash-attested private daily catalog.

This is breadth research only. It must produce local-paper evidence, not a
selected model, ensemble member, GPU campaign, KIS Paper input, or profitability
claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `DECISIONS.md`, and the active Data, Engine Research, Execution, and
   orchestration stateboards.
2. Reattest the existing QQQ/SPY daily catalog and preserve its existing
   retrospective/source limitations. Do not fetch data or use the current
   intraday-head recovery result as a research input.
3. Ask Claude for a short falsification-first drift check only if the frozen
   contract would open a sealed holdout, promote a result, or change an existing
   strategy/execution authority. A normal candidate-only CPU control does not
   wait on the expired local Claude OAuth session.

## Frozen Candidate

- On completed daily session `t`, calculate each asset's 63-session close return
  from QQQ and SPY only.
- Enter one QQQ `local_paper` long position at `t+1` open only when QQQ's return
  is strictly greater than SPY's; otherwise remain flat.
- Flatten at `t+2` open. Use one share, the existing fixed after-cost economics,
  and no overlapping positions.
- Use the existing chronological 3,783 development / 22 purge / 951 validation
  session contract. A validation decision is eligible only when its full
  63-session causal feature window and both execution bars are inside its own
  split.
- Compare only fixed time-matched `always_long` and `flat` baselines. The
  candidate is falsified if validation has zero trades or does not strictly beat
  both comparators after costs. Do not tune the lookback, threshold, cadence,
  costs, or comparator after seeing results.

## Work

1. **Data:** add a narrow, source-safe loader/contract binding that reattests
   QQQ/SPY catalog identity before it exposes the exact causal slices. Preserve
   completed-bar, source, point-in-time, and corporate-action limitations.
2. **Engine Research:** implement the fixed deterministic control and its
   content-addressed external artifact under
   `D:\thericher-v2\model-artifacts`. Persist only provenance, configuration,
   aggregate metrics, categorical outcome, and replay identity; never raw bars,
   derived returns, per-decision values, model weights, or checkpoints.
3. **Execution:** use the existing broker-free local paper simulator only. Every
   fill must remain `source: local_paper`; do not create a KIS client, account
   read, quote, order, or schedule.
4. **Validation:** add focused tests for causal 63-session boundaries, split and
   purge isolation, fixed baseline alignment, costs, no-overlap replay, result
   immutability, no-network/credential/broker access, and the strict kill rule.
5. Run a deterministic CPU smoke first, then one full CPU control only if the
   smoke passes. Keep GPU idle for this control; a non-falsified result still
   requires an independent frozen replication before any GPU or ensemble work.

## Boundaries

- No KIS calls, credentials, live route, paid data/model, public service, or
  raw-data disclosure.
- No parameter sweep, model training, checkpoint, ensemble, threshold tuning,
  Paper order, or promotion.
- Keep market data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.

## Completion

- The exact fixed contract, CPU smoke, and full control each have source-safe
  external evidence and deterministic replay tests.
- The result is categorically `falsified` or `candidate_only`; either outcome
  leaves model selection, GPU depth, ensemble, and KIS Paper routes unchanged.
- Stateboards record the exact research result and the independent intraday
  worker's recovery status without making either a global hold.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Add QQQ SPY relative regime control`
