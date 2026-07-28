# Next Codex Goal

## Objective

Run one frozen, candidate-only sealed validation and `local_paper` attribution
package for the completed NAS D1 breadth artifacts. This should connect the
existing deterministic CPU control and 18 CUDA checkpoints to a reproducible
after-cost local simulation without selecting a winner, building an ensemble,
or sending any broker request.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattest the frozen inputs and evidence before any target is reconstructed:
   - panel dataset: `sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`
   - campaign contract: `sha256:5a9ceb6df7b6c1909ef452b8851fbd7bd23ec03660e9fc75bb278377079aaea5`
   - campaign precommit: `sha256:c54e795b3fb2caa76c9367a72aadc1c0ac685241bd5c59e2e12bdb0af603d37e`
   - CPU breadth summary: `sha256:4bfb8448a61cd741e63b12ab71fb58511be3700c936450286b2257b619067196`
   - CUDA breadth summary: `sha256:43a4f91c96cf2a081e7c53fc2ab7fa93c03bf7d7beee0f8b2524f9aa37492ed7`
3. Before opening or interpreting the sealed validation target, ask Claude for
   the required concise falsification-first review. If local OAuth is still
   expired, record `review_unavailable` and continue only this non-promoting,
   no-cost candidate evaluation; do not treat the unavailable review as a
   result endorsement.

## Frozen Evaluation Contract

- Use only `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA` from the
  source-local current NAS panel and the exact `1,510 / 22 / 647` phase split.
- Refit the six CPU L2-logistic controls deterministically and require their
  parameter hashes to match the CPU receipt. Load each GPU checkpoint only with
  `weights_only=True` and require its architecture, standardizer, and campaign
  lineage to match the CUDA receipt.
- Reconstruct validation targets only in memory using the already frozen
  `t+1` open to `t+2` open, one-share, 1 bps fee and 2 bps per-fill slippage
  semantics. Never write labels, prices, feature rows, prediction vectors, or
  per-decision outputs.
- On every other chronological validation sample, map probability `>= 0.5` to
  one long share and lower probability to flat. Use the existing fixed `flat`,
  `always_long`, and `previous_bar_direction` comparators on the same
  non-overlapping two-session slots. All simulated fills must retain
  `source: local_paper`.
- Treat the 24 fixed candidates independently. The package may report only
  aggregate classification and after-cost attribution facts per candidate. It
  may not rank, choose, retune, ensemble, promote, or create a Paper order.

## Work

1. **Validation:** build a sealed evaluator that owns validation-target
   reconstruction and refuses unpinned source, checkpoint, CPU-model, split,
   threshold, or comparator drift.
2. **Engine Research:** implement the deterministic CPU re-fit and CUDA
   checkpoint inference adapters, then run the 24 fixed candidate evaluations
   through the broker-free local paper simulator.
3. **Review:** use a temporary independent Validation role to verify target
   isolation, no-tuning behavior, `local_paper` fills, source-safe external
   receipts, and no KIS/network/credential/broker route.
4. **Artifacts:** write immutable source-safe precommit and result receipts only
   under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`. Keep
   checkpoints outside Git and do not create a report or gate family.

## Boundaries

- No KIS call, `.env` or credential read, provider download, paid asset, public
  service, account/quote/order route, live behavior, or broker submission.
- No parameter sweep, threshold tuning, winner selection, ensemble, model
  promotion, KIS Paper action, or live capital claim.
- Do not modify the source panel, feature window, phase split, target/cost
  semantics, candidate architectures, seeds, or source limitations.

## Completion

- All 24 fixed candidates either have a source-safe independent result or an
  exact bounded failure receipt with no incomplete output.
- Every retained replay fill is locally reconstructable with `source: local_paper`.
- Validation targets and per-decision values never leave process memory.
- Refresh stateboards and replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Evaluate sealed NAS D1 breadth candidates`
