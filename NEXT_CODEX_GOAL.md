# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run `kis-d1-causal-representation-feasibility-v1`: one bounded,
offline Engine Research campaign that proves a single causal TCN can consume
the existing KIS-shaped completed daily-bar input, train reproducibly in the
Docker research runtime, and keep its generated weights outside Git.

This is real model-engineering work, but it is not an alpha, forecasting,
profitability, PnL, ranking, ensemble, Paper-input, order, account, or live
claim. Its result is only a reproducible causal representation/runtime fact for
one frozen source-local input.

## Frozen Contract

- Reattest only `load_kis_paper_daily_history_sequence_input` against
  `kis.paper.private.daily.nas.history.panel-v1` and exact dataset hash
  `sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`.
  Use only its six-symbol completed-D1 development phase (`1,510` common
  sessions): `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA`. The purge and
  validation phases may be reattested by the existing loader but must not be
  materialized into model examples or used for model selection.
- Derive one in-memory, causal `32`-session feature window per symbol from
  completed bars only. The fixed features are close-to-prior-close log return,
  high-to-open log ratio, low-to-open log ratio, close-to-open log ratio, and
  log volume change. Normalize from the predeclared training prefix only; do
  not persist feature values or raw bars.
- The self-supervised task masks the final `4` feature rows of each input
  window. The causal TCN receives only the preceding visible rows plus an
  explicit mask channel and reconstructs the masked rows. Targets are used
  solely in-memory for optimization; they are not trade labels, predictions,
  scores, or a backtest target.
- Use one fixed architecture: three causal dilated TCN blocks, `32` hidden
  channels, kernel size `3`, seed `20260802`, AdamW learning rate `0.001`,
  weight decay `0.0001`, batch size `256`, and at most `192` optimizer steps.
  Do not add an architecture matrix, window sweep, threshold sweep, model
  selection, or ensemble.
- Freeze one internal development-only geometry before target access: the
  earliest `1,000` development sessions supply normalization and training
  examples; the next `32` sessions are unused purge; the remaining development
  sessions supply a diagnostic reconstruction pass only. A finite diagnostic
  loss is a runtime fact, not a score or comparison result.
- Run a four-step CPU smoke first. If it passes and Docker CUDA is available,
  run exactly one bounded CUDA job under the existing `research` Compose
  service. If CUDA is unavailable, emit `runtime_unavailable`; do not fake a
  GPU result or extend/retry indefinitely. Stop a CUDA job at `192` steps or
  five minutes, whichever comes first.
- Write one immutable campaign contract, CPU receipt, CUDA-or-unavailable
  receipt, and safe non-pickle `.npz` weight artifact only under
  `D:\thericher-v2\model-artifacts\research\kis-d1-causal-representation-feasibility-v1`.
  Receipts may contain hashes, shapes, architecture identity, device category,
  step counts, and categorical finite/decreased-loss facts, but no raw bars,
  dates, prices, features, targets, predictions, numeric losses, PnL,
  credentials, account data, or broker payloads.

## Boundaries

- Do not call KIS, Norgate, Tiingo, or any network provider; read no `.env` or
  credentials.
- Do not access accounts, positions, orders, local-paper, brokers, or live
  behavior. Do not make this model available to Execution or Paper work.
- Do not use the historical KIS validation phase, prior candidate outputs,
  cross-source data, or a previously closed validation slice to choose any
  design or report an advantage.
- Do not add a generic training framework, scheduler, dashboard, public model
  dependency, or runtime replacement. Reuse the existing Docker research
  image and lazy PyTorch import boundary.
- Do not write raw data, model artifacts, or generated receipts to Git.

## Required Work

1. Engine Research: implement the fixed loader-to-causal-TCN campaign, safe
   serialization, and runner. Keep the module small and import-pure until its
   run function is invoked.
2. Research Steward: freeze the external campaign custody record before the
   CUDA appointment and close it with its categorical result. GPU work is
   justified only by the frozen contract above, not utilization alone.
3. Validation: add focused tests for source reattestation, causal masking,
   training-prefix normalization, phase exclusion, deterministic CPU smoke,
   CUDA-unavailable handling, external artifact containment/immutability, safe
   serialization, and absence of credential/network/KIS/broker/Paper/live
   access.
4. Run the CPU smoke and, when available, the bounded Docker CUDA run. Update
   only the relevant stateboards, handoff, decisions, and orchestration with
   source-safe categorical evidence. Record the next distinct CPU rule
   candidate as a one-line Engine queue item; do not implement it in this
   objective.

## Claude Context

Claude's new recommendation was an additional KIS/Norgate adjustment
reconciliation. Codex does not select it first because the immediately prior
goal already completed a narrower direct conformance test and this company
objective is explicitly engine development. Temporary Validation instead
recommended this causal self-supervised feasibility campaign as
`supported-with-limits`: it uses a new non-promoting task, avoids reusing
historical validation targets, and has a clear runtime/artifact kill test.
The campaign remains non-promoting even if CPU and CUDA both complete.

## Verification

```powershell
uv run --extra dev pytest -q <focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

## Completion

Report the frozen causal contract, CPU/CUDA categorical outcomes, artifact
hashes and root, tests, commit hash, intentional omissions, and the next
recommended objective. Replace this file with exactly one next objective only
after completion evidence is committed and pushed.
