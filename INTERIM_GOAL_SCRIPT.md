# Interim Goal Script

Use this goal until the operator provides the formal long-run v2 goal script.

## Mission

Prepare TheRicher v2 for engine-first development without recreating the v1
gate/report sprawl.

The work should make the next formal goal easier to execute by creating a small,
testable, Docker-ready foundation for:

- market data,
- feature generation,
- model signals,
- ensemble decisions,
- backtesting,
- state/event logging,
- dashboard monitoring,
- daily operator review.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders.
- Do not read real credentials.
- Do not expose a public dashboard.
- Do not import large v1 modules wholesale.
- Do not create many generated reports.
- Do not add safety gates that block research or paper iteration unless they are
  execution hard stops.

Allowed v1 usage:

- inspect v1 for reusable ideas,
- copy only tiny, well-understood functions after documenting why,
- prefer fresh v2 interfaces over compatibility with v1.

## Collaboration Rule

Before making architecture-changing implementation decisions, ask Claude CLI for
a concise review. Use Claude as a drift brake, not as an implementation owner.

Record accepted decisions in `DECISIONS.md`.

## Work Plan

### 1. Repo Hygiene

Create or verify:

- `pyproject.toml`,
- package layout under `src/thericher_v2`,
- test layout under `tests`,
- lightweight lint/test commands,
- `.gitattributes` for consistent text files,
- a dependency strategy that does not bloat the runtime image.

Keep dependencies minimal. Heavy ML dependencies belong in the research Docker
profile, not the base engine.

### 2. Core Contracts

Create small dataclasses or typed models for:

- `Bar`,
- `Timeframe`,
- `Signal`,
- `ModelPrediction`,
- `EnsembleDecision`,
- `OrderIntent`,
- `PositionSnapshot`,
- `PortfolioSnapshot`,
- `RiskLimits`,
- `EmergencyState`.

These contracts should be simple enough to understand in one screen.

### 3. State Foundation

Implement a minimal state layer:

- SQLite schema bootstrap,
- append-only JSONL event writer,
- replay/read helpers,
- tests proving events can reconstruct simple positions and decisions.

Do not overbuild migrations yet. Use a simple schema version table.

### 4. Research Skeleton

Add a minimal research path that can run without broker access:

- synthetic/sample OHLCV data loader,
- one trivial technical model,
- one ensemble decision function,
- one tiny backtest loop with fees/slippage parameters,
- tests for deterministic output.

This is not the final strategy. It is a harness to prevent architecture drift.

### 5. Docker Foundation

Create a minimal Docker/Compose setup:

- `engine` service for CPU runtime,
- `web` service placeholder for dashboard/API,
- `research` profile for GPU-capable experiments.

Do not require GPU for normal tests or engine startup.

### 6. Dashboard Boundary

Create only a skeleton if time allows:

- authenticated local/LAN dashboard plan,
- read model for mode, heartbeat, holdings, orders, predictions,
- two planned write actions: stop new orders and cancel open orders.

No real broker actions yet. Emergency actions should write local state only
until execution adapters exist.

### 7. Daily Review System

Create a first daily report generator that writes one daily bundle:

- `reports/daily/YYYY-MM-DD-summary.md`,
- `reports/daily/YYYY-MM-DD-metrics.json`,
- `reports/daily/YYYY-MM-DD-next-goal.md`.

The generator should summarize repository status, completed work, tests, open
decisions, and recommended next goal. It should not create many side reports.

## Verification

Before stopping:

- run the test suite,
- run formatting/lint if configured,
- verify no ignored secret-like files are staged,
- verify git status is clean after commit/push,
- push to `origin/main` or a clearly named branch if main protection is later
  enabled.

## Final Report To Operator

Keep the final report concise:

- what was built,
- what was intentionally not built,
- tests run,
- repo/branch/commit,
- next recommended formal goal script outline.

## Drift Checks

Stop and simplify if any of these happen:

- more docs than code are being added after the initial skeleton,
- a report exists only because another report expects it,
- paper trading is blocked by research-quality metadata,
- the dashboard starts becoming a command center,
- ML exploration changes execution safety behavior,
- v1 compatibility starts dictating v2 architecture.
