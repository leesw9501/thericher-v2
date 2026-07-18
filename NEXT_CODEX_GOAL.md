# Next Codex Goal

## Objective

Build one compact, reproducible PnL-attribution view for the completed
development-only explicit-event replay `raw-d1-explicit-events-20260718-r3`.

This advances PnL attribution. It must explain local-paper trade, cost, and
realized-PnL evidence without making a model-selection or profitability claim.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
`VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
`agents/README.md`, and the Data, Engine Research, Execution, and Review
stateboards.

## Authority And Boundaries

- Use only immutable local data and artifacts already under `D:\market_data`
  and `D:\thericher-v2\model-artifacts`.
- Do not read `.env`, call a network API, access KIS, acquire data, submit an
  order, change `THERICHER_MODE`, or use live credentials.
- Do not retrain, use CUDA, create new candidates, change checkpoints, rank,
  select, promote, or claim profitability.
- Keep source artifacts immutable; write at most one new external attribution
  artifact under `D:\thericher-v2\model-artifacts`.
- Preserve `source: local_paper`, the r3 summary hash
  `sha256:3cac5f0b14e602c6a0043bb141fa7d6add1ca02b8ab4e214145443a1d8711609`,
  and the parent `unsupported` verdict.

## Required Work

1. Engine Research owns a small read-only consumer of r3 summary/event evidence
   that aggregates realized PnL, fees, slippage, trade counts, and flat-ending
   state by fixed cell. It must verify referenced external artifact hashes.
2. Data independently confirms the attribution reads the pinned r2 and Tiingo
   lineage only, without rewriting snapshots or interpreting adjusted fields.
3. Review checks that the result remains a single evidence artifact rather than
   a dashboard, report family, gate, scheduler, or promotion mechanism.
4. Add focused tests for local-only operation, artifact hash failure, immutable
   source handling, and no broker/credential/network path.
5. Refresh stateboards, `HANDOFF.md`, and this next single goal; verify, commit,
   and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

Report the external attribution artifact hash, data lineage checked, tests,
commit/push result, intentionally omitted work, and the next recommended goal.

## Suggested Commit Message

`Add explicit-event replay attribution`
