# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-paper-readonly-account-refresh-v1`: run and attest one bounded,
current KIS virtual-Paper account refresh through the existing named read-only
bridge, then make only its sanitized projection available to the existing
loopback dashboard.

This is an Execution-readiness capability test. It must make the actual
account, position, open-order, and orderable-funds state observable without
submitting, changing, cancelling, or inferring a trade.

## Boundaries

- `KIS_PAPER_*` credential reads and read-only account calls are
  standing-authorized. Do not read or route `KIS_LIVE_*`.
- Keep `THERICHER_MODE=off`. Do not submit, modify, cancel, reconcile, or
  synthesize an order or intent; do not call quote, market-data, or live routes.
- Use the existing `kis-readonly`/console-bridge ownership path and the
  existing loopback-only dashboard. Do not build a public service or a second
  dashboard.
- Never print or persist tokens, account numbers, raw broker bodies, order IDs,
  or raw prices. Use the Docker runtime projection and external artifact root
  only for the already-established sanitized shapes.
- Do not change the existing intraday-head or SPY paginated-prefix schedules.
  Their next session receipt remains independently worker-owned.

## Required Work

1. Ask Claude for a concise falsification-first route/recovery drift check
   before changing an execution boundary. State the existing named bridge,
   endpoint allowlist, strongest no-order kill test, and the fact that would
   reverse the conclusion.
2. Inspect the current read-only bridge, runtime projection, dashboard view,
   and prior `account_unavailable` evidence. Freeze one bounded actual refresh
   contract before calling KIS.
3. Execute at most one current read-only Docker refresh with the existing
   virtual host and collect only a sanitized, source-safe result. A categorical
   account/provider/configuration failure is a truthful completion result; do
   not turn it into foreground retrying or a cross-lane hold.
4. Verify that a successful projection, if available, is renderable by the
   loopback dashboard without credentials or broker access in the web process.
   An unavailable/malformed projection must remain hidden or categorically
   unavailable rather than exposing raw data.
5. Add focused tests for route allowlisting, no-order behavior, projection
   sanitization/freshness, dashboard isolation, and the exact failure recovery
   category discovered by the bounded run. Refresh the Execution and
   orchestration stateboards with only durable evidence.

## Completion Evidence

- Claude records `unsupported`, `uncertain`, or `supported-with-limits` without
  granting authority; independent work continues in every case.
- one bounded live virtual-Paper read-only attempt has a source-safe outcome;
  no order-side effect, live credential, or secret output occurs;
- focused tests plus required verification pass; commit and push complete; then
  replace this file with exactly one next company objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile kis-paper-intraday-head config --quiet
docker compose --env-file .env.example --profile kis-readonly config --quiet
```
