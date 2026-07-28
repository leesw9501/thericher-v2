# Next Codex Goal

## Objective

Exercise one bounded QQQ `kis_paper` canary through the already deployed,
fresh-intraday route. Prove the existing local decision, durable intent,
virtual submission, and reconciliation boundary from one new current-session
attempt without selecting a research model, widening broker authority, or
touching live behavior.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   stateboards.
2. Reattach the installed QQQ/NAS intraday-head task, its exact terminal
   receipt lineage, and the existing target-binding/canary implementation.
   Treat a historical receipt as evidence only, never as a current-order input.
3. Confirm the current task owns a ready, fresh completed-bar window before it
   may construct a new virtual intent. Do not add a parallel collector, a new
   scheduler, or a manual broker bypass merely to force an attempt.

## Authority And Boundaries

- `KIS_PAPER_*` is standing-authorized only through the existing dedicated
  private `kis_paper` route. It may read the virtual account and current quote,
  persist one new target-local intent, and submit/modify/cancel/reconcile only
  that virtual intent when its existing call-time technical checks pass. A
  submitted bounded canary follows the existing immediate-cancel and exact
  reconciliation lifecycle.
- Do not read or route `KIS_LIVE_*`, enable live behavior, change a material
  execution-risk limit, or expose a public service.
- Keep `THERICHER_MODE=off` and do not add a new credential reader, log,
  artifact, Git entry, dashboard field, or Claude prompt containing secrets,
  account identifiers, raw broker bodies, or raw market rows.
- The existing paper-vs-live isolation, durable-intent-before-side-effect rule,
  unknown-outcome reconciliation rule, and `source: local_paper` offline
  replay rule are fixed. This objective does not select, rank, ensemble,
  promote, or evaluate a research candidate.
- A stale/incomplete window, unavailable account, incompatible position/open
  order, or categorical broker failure is a precise terminal fact for this one
  attempt. Record and recover it through the owned route; do not force a
  replacement intent or block independent Data/Research work.

## Work

1. **Data:** let the existing Data-owned intraday-head route produce or
   reattach one current QQQ/NAS completed-bar window. Preserve its single-client
   collector, source-safe receipt, and normal schedule ownership.
2. **Execution:** use that exact fresh receipt to run one bounded virtual-paper
  canary through the existing target-binding path. Re-read account and quote at
  the call site, persist the exact intent before a broker side effect, then use
  the existing immediate-cancel and reconciliation lifecycle if submission is
  accepted. Do not bypass a no-intent condition.
3. **Validation:** independently reattach the terminal receipt with the
   network-disabled validator and confirm the loopback operations console still
   presents a sanitized read-only projection without a broker client or
   submission control.
4. **Orchestration:** if the current market input is not yet eligible, dispatch
   no duplicate foreground wait. Record the precise source/status fact and
   continue another ready lane under the next goal; the installed owner keeps
   its normal due time.

## Completion

- One new source-safe terminal canary receipt exists: reconciled virtual-paper
  lifecycle when all predicates passed, otherwise an exact bounded no-intent or
  technical recovery outcome.
- The independent validator reattests the same terminal scope.
- No live request, secret output, raw broker payload retention, model
  promotion, ranking, ensemble, or forced replacement intent exists.
- Refresh the relevant stateboards and replace this file with exactly one next
  objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Exercise bounded QQQ paper canary`
