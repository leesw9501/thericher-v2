# Next Codex Goal

Continue TheRicher v2 from `C:\Users\Public\Documents\thericher-v2`.

## Objective

Deliver the first coordinated Data, Engine Research, and Execution readiness
increment for an honest local model campaign and a future KIS paper loop.

The company outcome is one catalog-backed, executable-target validation path
plus broker-neutral execution contracts. The three durable lanes should advance
ready, non-conflicting work in parallel. Data correctness outranks GPU use, and
no lane should wait merely because another lane is still running.

This advances data collection, feature/model research, backtest and
walk-forward validation, paper-trading readiness, and PnL attribution.

## Start

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read the files printed by the script, beginning with `HANDOFF.md` and this
   goal.
3. Act as the Codex Orchestrator. Assign bounded work to the Data, Engine
   Research, and Execution roles; use temporary independent Validation after
   contracts are frozen.
4. Ask Claude for a concise falsification review only at the bias-prone
   boundaries defined in `AGENTS.md`. Claude is advisory and does not stop
   unrelated safe work.

## Hard Boundaries

- Do not read credentials, `.env`, account identifiers, or secret-like files.
- Do not call KIS or another broker, query an account, or submit paper/live
  orders.
- Do not enable `kis_paper` or `kis_live`.
- Keep existing broker-free fills labeled `source: local_paper`.
- Do not buy data, models, services, or dependencies.
- Store market data only under `D:\market_data` and generated artifacts only
  under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Check `D:` capacity before acquisition; warn below 20 percent free and stop
  before autonomous work would cross 15 percent free.
- Do not create a scheduler, daemon, coordinator, general agent platform,
  public dashboard, new durable role, report family, or promotion bureaucracy.
- Do not import v1 wholesale or load arbitrary model code in Execution.
- Do not claim profitability or promote a model from this increment.

## Parallel Work Packages

### Data Agent

1. Build one compact training-readiness catalog for the three exact intraday
   files listed in `HANDOFF.md` and a bounded sample/inventory of the existing
   daily universe.
2. Record file lineage, schema, symbols, sessions, timestamp ordering,
   duplicates, critical nulls, OHLCV invariants, interval gaps, overlap, and
   candidate split eligibility.
3. For daily candidates, make adjustment, corporate-action, ordering, range,
   and point-in-time limitations explicit before model-input use.
4. Acquire additional data only when it is no-auth, no-cost, lawful,
   license-compatible, bounded, and directly closes a catalog gap. Deduplicate
   it and write it to `D:`. Stop when no useful approved source remains.
5. Write one external machine-readable artifact and update `agents/data.md`
   with the exact readiness result and any concrete operator request.

### Engine Research Agent

1. Define one structured campaign contract that consumes the Data-owned
   catalog. It must freeze:
   - an executable entry/exit and target aligned with local-paper fill timing,
   - strictly forward, non-overlapping development/validation windows,
   - a sealed final holdout that is not used for tuning,
   - fees, nonzero slippage assumptions, and after-cost PnL attribution,
   - naive baselines and stable dataset/evidence identifiers.
2. Connect the existing validation harness to that contract without adding a
   parallel research job family.
3. Run a deterministic CPU baseline first. Treat all old short-intraday results
   as development evidence, never as ranking or promotion evidence.
4. Only if Data marks the campaign inputs eligible and the contract is frozen,
   run one bounded breadth experiment in Docker with PyTorch CUDA. Keep all
   outputs external. Otherwise record the precise blocker and prepare the next
   CPU-side hypothesis without pretending that GPU utilization is progress.
5. Keep breadth and depth queues visible in `agents/engine-research.md`; do not
   move a candidate into depth without the required Claude challenge.

### Execution Agent

1. Add the smallest typed, broker-neutral contracts needed for later KIS paper:
   account/buying-power snapshot, order intent/request, acknowledgement and
   status, partial fill, cancellation, open orders, and reconciliation result.
2. Prove lifecycle behavior with a deterministic fake transport. Cover
   persisted intent before side effects, idempotent retry, partial fills,
   cancellation, unknown outcomes, and reconciliation.
3. Keep all real broker transports disabled. Do not add KIS endpoints,
   credentials, account queries, or strategy logic.
4. Preserve current local-paper replay and source semantics unless a focused
   compatibility fix is required and tested.

### Validation Agent

1. Freeze Data, Research, and Execution contracts before independent checks.
2. Validation must not tune the candidate it evaluates. Test timestamp/target
   alignment, split non-overlap, sealed-holdout behavior, after-cost accounting,
   artifact placement, and broker/network/credential independence.
3. Return bounded findings and evidence identifiers to Codex, then exit.

### Codex Orchestrator

1. Reuse current event/artifact primitives for lineage. Add only the minimum
   shared recovery record needed by this objective; do not build a worker
   platform or duplicate evidence into Markdown.
2. Run a simplification review before integration. Remove wrappers, reports,
   gates, and abstractions that do not directly improve an engine loop.
3. Resolve cross-role contract conflicts and integrate only evidence-backed
   outputs.
4. Update concise stateboards and `HANDOFF.md`, refresh this file with the next
   single company objective, then commit and push.

## Claude Challenge Points

Use the falsification prompt in `AGENTS.md` before relying on:

- the frozen dataset/split/target contract if leakage or survivorship choices
  are material,
- any unexpectedly strong result,
- any breadth-to-depth or ensemble selection,
- a major dependency/runtime or durable-worker expansion.

Request one verdict: `unsupported`, `uncertain`, or
`supported-with-limits`. Do not send secrets, account identifiers, raw sealed
labels, or unnecessary rows. Routine coding, tests, formatting, and known-file
catalog mechanics do not need Claude.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report focused Data, CPU baseline, fake-transport, Validation, and optional
Docker/CUDA commands. Verify generated artifacts are outside Git.

## Suggested Commit Message

`Build parallel engine readiness increment`

## Completion Report

Report changed files, role agents used, tests, commit and push hash, data found
or acquired, remaining operator data requests, CPU/GPU work and artifact paths,
execution readiness, Claude verdicts and resolutions, intentionally omitted
work, and the next recommended company objective.
