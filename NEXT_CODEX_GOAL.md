# Next Codex Goal

## Objective

Build `private-kis-paper-operator-dashboard-v1`.

Create the smallest Docker-backed, loopback-only private operator dashboard for
the existing KIS Paper account-read contract and deterministic local safety
controls. It should make current paper cash, positions, open orders, source
state, and effective entry/exit pause state observable without making the
dashboard a strategy engine or an order-submission surface.

## Hard Boundaries

- Use only `KIS_PAPER_*` through the existing named Paper account-read owner
  paths. Never read, reference, route, or log `KIS_LIVE_*`.
- The dashboard is private and loopback-only. Do not expose a public host,
  public URL, tunnel, cloud deployment, or unauthenticated non-loopback bind.
- No dashboard button may create, modify, cancel, or imply a broker order.
  It may only read Paper state or persist deterministic local control state.
- Do not invent account values, prices, PnL, fills, or strategy recommendations
  when an account read is unavailable. Render an explicit unavailable state.
- Keep credentials, account identifiers, raw API payloads, and dashboard auth
  values out of Git, logs, browser HTML, screenshots, and external artifacts.
- Preserve the local-paper replay and all KIS collector/task behavior. Do not
  alter live routes, strategy selection, model promotion, GPU scheduling, or
  market-data collection.

## Required Work

1. Run a concise Throughput Review: the task-owned QQQ/SPY collection remains
   externally due; the operator dashboard is an independent Execution/Infra
   package. Ask Claude CLI for a short drift-check before any dashboard/runtime
   architecture change, and record only `review_unavailable` if it cannot
   return in the bounded window.
2. Reattest the existing KIS Paper account snapshot and local emergency-control
   contracts. Reuse their data structures and ownership boundaries instead of
   introducing a parallel broker client or order path.
3. Build a minimal Docker-backed local UI with a compact account view: current
   cash/orderable state when available, positions, open orders, data freshness,
   and source/route status. Account refresh must be explicit or bounded and
   read-only; no hidden background order behavior is allowed.
4. Add deterministic local operator controls for entry and exit pause only when
   their execution semantics are real and testable. The UI must show the
   effective persisted state and clearly distinguish a local control from a
   broker action. Keep an emergency/cancel state visible when the existing
   contract supports it.
5. Enforce loopback-only serving and the existing dashboard-auth policy. A
   missing local configuration may make account reads unavailable, but cannot
   downgrade host isolation or reveal a secret.
6. Add focused tests for virtual-route isolation, no `KIS_LIVE_*` access,
   absence of broker submission from dashboard routes, secret-free rendering,
   read-only account handling, unavailable-state rendering, pause-control
   persistence, and loopback/public-bind rejection.
7. Run the dashboard locally in Docker when configuration permits and inspect
   the actual private UI. Refresh Execution, Infra, orchestration, and handoff
   stateboards with only current contracts and limitations.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add private KIS Paper operator dashboard`
