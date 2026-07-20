# Next Codex Goal

## Objective

Build one bounded KIS virtual-paper read-only reconciliation snapshot bridge for
the Docker-local paper console. The bridge improves the paper-trading and
live-risk-control loops by replacing the console's KIS `unknown` facts with a
fresh, typed, sanitized snapshot when one can be reconciled.

This is not an order, capital, model, data-archive, or live-trading objective.

## Authority And Boundaries

- The 2026-07-20 decision authorizes isolated `KIS_PAPER_*` virtual-paper
  development calls for typed account, position, buying-power, open-order, and
  necessary bounded market-data reads.
- Keep `THERICHER_MODE=off`. Do not read `KIS_LIVE_*` or call a live endpoint.
- Do not submit, modify, or cancel an external order. Do not propose a paper
  capital amount until a complete fresh read-only reconciliation exists.
- The web process must never receive, read, log, or call KIS, Tiingo, or a
  broker. It may consume only a separately produced sanitized snapshot.
- Do not persist credentials, account identifiers, raw broker responses,
  response-derived error text, or raw market rows in Git, logs, rendered HTML,
  tests, artifacts, or the runtime snapshot.
- Use one bounded reconciliation run with no automatic retry loop. A rejected,
  partial, stale, malformed, or incomplete result is explicitly `unavailable`,
  never an inferred empty account.
- Keep the local console loopback-bound. Its local emergency actions remain
  local-only and cannot become broker cancellation controls.
- The terminal raw-minute observation and any existing research campaign remain
  separate historical evidence. Do not retry, widen, or reuse them here.

## Required First Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
   `RUNBOOK.md`, `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
3. Inspect `execution.kis_readonly`, its tests, the dashboard snapshot/server,
   the local event store, and Docker Compose before editing.
4. Ask Claude for one short falsification-first drift-check before introducing
   a new one-shot bridge or changing a KIS read-only contract. Do not send it
   credentials, account identifiers, raw responses, or row-level data.

## Work Packages

### Execution: Read-Only Reconciliation

1. Reuse or narrowly extend the existing typed allowlisted KIS paper reader;
   do not introduce a generic KIS client, order path, daemon, scheduler, or
   broker dependency in the web process.
2. Define a small versioned sanitized snapshot contract with observed time,
   completeness/freshness status, and only console-safe mapped facts. Preserve
   the distinction between `unknown`, `unavailable`, and a verified empty list.
3. Add a single-shot execution-side runner that reads only the approved local
   paper configuration, performs the bounded reconciliation, writes the
   sanitized snapshot into the Docker-local runtime, and writes external
   sanitized evidence under `D:\thericher-v2\model-artifacts`.
4. Keep the default Docker engine command credential-free and non-broker. Scope
   any one-shot bridge credential access to the execution-side invocation only.
5. Make the console show the latest fresh sanitized KIS facts only when the
   snapshot contract proves them complete. Otherwise retain explicit
   `unknown`/`unavailable` state without reusing old probe results.

### Validation And Review

1. Add focused tests for snapshot redaction, strict completeness/freshness,
   fail-closed malformed or partial input, web-process credential isolation,
   and no order/cancel path.
2. Use an injected fake transport for contract tests. After tests pass, run one
   real bounded KIS virtual-paper reconciliation attempt with the local `.env`;
   report only sanitized result metadata.
3. At integration, verify that no new report/gate system, durable worker,
   general coordinator, or public service was created.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Also run focused bridge tests and a Docker-local HTTP smoke using `.env.example`
or explicit nonsecret values. The one real KIS read-only attempt is reported
separately without raw data or secrets.

## Completion

Refresh `agents/execution.md` and `HANDOFF.md` with durable bridge facts,
including the exact sanitized result status and recovery classification. Refresh
this file to one next objective, commit, push, and continue. A successful
reconciliation leads to a proposed paper-capital envelope for operator approval;
it does not authorize an order canary.
