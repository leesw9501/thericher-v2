# Next Codex Goal

## Objective

Build the first KIS-native intraday feature and candidate-breadth foundation
from the frozen QQQ 20-session source, while KIS regular-session minute coverage
continues independently for QQQ and SPY.

Produce a reproducible CPU feature/target contract and simple chronological
candidate comparisons. Once that contract exists, run one bounded Docker
PyTorch CUDA sequence-model smoke using only the same frozen source. This is
descriptive research, not a model promotion or profitability claim.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` data, account, order, modify, cancel,
  reconciliation, raw-retention, and goal-owned schedule work is authorized.
- Retain raw market data only under `D:\\market_data`; keep generated artifacts
  under `D:\\thericher-v2\\model-artifacts` or `/app/model_artifacts`; never
  put either in Git.
- Do not output or commit credentials, account identifiers, raw quote/broker
  bodies, raw order IDs, or private intent state.
- Do not read `KIS_LIVE_*`, call a live host/route, use real capital, buy data,
  accept unclear rights, or expose a public service.
- An old marker, partial data run, or unresolved distinct Paper intent never
  pauses fresh correctly scoped Paper data, schedule, account, or order work.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect the current KIS intraday indexes and the completed QQQ campaign
   manifest before selecting any new input or writing an artifact.
5. Ask Claude for a concise falsification-first check before using a CPU result
   to choose the CUDA candidate or interpreting a material outperformance.
   Never send secrets, raw rows, or broker output.

## Role-Owned Work

### Data Agent

1. Continue bounded cursor/head collection for `QQQ/NAS` and `SPY/AMS`, with
   reattested regular-session coverage and explicit gap facts. Do not mix
   providers or fill missing KIS minutes.
2. Expose one exact, hash-bound KIS-only selection for the initial QQQ feature
   contract: 20 ordered full regular sessions and their explicit `SessionWindow`
   values. Preserve the current timestamp/open-close semantics limitation.
3. Report safe coverage growth and any concrete data/source/storage issue; do
   not create a new data-quality approval gate.

### Engine Research Agent

1. Build a small feature/target contract using only completed KIS bars from the
   fixed QQQ source. Start with 90 completed 1m bars plus deterministic 5m/10m
   resamples, declared session boundaries, next-bar executable targets, and the
   existing 10 / 1 / 9 chronology. Keep 1h/3h inactive unless their full
   completed context is explicitly supported.
2. Run a CPU breadth comparison with simple deterministic/regularized candidates
   against the completed naive references. Record dataset, feature schema,
   split, costs, metrics, and replay evidence outside Git. Do not tune against
   the 9-session validation region or claim selection/profitability.
3. Once the CPU feature contract is frozen, run one bounded Docker PyTorch CUDA
   GRU/TCN-or-smaller sequence smoke with a fixed compute budget and artifacts
   under `/app/model_artifacts`. It may validate the research runtime and
   pipeline only; it cannot promote a model or consume a sealed holdout.
4. Refresh breadth, depth, ensemble, and replication queues from the evidence.
   Ensemble work requires independently generated out-of-fold predictions.

### Execution Agent

1. Keep the explicit-calendar quote-derived KIS Paper session and the data-only
   intraday head collector independent and active. Reconcile each durable
   virtual intent on its own identity.
2. Fix only concrete virtual-route, safe-projection, pacing, calendar, or
   reconciliation defects. Do not make strategy decisions or add a live route.

## Completion Evidence

- A hash-bound KIS-only feature/target contract with explicit session and
  timestamp limitations.
- CPU candidate outputs versus the fixed local-paper naive references, with no
  validation-tuning or model-promotion claim.
- One bounded Docker CUDA smoke artifact when the frozen CPU contract and GPU
  runtime are available; otherwise a precise technical cause, not a fabricated
  result.
- Continued independent KIS cache/head and Paper-session recovery facts.
- No live route, secrets, raw data, or generated artifact committed to Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add intraday feature breadth foundation`
