# Next Codex Goal

## Objective

Add the first authoritative observation loop for receipt-linked KIS Paper SPY
orders.

The completed daily entry/exit path may create a one-share virtual limit order.
This objective must observe the exact durable intent through KIS Paper facts and
produce truthful lifecycle attribution without fabricating a fill, realized
PnL, or a permission gate.

## Standing Authority

- All private `KIS_PAPER_*` market/account reads, virtual order submit/modify/
  cancel, reconciliation, sizing, local `D:` retention, and schedules are
  authorized. Continue ready Paper work by default.
- Do not read `KIS_LIVE_*`, use a live host/route, real capital, paid data,
  unclear rights, public exposure, Git-hosted raw data/artifacts, or secrets.
- A stale daily receipt, blank quote, missing fill, unfilled order, historical
  marker, or unknown exact intent is evidence about that scope only. It must
  not block a distinct correct Paper action or another lane.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect only sanitized daily-session, lifecycle, runtime, and scheduled-task
   metadata before choosing a recovery or observation action.
5. Ask Claude for a concise falsification-first check before relying on a KIS
   completion/position field as fill, terminal lifecycle, or PnL evidence.

## Role-Owned Work

### Data Agent

1. Verify the narrow KIS Paper completion/position source contract needed for
   exact SPY intent observation: endpoint scope, exchange mapping, pagination,
   timestamp meaning, and safe provenance. Do not mix a provider or infer a
   fill from a daily bar.
2. Keep the daily head resumable and publish only the safe freshness facts that
   the active session needs.

### Engine Research Agent

1. Define a compact attribution schema joining immutable receipt, target
   resolution, intended side, observed lifecycle, and `pnl_status`. Treat a
   missing or incomplete KIS completion fact as `not_observed` or pending, not
   as a negative return or a model result.
2. Preserve local-paper replay separately from KIS Paper evidence; do not tune
   the two-close baseline or start model selection from one Paper observation.

### Execution Agent

1. Add a read/reconcile path for one exact receipt-linked SPY Paper intent.
   It must make no new submit, modify, or cancel call while observing an order.
2. Publish a safe immutable observation fact that can distinguish at least
   `not_submitted`, `open`, `cancelled`, `filled`, `outcome_unknown`, and
   `unavailable` only when KIS facts support that distinction. Keep raw order
   IDs, prices, quantities, account values, fills, and broker payloads private.
3. Derive realized PnL only if an official KIS Paper fact supplies enough
   authoritative information; otherwise retain `pnl_status: not_observed`.
   Do not estimate it from daily bars, quotes, intent, or acknowledgement.
4. Add a bounded goal-owned observer schedule only after offline and Docker
   tests prove it is Paper-only, idempotent, and cannot create a broker side
   effect. Do not turn scheduling into a quota or approval latch.

### Validation Agent

1. Independently test that observation never emits an order request, cannot
   turn an acknowledgement into a fill, and cannot create a PnL claim from
   incomplete/stale facts.
2. Test exact receipt linkage, restart/replay behavior, Paper/live isolation,
   and artifact redaction with no network, credential, or KIS dependency.

## Completion Evidence

- One receipt-linked Paper intent can be observed/reconciled independently of
  new daily decisions.
- Lifecycle/PnL attribution remains truthful under missing, stale, open,
  cancelled, and ambiguous KIS facts.
- Any observer schedule is private, Paper-only, idempotent, and has no broker
  side-effect capability.
- Data, models, secrets, raw broker facts, and generated artifacts remain off
  Git; no live path is added.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add paper lifecycle observation loop`
