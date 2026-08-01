# Next Codex Goal

## Objective

Build one small, date-indexed Norgate D1 pilot from the qualified local
capability receipt.

The pilot replaces the old static-universe assumption for exactly three frozen
source cases. It is Data-led and remains
`norgate_trial_daily_offline_research_only`: it may validate date-indexed
membership handling and a KIS-shaped completed-D1 loader, but it must not make
a model, ranking, GPU, PnL, broker, or Paper claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattach the qualified Norgate capability receipt
   `sha256:8a6433a5...ae1d908d` and its consumer outline. Do not reinterpret
   qualification as point-in-time availability or a model input.
3. Ask Claude for a short falsification-first drift check before relying on the
   date-indexed membership interpretation or creating the pilot contract. A
   timeout is `review_unavailable`, not support or a hold.

## Work

1. **Data:** use only the local Windows Norgate runtime and the three frozen
   AAPL/PLTR/AAL cases. Write a fresh immutable precommit before source reads,
   then materialize raw D1 and per-date membership/listing evidence only under
   `D:\market_data`. Keep membership rows separate from OHLCV rows and bind the
   Norgate package plus database metadata fingerprint. Do not use a full union,
   network provider, credential, KIS, broker, Docker provider, or paid source.
2. **Data:** create a hash-attested external manifest with per-case aggregate
   coverage, source limitations, and an explicit `offline_research_only` scope.
   Preserve raw rows only under `D:`. Vendor availability time, adjustment
   semantics, and capital-event completeness remain `unknown` unless directly
   established by the source. A missing/contradictory source field is
   `unqualified` or `input_unavailable`, never a silent fallback.
3. **Engine Research:** add only a pure loader/adapter that consumes the
   attested pilot as completed D1 `Bar` data and exposes membership state at the
   declared source date. It must reject static-current-listing substitution and
   source/date misalignment. It may reattach the existing consumer outline but
   may not train, score, rank, tune, allocate GPU, create an ensemble, write a
   model artifact, or form a Paper intent.
4. Add focused tests proving host-only/lazy Norgate import, D:/Git isolation,
   precommit-before-source ordering, date-indexed membership rather than static
   selection, raw-row omission from manifests, and rejection of any model or
   Paper route.
5. Record the pilot result and one next recovery fact in Data/Engine stateboards
   without creating a report family, approval gate, or durable sub-agent.

## Completion

- One external pilot is `qualified_for_offline_research`, `unqualified`, or
  `input_unavailable`, with its source limits explicit.
- No raw row, credential, model artifact, KIS call, broker order, GPU job,
  model result, ranking, PnL, or Paper behavior enters Git or this goal result.
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

`Add Norgate daily capability probe`
