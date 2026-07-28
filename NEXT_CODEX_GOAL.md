# Next Codex Goal

## Objective

Reattest the existing private KIS Paper operations console to one fresh,
sanitized virtual-account observation so the local dashboard can reliably show
current Paper account, positions, open-order categories, and execution-control
state without widening broker authority.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattach the existing dashboard, `kis-readonly` bridge, account projection,
   and emergency-control contracts before adding a new route or worker.
3. Ask Claude for a concise falsification-first check before any material
   dashboard/broker-boundary or scheduler change. If local OAuth remains
   expired, record `review_unavailable` and continue this private non-live
   package.

## Contract

- Execution owns the KIS Paper read-only observation and its sanitized runtime
  projection. The dashboard remains local/loopback and never reads credentials
  or calls KIS itself.
- KIS Paper account, position, and open-order reads are standing-authorized.
  This objective has no `KIS_LIVE_*`, live behavior, order submission,
  modification, cancellation, or public-service work.
- Reuse the existing virtual-only route, serializers, dashboard controls, and
  Docker boundaries. Do not rebuild v1 reports/gates or create a second console.
- Persist only source-safe account categories and freshness/provenance outside
  Git. Never persist or log credentials, account identifiers, raw broker bodies,
  or quote values.
- Data's installed NAS D1 forward task remains independent. Do not wait for its
  later sessions or alter its collector/observer contract.

## Work

1. **Execution:** run one bounded KIS Paper read-only refresh through the
   existing bridge, reattest its virtual route and projection, and classify any
   failure precisely without creating an intent or broker side effect.
2. **Dashboard:** verify the existing Docker-local dashboard consumes only the
   fresh sanitized projection and shows account/position/open-order categories,
   local-paper provenance, and pause-buy/pause-sell/emergency controls. Keep it
   credential-free and loopback-bound.
3. **Validation:** add focused tests for read-only route isolation, stale or
   malformed projection handling, dashboard-only control persistence, and no
   KIS/live/credential dependency in the web process.
4. **Orchestration:** run one local Docker smoke and one bounded read-only
   runtime observation. A source/account availability failure is a scoped
   recovery fact, not a hold on Data or Research.

## Completion

- One current source-safe KIS Paper account projection is reattestable or a
  precise scoped recovery receipt exists.
- The local dashboard accurately reflects only that projection and local control
  state, with no public exposure or direct broker/credential path.
- Focused tests prove the read-only and route-isolation boundary. Refresh
  stateboards and replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Refresh private paper operations console`
