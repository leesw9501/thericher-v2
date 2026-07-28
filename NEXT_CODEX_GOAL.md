# Next Codex Goal

## Objective

Freeze and CPU-smoke one distinct KIS-compatible QQQ/SPY D1
overnight-versus-intraday state hypothesis while the broad KIS D1 collector
continues independently.

Use only the existing fixed source-local QQQ/SPY daily-history pair and its
already recorded 4,756-session coverage. This is a new causal hypothesis, not
a retune or relabel of the closed linear, compact-GRU, tree, CACC, ETF trend,
relative-regime, relative-allocation, sealed NAS, or volatility-conditioned
candidate families.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach only existing source-safe fixed-pair lineage, split, and cost facts.
   Do not print market rows, returns, labels, credentials, account identifiers,
   or broker bodies.
3. Ask Claude for a concise falsification-first review before freezing the
   hypothesis contract. State its causal timestamps, naive comparators, cost
   model, split, leakage/survivorship checks, and strongest kill test.

## Authority And Boundaries

- This is offline Engine Research and temporary Validation work. Do not read
  `.env`, call KIS, submit/modify/cancel orders, access account/position/quote
  routes, enable live behavior, or expose a dashboard.
- Use only KIS-compatible daily OHLCV-derived fields available from the fixed
  pair. Do not blend Norgate, Tiingo, rankings, current-listing broad-panel
  membership, news, or unavailable higher-frequency data.
- Freeze the chronological split, after-cost long-versus-flat target, feature
  timestamps, normalizer fit range, and comparators before the CPU run. No
  threshold sweep, ensemble, model selection, Paper action, or GPU depth run
  belongs to this objective.
- Keep all generated artifacts under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`, never Git.
- The broad collector and its scheduler remain independent. Its incomplete
  current-listing panel is not a research input or a reason to hold this goal.

## Work

1. **Engine Research:** define one explicit overnight-versus-intraday state
   feature/target/split/cost contract using the fixed QQQ/SPY D1 source only.
   Make the feature values reconstructible from KIS daily OHLCV fields.
2. **Validation:** add focused causal/leakage and source-isolation tests plus
   a naive flat, always-long, and previous-bar-direction comparison contract.
3. **Engine Research:** run one bounded Docker CPU smoke only after the frozen
   contract validates. Store source-safe aggregate artifacts externally.
4. **Validation:** independently reattest the CPU artifact and reject any
   leakage, split, provenance, or route-isolation violation. A failed or weak
   result closes only this candidate.
5. Refresh stateboards, replace this file with exactly one next objective, then
   continue. A later GPU objective requires this exact CPU evidence; do not
   preempt it merely to raise utilization.

## Completion

- One frozen KIS-compatible causal contract and CPU-only source-safe artifact
  exist outside Git.
- Independent Validation records whether the contract/artifact reattests.
- No broker, credential, KIS network, Paper, live, or GPU work occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add KIS-compatible overnight state contract`
