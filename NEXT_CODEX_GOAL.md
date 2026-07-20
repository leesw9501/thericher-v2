# Next Codex Goal

## Objective

Turn the existing JSON-only dashboard skeleton into a usable, Docker-local,
optionally token-protected paper-console foundation. It must make the broker-free local
simulation visible now, without making KIS connectivity, model profitability,
or the pending raw-`1m` observation a prerequisite.

The result is a compact operational screen at `http://127.0.0.1:8787`, not a
public dashboard and not a broker console.

## Current Authority

- Keep `THERICHER_MODE=off`.
- The `web` process must never receive, read, log, or call `KIS_*`, Tiingo, or
  any broker endpoint. An optional `THERICHER_DASHBOARD_TOKEN` remains only a
  local dashboard-authentication secret.
- Do not make any KIS account, position, buying-power, open-order, order,
  cancel, market-data, or live request in this objective. Do not read the
  actual `.env` during tests or Docker verification.
- Do not submit, modify, or cancel an external order. Existing local fills
  remain `source: local_paper`.
- Keep Docker bound to `127.0.0.1`; do not expose a public or LAN service.
- Do not add a frontend framework, a new database, a daemon, or a dashboard
  report family. Reuse the stdlib server, existing event store, emergency
  state, and Docker `web` service.

The separately reserved 2026-07-20 KIS raw-`1m` observation remains an
independent, metadata-only scheduled operation. Do not run it manually,
broaden it, display raw fields, or treat either terminal result as a dashboard
or capability promotion.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
   `RUNBOOK.md`, `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
3. Inspect the existing dashboard server, view model, local event replay,
   emergency state, and Docker `web` service before editing.
4. Ask Claude for a short drift-check only if a new web dependency, a KIS
   bridge, a new durable runtime, or a material safety-control semantic is
   proposed. None is expected for the intended implementation.

## Work Packages

### Execution: Local Paper Console

1. Keep the machine-readable state endpoint and make `/` render a compact,
   practical browser UI from the same sanitized snapshot. Use a dense summary
   and tables rather than a landing page or decorative card layout.
2. Show only locally reconstructable facts:
   - configured mode and monitor status;
   - emergency state and local-paper activity;
   - local positions, cash, decisions, fills, and PnL only when the event
     store can establish them;
   - clear empty states when no local events exist.
3. Show KIS holdings, prices, buying power, and open orders as `unknown` until
   a future, fresh, separately authorized sanitized read-only reconciliation
   exists. Do not substitute old probe facts, local inference, or zeroes.
4. Expose only the existing local safety actions: pause new entries and request
   local cancellation. They must change only local emergency state and clearly
   remain unable to call a broker. Do not add a generic "sell stop" because it
   could suppress a hard-risk exit; any later discretionary-reduction pause
   needs a separately scoped execution decision.
5. Preserve consistent token protection for the HTML, JSON, and action
   endpoints when `THERICHER_DASHBOARD_TOKEN` is configured. With no token,
   loopback-only binding is the minimum access boundary. Never include a token,
   account identifier, raw broker payload, or secret in rendered HTML, logs,
   snapshots, tests, or artifacts.

### Infra Capability: Local Docker Proof

1. Keep the `web` container credential-free apart from the optional dashboard
   token and confirm its mounted runtime state is sufficient for the screen.
2. Verify the page through the Docker `web` service using `.env.example` or
   explicit nonsecret values, then report the localhost URL. Do not use the
   real `.env` for this proof.

### Review

At integration, check that the change improves the paper-trading and
live-risk-control loops without becoming a KIS adapter, account cache, generic
agent system, or report/gate layer.

## Required Tests

Add focused tests proving that:

- `/` is a usable HTML view, `/state` remains a sanitized machine-readable
  endpoint, and configured-token access applies consistently to both;
- local-paper replay appears correctly, including empty and nonempty states;
- unavailable KIS facts render as `unknown`, never as zero or inferred data;
- the two controls update only local emergency state and cannot invoke a
  broker;
- the dashboard process has no KIS client/config dependency and Docker keeps
  it loopback-bound.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Also run a focused Docker-local browser or HTTP smoke test against the `web`
service, without the real `.env`, and report the command and result.

## Completion

Update `agents/execution.md` and `HANDOFF.md` only with durable console facts.
Record the pending raw-`1m` observation's sanitized terminal state if its
scheduled automation completes while this objective runs. Refresh this file to
the single next objective, commit, and push. The likely next direction is a
separately scoped fresh KIS read-only reconciliation bridge, followed later by
an explicitly authorized paper-order canary; neither is implied by this goal.
