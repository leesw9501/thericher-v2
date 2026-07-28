# Next Codex Goal

## Objective

Freeze and run one independent, candidate-only NAS D1 candle-state breadth
screen using the existing six-symbol private KIS historical panel. The goal is
to test a genuinely new causal OHLCV representation while keeping all outcomes
outside selection, ensemble, broker, and live paths.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattach the immutable NAS D1 panel, its source limitations, and the closed
   sequence/volatility candidate evidence before proposing a new feature or
   model family.
3. Ask Claude for a concise falsification-first check of feature availability,
   target timing, split isolation, naive baseline, and the strongest kill test.
   If local OAuth remains expired, record `review_unavailable` and continue only
   with candidate-only, non-promoting work.

## Contract

- Research owns this campaign. Data only reattests the already available D1
  OHLCV capability; Execution has no work package and no KIS/account/order
  route may be imported.
- Use only completed bars from the frozen six-symbol NAS D1 panel under
  `D:\market_data`. Every feature at decision time `t` must use bars at or
  before `t`; the inherited long-versus-flat target may use only later `t+1`
  and `t+2` references under an explicit fixed cost model.
- The new hypothesis is a per-symbol daily candle-state representation: gap,
  body-to-range, close location, range-to-prior-close, and a completed-bar
  volume-relative feature over a fixed causal window. It must not rank symbols,
  infer point-in-time universe membership, use current-listing membership as a
  feature, or blend another source.
- Freeze the dataset identity, exact feature definitions, window, split,
  normalizer fit domain, target/cost convention, naive baseline, compute budget,
  and strongest kill test before model execution.
- First run a deterministic CPU smoke. Only if its contract/tests are complete
  and CUDA is available, run one bounded network-disabled Docker CUDA breadth
  screen. Artifacts and checkpoints belong only under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- No KIS call, credential read, account read, `OrderIntent`, paper order, model
  selection, ranking, ensemble, promotion, or live behavior belongs to this
  objective. Any replay uses only in-memory `source: local_paper` fills.

## Work

1. **Data:** reattest that the frozen source-local panel has complete daily
   OHLCV fields needed by the fixed contract, recording source-safe capability
   only and no new collection.
2. **Engine Research:** implement the causal candle-state adapter and immutable
   campaign contract with a distinct model/baseline plan. Reject incomplete,
   non-finite, cross-phase, or future-dependent inputs before fitting.
3. **Validation:** add focused leakage, source-safety, artifact-root, and route
   isolation tests. The Validation role must not tune the candidate it checks.
4. **Engine Research:** run the fixed CPU smoke and, when eligible, the
   network-disabled Docker CUDA breadth screen. Retain only source-safe aggregate
   receipts and external checkpoints; classify the result without choosing a
   winner.

## Completion

- A frozen causal candle-state contract and focused validation evidence exist.
- The CPU smoke and eligible CUDA screen have reproducible source-safe receipts,
  or a precise scoped runtime recovery fact exists.
- No raw market rows, predictions, targets, credentials, broker payloads,
  orders, selection, ensemble, or live behavior are retained or created.
- Refresh the role stateboards and replace this file with exactly one next
  objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Screen NAS D1 candle-state candidates`
