# Next Codex Goal

## Objective

Complete `kis-paper-daily-auth-capability-probe-v1`: isolate the virtual-host
KIS Paper authentication capability behind the QQQ/SPY D1 collector's
source-safe `auth_rejected` result. This advances Data recovery only; it does
not make data, causal input, strategy, model, execution, or trading eligible.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first check before changing the authentication probe or making
  its one external token attempt. A missing response is `review_unavailable`,
  not agreement or a hold on this standing-authorized private Paper package.
- `KIS_PAPER_*` credential reads are authorized only through the named Data
  authentication path. Never read or route `KIS_LIVE_*`; never print, log,
  persist, or send credentials, tokens, account identifiers, raw broker bodies,
  or raw market rows to artifacts, Git, or Claude.
- Begin with source/fixture-only inspection. Reuse existing KIS Paper
  market-data authentication primitives; do not add a provider, scheduler,
  worker, public surface, account route, quote route, order route, or runtime
  replacement.
- If an external attempt is needed, make at most one virtual-host token request
  after a source-safe ownership/gate check. It must make no daily market-data,
  account, position, open-order, quote, order, or live request and may not
  retain the token. A due/ownership mismatch closes without an attempt; no
  automatic retry or foreground waiting.
- Retain only static categorical outcome, timestamp bucket, route isolation,
  and external receipt hash/pointer. `authenticated` proves only a bounded
  token capability; `auth_rejected` remains a route fact, not a credential
  diagnosis, consumer promotion, or operator-approval gate.

## Required Work

1. Inspect existing authentication/config/gate primitives and define the
   smallest source-safe probe contract with fixed outcome taxonomy.
2. Add focused fixtures proving no credential, token, market-data, account,
   order, raw body, or dynamic exception detail can enter a receipt; preserve
   existing collector behavior.
3. Run any required source-only verification. Then, only under the stated
   ownership/gate conditions, make one virtual-host authentication attempt and
   reattach its immutable source-safe outcome.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with the exact
   result. Do not retry the D1 collector in this objective.
5. Run verification, commit, push, replace this file with exactly one next
   objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
