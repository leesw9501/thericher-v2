# TheRicher v2 Handoff

Use this file as the first read for a fresh Codex task.

## Current Repository

- Repo: `leesw9501/thericher-v2`
- Local path: `C:\Users\Public\Documents\thericher-v2`
- Default branch: `main`
- Visibility: private

This repo is a clean v2 start. Do not continue v1's report/gate/operator-console
architecture here. The v1 repository may be inspected only as a reference and
parts source.

## Product Direction

TheRicher v2 is an engine-first KIS trading workstation for a single
Korea-based operator.

The main loop is:

1. collect intraday data,
2. build features,
3. run chart/ML/DL models,
4. combine signals,
5. backtest and walk-forward validate,
6. paper trade through KIS,
7. attribute results,
8. promote only proven engines to small live capital.

## Non-Negotiable Boundaries

- No KIS API calls until an explicit future goal allows it.
- No paper or live orders until an explicit future goal allows it.
- No credential reads.
- No public dashboard.
- No v1 wholesale imports.
- No report sprawl.
- No safety gate that blocks research iteration unless it is a true execution
  hard stop.

## Current Foundation

Implemented and pushed:

- engine-first charter docs,
- Python package skeleton,
- immutable core contracts using `Decimal` and UTC-aware timestamps,
- append-only JSONL event log,
- rebuildable SQLite query views,
- deterministic synthetic OHLCV,
- market data provider protocol, local CSV/sample providers, and deterministic
  timeframe resampling for `1m`, `5m`, `10m`, `1h`, and `3h`,
- simple momentum model,
- simple ensemble decision,
- next-bar backtest harness with fees and slippage,
- local-only dashboard skeleton,
- local emergency state for stop-new-orders and cancel-open-orders,
- broker-free local paper execution simulator with next-bar-open fills,
  duplicate client order id protection, emergency-stop blocking, deterministic
  cash/position replay, and local paper event logging,
- bounded model-validation harness that connects `Bar` data, a momentum model,
  ensemble decisions, and broker-free local paper execution,
- validation smoke CLI with optional explicit Yahoo intraday snapshot input and
  artifact writing outside Git,
- bounded research experiment queue that sweeps small momentum/timeframe
  variants through the validation harness and writes metrics outside Git,
- walk-forward attribution layer for the experiment queue with chronological
  windows, per-window replay metrics, PnL, and drawdown,
- GPU candidate smoke preparation artifact for the first longer research
  candidate, selected from walk-forward metrics without training or storing
  artifacts in the repo,
- research-profile GPU runtime smoke CLI that records `nvidia-smi` readiness
  and selected candidate metadata outside Git,
- research-profile GPU compute smoke CLI that runs only inside the bounded
  research path, records selected candidate metadata, and writes either
  `compute_ran_only` or non-fatal `prepared_not_trained` artifacts outside Git,
- optional GPU training smoke CLI with a tiny optimizer/gradient-step seam; it
  imports no heavy framework at module load, writes artifacts outside Git, and
  remains `prepared_not_trained` until a research-only backend is approved and
  installed,
- agent lane stateboards under `agents/`,
- daily report bundle generator,
- Dockerfile and compose services: `engine`, `web`, `research`,
- tests and lint baseline.

## Verification Baseline

The latest completed baseline passed:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Expected result:

- `59 passed`
- `All checks passed!`
- Docker compose config exits zero

## Current Architecture Decisions

Read these files before changing architecture:

- `VISION.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `DECISIONS.md`
- `RUNBOOK.md`
- `agents/README.md`
- `INTERIM_GOAL_SCRIPT.md`

Key decisions:

- JSONL is the source of truth.
- SQLite is a rebuildable query view.
- Dashboard actions are local-only until broker adapters exist.
- Base engine has no heavy runtime dependencies.
- GPU/ML work belongs in the research lane/profile.
- GPU compute and training must run through the Docker `research` target/profile
  unless an explicit future decision allows otherwise.
- GPU model artifacts belong outside the repo at
  `D:\thericher-v2\model-artifacts` by default.
- Operator-provided market data lives outside the repo at `D:\market_data`.
- Additional market data acquisition must use no-auth, lawful,
  license-compatible sources and stop when those limits are hit.
- Local paper execution fills at next completed bar open and labels simulated
  fills with `source: local_paper`.
- Long Codex tasks refresh `NEXT_CODEX_GOAL.md` before ending.
- Engine Research Agent keeps bounded GPU experiments queued by default once GPU
  research starts.
- Agent stateboards are lane queues only; `NEXT_CODEX_GOAL.md` remains the
  single next objective.
- First paper execution target is US equities through KIS.
- Korean equities are research/data-parallel at first.

## Recommended Next Slice

Approve and add the first research-only GPU compute backend, then run the first
tiny bounded training smoke with a real backend:

1. keep the base engine dependency path light,
2. install the approved backend only in the Docker `research` target/profile,
3. run the existing tiny deterministic GPU training smoke for the selected
   walk-forward candidate,
4. write all generated outputs outside Git.

Do not start with a dashboard expansion, KIS credentials, or broker submit.

## Daily Operator Review

The operator wants daily review at 08:00 KST. Keep reports to one bundle:

- `reports/daily/YYYY-MM-DD-summary.md`
- `reports/daily/YYYY-MM-DD-metrics.json`
- `reports/daily/YYYY-MM-DD-next-goal.md`

Do not create many status reports.
