# Next Codex Goal

## Objective

Resolve the first KIS Paper canary price-input compatibility issue and, when a
bounded KIS Paper price input is actually proven during an eligible US session,
run the next independently identified virtual canary through the existing
paper-only executor.

The first scheduled quote session received a success-shaped KIS response but
both required quote fields were blank, so it created no intent or order. This
goal makes that input contract truthful; it is not a profitability, model,
capital, report, or manual-approval milestone.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market/account reads, positions, open orders,
  virtual-order submit/modify/cancel, reconciliation, raw data retention on
  `D:`, and goal-owned schedules are authorized. A distinct paper intent does
  not need a new capital, trade-count, profitability, or confirmation gate.
- Never read `KIS_LIVE_*`, build a live route, use real capital, buy data,
  accept unclear rights, expose a public service, or commit secrets, raw data,
  or generated artifacts.
- Keep raw data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- `raw_market_data_retained: false`, an old unknown intent, a missing price
  candidate, or a failed probe affects only that concrete recovery or price
  conversion. None disables a later correctly scoped KIS Paper call, schedule,
  data collection, or distinct virtual intent.
- Do not guess, synthesize, or silently normalize a KIS price. A price source
  may be used only when its unit/tick scale, venue mapping, completed-bar time,
  freshness, and explicit-limit behavior are evidenced by code/tests and
  official or retained KIS evidence. This is input correctness, not an operator
  gate; unqualified candidates simply remain out of that conversion.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect only safe scheduled-task state, console projections, external
   evidence metadata, and cache metadata before reacting. Do not output
   credentials, account identifiers, raw broker bodies, or raw quote values.
5. Ask Claude for a short falsification-first drift-check before relying on a
   new Paper price source or changing the canary price-input route.

## Role-Owned Work

### Data Agent

1. Examine the existing KIS Paper head/cache and official KIS schema evidence
   to establish or reject one specific price candidate's scale, normalized
   exchange, timestamp completion, and freshness contract.
2. Keep the prospective head cache collecting on its existing schedule and run
   the metadata-only observation preparer after every outcome. A `pending`
   research result does not block this execution work.
3. If the head cache cannot prove the contract, record the exact missing fact
   and move to the next KIS Paper-compatible candidate without rewriting raw
   bytes or inventing a generic data platform.

### Execution Agent

1. Keep the current blank-field quote classification and Paper-only route
   isolation intact. Diagnose new candidates with allowlisted structural
   metadata only: HTTP class, mapping shape, field validity, scale, venue, and
   freshness categories; never retain quote values or response bodies.
2. Implement the smallest price-input adapter only after Data's contract is
   explicit. Persist the source provenance with the exact intent, retain the
   existing explicit-limit, identity, pacing, and reconciliation behavior, and
   make no live change.
3. During an eligible US session, execute a newly identified virtual canary
   automatically when the technical input contract holds. If it cannot hold,
   continue other KIS Paper data/account diagnostics and preserve the narrow
   reason; do not create an approval, quota, or global pause.

### Engine Research Agent

1. Keep the completed no-winner screen and prospective observation contract
   unchanged. Do not turn this execution price-input repair into a model
   selection, retuning, ensemble, or GPU-training decision.

## Completion Evidence

- A price-input candidate is either proven with a focused executable contract
  or rejected with a safe, exact missing-fact record; no raw quote values are
  retained.
- If proven during a due session, a new KIS virtual canary is attempted through
  the existing paper-only executor and its sanitized outcome is reconciled.
- Data head scheduling and research preparation remain independent and current.
- No KIS live behavior, secret output, raw broker payload, public dashboard,
  or generated artifact enters Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Resolve KIS paper price input`
