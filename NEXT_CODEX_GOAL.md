# Next Codex Goal

## Objective

Make the existing KIS Paper read-only account path produce one truthful,
source-safe account-readiness result for a later paper canary, while every Data
collector continues independently.

This is Execution plumbing, not a trade decision. It must establish only what
the virtual account, position, and open-order endpoints can provide and whether
the existing parser, host pinning, and recovery behavior are correct.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the existing virtual-only account bridge, its source-safe receipts,
   and the active broad and forward Data task states without printing
   credentials, account identifiers, raw broker bodies, prices, or quantities.
3. Ask Claude for a short falsification-first check only if a change would
   alter persisted-intent, broker recovery, or Paper-order semantics. A
   read-only parser or route-isolation repair does not need a routine review.

## Authority And Boundaries

- `KIS_PAPER_*` is approved for the existing virtual-host account, position,
  and open-order read-only path. Do not read or route `KIS_LIVE_*`.
- Do not submit, modify, cancel, or replace any broker order. Do not create a
  Paper intent, canary, model score, allocation, dashboard change, or live
  behavior.
- Reuse the existing virtual-host pinning, source-safe serializer, token/request
  guards, and reconciliation vocabulary. Do not create a second broker client
  or a generic workflow framework.
- A result may expose only categorical readiness, route identity, snapshot
  freshness, count/bucket facts, recovery class, and an external receipt hash.
  Never write credentials, account numbers, broker bodies, raw balances,
  positions, orders, or prices to Git, logs, stateboards, artifacts, or Claude.
- A technical unavailable/error result is scoped evidence for this read-only
  attempt. It is not an operator hold, a Data-collection hold, or a reason to
  retry an order.
- Broad KIS D1 backfill and the QQQ/SPY forward-data schedule retain their own
  locks, gates, and due times. Do not stop, duplicate, or serialize them behind
  this bounded read-only work.

## Work

1. **Execution:** inspect the current read-only account bridge and the exact
   `account_unavailable` evidence. Trace the virtual host, response parsing,
   snapshot validation, safe serialization, TTL, and failure classification.
2. **Execution:** make the smallest repair needed for a real KIS Paper
   read-only diagnostic to distinguish a valid empty/flat account snapshot from
   an unavailable, malformed, stale, wrong-host, or route-isolation failure.
3. **Validation:** add focused tests for virtual-host-only routing, no live
   credential access, no order endpoint/canary/intent path, source-safe receipt
   contents, a valid empty snapshot, and each repaired failure classification.
4. **Execution:** run one bounded real virtual-paper read-only diagnostic when
   its shared request/token guard permits. If that exact call is unavailable,
   persist only its safe recovery result and leave any retry to the existing
   owned path; continue other ready work without a foreground sleep.
5. Refresh affected stateboards, replace this file with exactly one next
   objective, then continue. A later separate goal may consume a complete
   account-readiness result for a one-share Paper canary.

## Completion

- Existing KIS Paper account-readiness behavior is source-safe, virtual-host
  pinned, and covered by focused tests.
- One real bounded read-only diagnostic or an equally truthful safe unavailable
  receipt exists outside Git.
- No order side effect, Paper intent, model decision, or live route occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Harden KIS Paper account readiness`
