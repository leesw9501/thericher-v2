# Next Codex Goal

## Objective

Build the bounded offline consumer for the already precommitted
`kis-intraday-prospective-head-observation-r1` contract. It must accept only a
verified external first-five preparation pair and the fixed KIS-native
historical-development prefix, create one immutable frozen-model receipt, and
produce one replayable local-paper observation per selected prospective QQQ
session. The implementation and synthetic proof may be completed now, but no
real consumer run may begin until the existing head collector has produced the
verified preparation pair.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/orchestration.md`
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/review.md`

3. Ask Claude for a short falsification-first drift-check before defining the
   frozen-model receipt or opening the first prospective receipt. Do not send
   credentials, raw bars, cache paths, or artifact contents.

## Hard Boundaries

- Use the fixed first-five chronological-session contract unchanged: 90
  completed 1m / 18 completed 5m / 9 completed 10m inputs, next-open/following-
  open long-only timing, and the declared 1 bp plus 2 bps cost model. Do not
  retune features, alter splits, inspect a burned region, select an ensemble,
  or promote a model.
- The consumer must verify the precommit/planning pair's hashes, contract,
  selected dates, and selected-row fingerprint identity before it reads any
  cache data. Missing, malformed, changed, or unready preparation is a scoped
  pending/unavailable result with no artifact overwrite.
- Train only the fixed regularized-linear control on the ten historical
  development sessions named by the contract. Store its deterministic frozen
  model receipt outside Git. Do not use GPU, external weights, a new dependency,
  a network call, credential, or KIS route.
- Evaluate only the selected five prospective sessions with `flat`,
  `always_long`, `previous_bar_direction`, and the frozen regularized-linear
  control through the existing local-paper simulator. Every fill remains
  `source: local_paper`; no broker order, account route, decision dashboard, or
  paper capital action is allowed.
- Generated receipts and any runtime evidence stay under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`, never Git. Do
  not expose raw rows, prices, secrets, account facts, or order identifiers.
- `KIS_LIVE_*` remains unavailable. The implementation's synthetic proof is
  offline; a real run uses no KIS call because it consumes only existing cache
  data and the verified preparation pair.

## Role-Owned Work

### Data Agent

1. Specify and test the smallest verified offline read boundary from the
   existing head cache plus preparation pair to the consumer.
2. Preserve cache/index semantics and make source/selection mismatch fail
   before consumer artifact creation.

### Engine Research Agent

1. Implement the deterministic frozen regularized-linear control and its
   receipt against only the named historical development prefix.
2. Implement the five-session local-paper observation and aggregate summary
   without creating a selection, promotion, ensemble, GPU, or broker result.

### Validation Agent

1. Use synthetic cache and receipt fixtures to prove unready rejection,
   receipt/pair tamper rejection, deterministic frozen-model reuse, replayable
   `local_paper` fills, and no artifact on failed verification.
2. Prove the consumer has no KIS/network/credential/order/GPU access and that
   it does not cross the fixed historical/prospective boundary.

## Completion Evidence

- Synthetic tests prove that only a valid preparation pair can start a run,
  the frozen receipt is deterministic and reusable, each selected session's
  local-paper event is replayable, and a malformed input writes no final
  artifact.
- A focused offline smoke demonstrates the no-network/no-credential/no-order
  path. No real run occurs before a valid external preparation pair exists.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add prospective intraday observation consumer`
