# Runbook

## Modes

The engine supports three modes:

- `off`: collect data and run research only. No order placement.
- `paper`: KIS paper trading allowed within risk limits.
- `live`: live trading allowed only after explicit promotion and capital caps.

Default mode is `off`.

## Long Task Workflow

Start each long Codex task with:

```powershell
.\scripts\start_next_codex_task.ps1
```

Then read the required handoff and architecture files printed by the script.
Before changing architecture, promotion rules, or agent governance, ask Claude
CLI for a short drift-check and judge it against `HANDOFF.md`,
`ARCHITECTURE.md`, and `DECISIONS.md`.

Before ending a long task:

- run the relevant verification commands,
- commit and push completed work when changes are ready,
- refresh `NEXT_CODEX_GOAL.md` with the next single objective,
- keep the next goal tied to one engine loop.

When GPU research is active, keep bounded training and validation jobs running
on the single GPU by default. Other lanes may proceed while those jobs run, as
long as they do not touch the same ownership boundary or enable broker/live
behavior prematurely.

## Emergency Stop

There are two independent emergency actions.

### Stop New Orders

Effect:

- prevents new orders,
- persists across engine restart,
- does not automatically cancel existing open orders.

Resume requires explicit local confirmation.

### Cancel Open Orders

Effect:

- asks the broker adapter to cancel currently open orders,
- logs every cancel request and result,
- does not resume new order placement.

This action is separate from stop-new-orders so the operator can choose whether
to freeze only new activity or also clear open orders.

## Live Promotion Draft Criteria

These are initial planning criteria and must be encoded in versioned config
before live mode exists.

- at least 20 paper trading days,
- at least 300 to 500 paper trades,
- positive expectancy after fees and slippage,
- positive expectancy under 2x cost stress,
- maximum drawdown within 6 to 8 percent,
- zero daily loss-limit violations,
- no dependence on one or two symbols for most profit,
- walk-forward and out-of-sample consistency,
- operator review approval before each capital ramp.

Daily return above 1 percent after costs is treated as a strong result but not a
promotion rule by itself. It can also signal overfitting or lucky regime
exposure.

## Daily Review

At 08:00 KST, the daily report should summarize:

- what changed,
- current mode,
- engine heartbeat,
- paper/live status,
- open risk events,
- model performance,
- trading metrics,
- blockers,
- next goal script.

One concise report bundle per day is preferred.

## Dashboard Minimum

The dashboard shows:

- mode,
- heartbeat,
- KIS connectivity,
- cash and equity by currency,
- holdings,
- open orders,
- recent fills and rejects,
- model signals,
- ensemble action,
- confidence,
- expected edge,
- risk score,
- stop-new-orders state,
- cancel-open-orders action status.

The dashboard must not show secrets, raw KIS payloads, or unrestricted order
controls.
