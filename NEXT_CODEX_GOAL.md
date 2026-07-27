# Next Codex Goal

## Objective

Deploy the verified QQQ runtime-freshness contract to the one existing private
KIS Paper intraday-head schedule, then prove its scheduled action uses the
rebuilt local image without creating a duplicate task, KIS call, or broker
action.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `RUNBOOK.md`, and the active stateboards.
2. Inspect only the named schedule, its runner, its Docker profile, and
   source-safe task metadata. Do not inspect raw market rows, account data, or
   credentials.
3. Treat the existing `runtime-freshness-v2` validation artifact as completion
   evidence for the prior objective, not as a current-market input.

## Work

1. **Infra/Execution:** use the existing schedule installer to rebuild its
   named local Docker services and update only the existing
   `thericher-kis-paper-intraday-head` task definition. Keep its runner,
   trigger cadence, ownership, `IgnoreNew`, and recovery behavior intact. Do
   not create a second task, manually trigger a duplicate run, or change a
   route authority.
2. **Validation:** inspect the installed task action and the relevant Compose
   service definition to prove that a due run uses the rebuilt local image and
   the same virtual-only/session/validator chain. This is a configuration proof,
   not a market-session observation.
3. **Data:** record only source-safe deployment evidence and the named worker's
   next due fact. A future regular-session observation belongs to the installed
   worker; do not foreground-wait for it.
4. **Execution:** retain the current two-minute QQQ runtime/Paper deadline.
   Do not invoke a standalone account, quote, order, cancel, or reconciliation
   call just to manufacture a result. The next due worker may naturally produce
   its existing truthful no-intent or Paper lifecycle.

## Boundaries

- `KIS_PAPER_*` remains standing-authorized only through the named scheduled
  paths. Do not read or route `KIS_LIVE_*`.
- No live behavior, cost, public service, raw-row disclosure, model promotion,
  or threshold widening.
- No new Windows scheduler, cron, polling loop, or foreground wait.
- Keep market data under `D:\market_data` and artifacts under
  `D:\thericher-v2\model-artifacts`.

## Completion

- The existing task is updated in place and its source-safe action/profile
  proof shows the rebuilt virtual-only route.
- The deployment creates no KIS/broker invocation, new task, secret output, or
  raw-market artifact.
- Stateboards identify the future observation as worker-owned `next_due`, not a
  company hold.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Deploy QQQ runtime freshness schedule`
