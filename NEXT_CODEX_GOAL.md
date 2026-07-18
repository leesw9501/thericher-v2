# Next Codex Goal

## Objective

Build one small, deterministic, no-lookahead daily feature materializer for the
existing development-only `SPY`/`QQQ`/`IWM` wrapper.

This advances feature/model research only. It must not create labels, models,
decisions, candidates, a campaign, paper orders, or a profitability claim.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Invoke the Review checkpoint.

## Boundaries

- Do not read `.env`, credentials, or account data; make no network, KIS, or
  broker call, and leave `THERICHER_MODE=off`.
- Use only the existing static broad-daily development wrapper. Do not acquire,
  rewrite, widen, or copy market data; do not breach the `D:` free-space floor.
- Do not train a model, use the GPU, construct labels, rank, promote, open a
  holdout, submit a local/external order, or claim profitability.
- Do not unwrap the development-only universe into a campaign or generic local
  paper path. Do not add a provider framework, feature registry, scheduler,
  dashboard, report family, or v1-style gate.

## Required Work

1. Let Engine Research define and implement one pure, bounded daily feature
   materializer that consumes `DevelopmentDailyUniverse` as its distinct source
   contract. It may add one private Data-owned re-verification accessor, but
   must not expose raw bars at the public development-universe boundary. Use a
   small explicit feature set and make every feature row at session `t` depend
   only on bars at or before `t`.
2. Keep output descriptive and in-memory: no target/label, score, threshold,
   trade intent, artifact write, or campaign adapter. Preserve the wrapper's
   source hash and limitation metadata with the feature result.
3. Add focused tests for deterministic ordering, common-session alignment,
   no-lookahead behavior, immutable source/limitation propagation, and refusal
   to accept a plain `CatalogedBars` tuple.
4. Ask Claude for a short leakage/architecture falsification check before
   architecture-changing edits. Invoke the Review checkpoint, then update the
   Data and Engine Research stateboards, `HANDOFF.md`, and this next goal.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add development daily feature materializer`
