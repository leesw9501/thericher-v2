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
- research-only PyTorch CUDA backend in the Docker `research` target
  (`torch==2.7.0+cu128` from the PyTorch CUDA 12.8 wheel index), with a tiny GPU
  training smoke that completed on the RTX 4090 and writes outside Git,
- lightweight Engine Research job runner CLI that executes one bounded
  `gpu_training_smoke` job at a time inside Docker `research`, writes a wrapper
  job artifact outside Git, and keeps `agents/*.md` as stateboards rather than
  autonomous workers,
- bounded GPU candidate training job kind in the research job runner; it
  consumes selected candidate metadata plus deterministic/sample or explicit
  local bars, trains a tiny PyTorch model under strict caps in Docker
  `research`, and writes metrics/model artifacts outside Git,
- bounded candidate evaluation job kind in the research job runner; it consumes
  external training metrics/model artifacts, reuses the training feature shape,
  runs PyTorch inference lazily inside Docker `research`, records baseline
  classification metrics, and writes evaluation artifacts outside Git,
- bounded candidate local-paper replay job kind in the research job runner; it
  consumes external training/evaluation artifacts, maps candidate probabilities
  into descriptive buy/sell/hold thresholds, runs only the broker-free local
  paper simulator, keeps simulated fills labeled `source: local_paper`, and
  writes replay/PnL attribution artifacts outside Git,
- bounded candidate replay comparison job kind in the research job runner; it
  consumes or runs candidate local-paper replay, runs a gap-tolerant momentum
  baseline through the same broker-free local paper simulator on the same bars,
  compares trades, PnL, drawdown, final position, fill count, and event count,
  and writes descriptive comparison artifacts outside Git,
- bounded candidate probability trace and threshold sweep job kind in the
  research job runner; it runs candidate probability inference once, persists
  an aligned per-example trace outside Git, replays a small buy/sell threshold
  grid through local paper without rerunning inference, compares each variant
  to the existing momentum baseline metrics, and keeps output descriptive,
- bounded threshold robustness replay job kind in the research job runner; it
  reuses the threshold sweep trace and local-paper replay primitives across a
  capped set of local Yahoo slices, records per-slice PnL, drawdown, fill
  counts, and final positions, and keeps output descriptive rather than
  promotional,
- bounded multi-slice candidate training and evaluation input; candidate
  training/evaluation can now consume explicit local Yahoo `(snapshot, symbol)`
  slices, preserve the existing four-feature shape, record per-slice row counts
  and provenance, and write model/evaluation artifacts outside Git,
- bounded multi-slice probability calibration probe; it derives a small
  deterministic threshold grid from observed candidate probability quantiles,
  replays that grid through the existing threshold robustness/local-paper path,
  writes descriptive artifacts outside Git, and records no best threshold,
  promotion, or pass/fail gate,
- bounded calibration holdout replay; it consumes the calibration threshold
  grid unchanged, runs bounded holdout traces on the disjoint
  `snapshot=2026-06-18` CVS, FCX, and KO slices, replays through the existing
  threshold robustness/local-paper path, verifies fill sources, and keeps the
  result descriptive,
- bounded real-data candidate breadth queue; it defines three nearby
  `m1_lb*_b10_s10` candidate variants, writes candidate metadata outside Git,
  runs each variant through the existing bounded training/evaluation primitives
  in Docker `research` under strict caps, and records descriptive
  probability/evaluation summaries without a winner, recommendation, or
  promotion gate,
- bounded breadth holdout bridge; it consumes the external breadth queue
  artifact, reuses the existing threshold calibration, robustness replay, and
  threshold holdout primitives for each queued candidate, verifies disjoint
  holdout local-paper fills remain `source: local_paper`, and records
  candidate-by-candidate probability/PnL/drawdown evidence without a winner,
  recommendation, or promotion gate,
- bounded depth target; it consumes the external breadth holdout artifact,
  selects at most one completed candidate with a deterministic
  `research_scheduling_only` heuristic, retrains/evaluates/calibrates/holdout
  replays the chosen candidate in Docker `research` with PyTorch CUDA under
  deeper but still capped limits, and records probability/PnL/drawdown/fill
  source evidence without a winner, recommendation, or promotion gate,
- bounded depth-vs-breadth comparison; it consumes the external depth target
  and breadth holdout artifacts, compares only the selected candidate's
  pre-depth holdout evidence against the deeper training evidence, records
  probability/fill/PnL/drawdown/cap/data-slice deltas, and stays
  `research_comparison_only` with no winner, recommendation, pass/fail result,
  or promotion gate,
- bounded comparison-informed fill-aware threshold rerun; it consumes the
  external depth comparison and depth target artifacts, derives a capped
  stricter threshold grid for the selected candidate, replays existing holdout
  slices through the proven local-paper path, and stays
  `research_threshold_rerun_only` with no winner, recommendation, pass/fail
  result, scheduler, or promotion gate,
- bounded zero-fill threshold attribution; it consumes the external threshold
  rerun, robustness, calibration, and probability trace artifacts only, records
  per-slice/per-threshold opportunity counts and local-paper fill counts, and
  explains the strict grid as above the observed buy-probability range without
  rerunning training, selecting a winner, or adding a promotion gate,
- bounded attribution-informed threshold band rerun; it consumes the external
  attribution artifact, derives a capped source-calibration band inside the
  observed probability range, replays existing holdout traces through the
  proven local-paper path, records `247` local-paper fills across 12 variants,
  and closes the threshold-only loop as descriptive evidence rather than a
  model-quality decision,
- bounded feature-branch replay attribution; it consumes the external
  `core_plus_bar_position_v1` feature-branch artifacts, derives a capped
  replay band from feature-branch probability evidence, reuses the existing
  robustness/local-paper path, records PnL/drawdown/fill attribution, and
  verifies all generated fills remain `source: local_paper`,
- local-paper holdout source verification now treats missing event files for
  zero-fill replay variants as empty evidence rather than a non-local fill
  failure, while still failing unreadable artifacts for variants with fills,
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

- `195 passed`
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
- PyTorch CUDA is approved only for the Docker `research` target/profile. Keep
  it out of the base engine and local dev/test dependency path.
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

Add broker-safe local-paper source-filtered attribution views:

1. keep local-paper fills queryable separately before broker fills exist,
2. add source filtering around replay/query attribution helpers,
3. prove mixed-source or missing-source data cannot be mistaken for local paper,
4. avoid KIS, credential, live/paper broker submit, dashboard expansion, or
   scheduler work.

Do not start with a dashboard expansion, KIS credentials, or broker submit.

## Daily Operator Review

The operator wants daily review at 08:00 KST. Keep reports to one bundle:

- `reports/daily/YYYY-MM-DD-summary.md`
- `reports/daily/YYYY-MM-DD-metrics.json`
- `reports/daily/YYYY-MM-DD-next-goal.md`

Do not create many status reports.
