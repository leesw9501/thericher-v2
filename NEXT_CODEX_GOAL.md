# Next Codex Goal

## Objective

Complete kis-paper-d1-prospective-observation-pairing-v1: add a bounded,
source-safe QQQ/SPY daily-observation pairing capability that records one
decision-time snapshot and one later re-observation of the same completed
session through the existing KIS Paper market-data route. Its only research
purpose is to falsify revision-leaking input; a matching pair never promotes
the v2 cache to a model, GPU, Execution, Paper, or live consumer.

## Boundaries

- Use only KIS_PAPER_* through the existing Data-owned QQQ/NAS + SPY/AMS daily
  route. Never read, route, or mention KIS_LIVE_*.
- Market-data calls and a goal-owned bounded schedule are approved. Do not use
  account, position, quote, order, or broker endpoints.
- Keep raw cache bytes under D:/market_data and source-safe receipts under
  D:/thericher-v2/model-artifacts; never print or retain raw rows, credentials,
  account identifiers, or response bodies in Git or receipts.
- Preserve the v1 quarantine and current v2 immutable data contract. Do not
  overwrite, clear, relabel, or use a conflicting row as an implicit revision.
- Reuse the existing single-client, measured-pacing, durable-cursor behavior.
  A rate limit or next due time belongs to the owned worker or schedule, never
  to foreground orchestration.
- Do not create a model, target, feature, campaign, GPU appointment, replay,
  order intent, Paper order, or live behavior.
- Do not treat one observation, a later final value, or a matching pair as
  point-in-time availability, provider finality, corporate-action qualification,
  a complete universe, or a profitability result.

## Required Work

1. Reattach the current v2 QQQ/SPY cache and its source-safe receipts before
   implementation. Define one immutable pair contract with the exact session
   key, first-observation time, later-observation time, source identity hash,
   and allowed categorical outcomes.
2. Add a minimal Data-owned two-stage worker or schedule using the existing
   daily collection path. It must persist the first stage before the later
   re-observation and keep a durable next_due without foreground waiting.
3. Make pair evaluation fail closed: missing first observation, absent
   decision-time bar, identity mismatch, conflicting cache state, or incomplete
   pair yields a scoped input_unavailable or disqualified outcome. A matching
   pair is measurement-only.
4. Add focused tests for KIS Paper-only routing, no credential/raw-data leakage
   in receipts, exact pair binding, immutable/idempotent artifacts, mismatch
   rejection, and schedule-owned waiting.
5. Run offline tests and a bounded wiring smoke. If an eligible session occurs
   under the task-owned schedule, run exactly the scoped first or later stage;
   otherwise preserve its next_due and continue another ready package without
   polling.
6. Ask Claude for a concise falsification-first review before relying on any
   pair result. Refresh stateboards, HANDOFF.md, and RUNBOOK.md; run required
   verification; commit, push, replace this file with exactly one next material
   objective, and continue.

## Strongest Kill Test

For either QQQ or SPY, if the intended decision-time observation is absent or
its immutable identity differs from the later re-observation, the session is
disqualified. If no two-observation pair can be produced prospectively, close
this measurement path rather than extending it.

## Verification

~~~powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
~~~
