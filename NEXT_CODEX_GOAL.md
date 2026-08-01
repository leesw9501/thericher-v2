# Next Codex Goal

## Objective

Build one bounded, source-local Tiingo D1 sequence-model breadth campaign for
SPY, QQQ, and IWM.

The campaign must test a distinct causal hypothesis from the completed simple
trailing-momentum control: short completed-D1 OHLCV sequences may carry
conditional next-session intraday-direction information. It is offline research
only and must not select a model, create an ensemble, claim profitability, or
become a KIS Paper/runtime input.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Data, Engine Research, Research Steward, and orchestration stateboards.
2. Reattach the immutable Tiingo D1 snapshot
   `D:\market_data\us_equities\tiingo_etf_daily\canonical\snapshot=20260801T173121Z-tiingo-etf-d1-r1`
   without reading `.env`, making network calls, or using KIS/Norgate data.
3. Ask Claude for a short falsification-first challenge before freezing the
   feature timestamp, target, event/discontinuity scope, chronological split,
   cost band, or GPU eligibility rule. Do not send raw rows, credentials, or
   target values to Claude.

## Work

1. **Data / Engine Research:** implement one pure raw-D1 sequence input builder
   for exactly SPY, QQQ, and IWM. It must consume only the verified Tiingo
   snapshot, use completed feature rows through `t`, derive a fixed short
   sequence of raw-OHLCV-derived normalized features, and label only the next
   session's open-to-close direction. Keep all provider rows in memory or D:;
   write no raw values, per-row labels, predictions, or checkpoints to Git.
2. **Engine Research:** freeze one chronological development/purge/validation
   contract before outcomes are read. It must use a finite fixed sequence-window
   menu, the existing raw event semantics, feature-side-only discontinuity rule,
   fixed `5/10/20`-bp round-trip cost band, naive comparator, minimum effective
   sample rule, structural leakage kill test, deterministic seed, and explicit
   compute stop rule. Do not reuse the completed momentum result to choose a
   window or threshold.
3. **Engine Research:** run a deterministic CPU smoke with a naive baseline and
   one small classical sequence-aware control. If the frozen eligibility rule is
   met, hand exactly one bounded GPU appointment to Research Steward for a
   fixed breadth batch of small GRU, causal-TCN, and compact-attention models.
   Use PyTorch CUDA only when available; persist safe numeric artifacts only
   under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
4. **Research Steward:** record source-safe campaign lineage, the GPU
   appointment or categorical ineligibility, exact compute stop result, and
   no sealed-evaluation allocation. GPU idleness must not itself create another
   training job.
5. **Validation:** independently reattach the precommit/summary and verify
   source separation, chronological causality, no network/credential/KIS/broker
   path, external artifact location, and no promotion/ensemble/Paper output.
6. Update the Data, Engine Research, Research Steward, and orchestration
   stateboards with aggregate-only evidence and one exact next recovery fact.
   Do not add a dashboard, report family, durable worker, new data-provider
   call, or a new approval gate.

## Completion

- The immutable Tiingo snapshot is verified and remains source-local.
- A CPU sequence baseline is complete, `no_structure`, or `input_unavailable`.
- A bounded CUDA breadth batch is completed only when its frozen eligibility
  rule is met; otherwise the source-safe reason is recorded.
- No KIS Paper/live call, credential read, order, data blend, model selection,
  ensemble, profitability claim, or Paper action occurs.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. Any external-job wait remains lane-local.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add Tiingo D1 sequence campaign foundation`
