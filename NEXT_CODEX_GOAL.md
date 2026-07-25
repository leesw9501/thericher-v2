# Next Codex Goal

## Objective

Continue the single prospective QQQ intraday-head collection through its next
2026-07-28 00:35 KST due result and decide, from metadata only, whether its
first-five-session preparation input has become valid. Do not wait in the
foreground or create a second scheduler: the existing four-trigger Data task
owns collection.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read `HANDOFF.md`, `AGENTS.md`, `RUNBOOK.md`, `agents/orchestration.md`,
   `agents/data.md`, `agents/engine-research.md`, and `agents/execution.md`.
3. Reattest the current metadata baseline with:

   ```powershell
   uv run python scripts\inspect_kis_intraday_head_coverage.py
   ```

## Hard Boundaries

- Use only source-safe runtime and metadata evidence: never print or commit
  raw market/broker data, prices, credentials, account identifiers, private
  intents, or KIS response bodies.
- Keep one `thericher-kis-paper-intraday-head` task, one Docker profile, the
  four-page-per-target cap, source pacing, strict conflicting-row rejection,
  and exact 390-minute session selection. Do not read `KIS_LIVE_*` or use a
  live route.
- Do not run a model/GPU job, select a candidate, create an intent, or submit
  a Paper order. The offline consumer remains input-pending until a valid
  first-five preparation pair exists.
- A scheduled wait, a short head union, a missing preparation pair, or a
  Claude tooling failure is scoped evidence, never an approval or Paper hold.

## Required Work

1. Reattest that the installed head task remains `Ready`, has the four KST
   triggers, and has no missed-run anomaly. Record only sanitized task facts.
2. After the next due result, compare its coverage to the reattested generation-8
   baseline: complete-minute counts, offset-based missing ranges,
   continuation/overlap categories, last reason category, and preparation
   status. Continue independent ready work instead of waiting for that time.
3. If five exact 390-minute QQQ sessions exist, invoke the existing
   metadata-only preparation handoff and then the credential-free offline
   consumer. Otherwise, retain the established collector rules unless a bounded
   source/test case identifies one exact recovery change.
4. The 2026-07-25 daily SPY session was categorical `paper_only` / `no_intent`
   / `session_closed`; its receipt reference had no exact receipt-derived run
   identity and observer/terminal fields were `not_attempted`. Consume the next
   daily result only through its exact receipt-derived run identity and
   categorical observer/terminal facts; do not infer fills or PnL from a
   no-intent, missing, or ambiguous observation.
5. Refresh the Data, Research, Execution, and orchestration stateboards with
   the current recovery class and next action, then verify, commit, and push
   any bounded implementation or stateboard change.

## Completion Evidence

- A source-safe before/after QQQ coverage comparison names session completeness,
  continuation/conflict categories, and `resume`/preparation status.
- A valid first-five pair drives only the existing offline local-paper
  observation; otherwise the precise next Data collection remains the normal
  recovery action.
- Daily SPY evidence, if present, remains categorical and makes no fill or PnL
  claim without authoritative completion facts.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```
