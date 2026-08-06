# Next Codex Goal

## Objective

Build `align-daily-operating-review-automation-v1`: update only the existing
daily operating-review Codex automation prompt so its recurring operator update
uses the current role stateboards, current objective, `ready / owned / due`
facts, bottleneck, recovery action, and current clean-root parallel verification
policy. This improves the data, research, validation, and Paper loops by making
operational evidence useful without adding a new approval process or worker.

The completed prior objective compressed `agents/orchestration.md` to a
57-line current projection. Its Claude governance drift-check timed out as
`review_unavailable`; independent consistency checks retained its due and
recovery facts.

## Hard Boundaries

- Do not create, delete, trigger, pause, resume, or retime an automation.
- Update only the prompt of the one existing daily operating-review automation;
  preserve its identity, name, recurrence, status, destination, execution
  environment, project, and target thread exactly.
- Do not call KIS, submit or modify Paper orders, manually invoke a task, or
  alter a broker route, order behavior, capital rule, credential path,
  dashboard, Docker/runtime, or live behavior.
- Do not read or expose `KIS_LIVE_*`, secrets, account facts, private intents,
  order identifiers, or raw market data.

## Required Work

1. Locate the existing daily operating-review automation from its local
   automation configuration, then read it through `automation_update` in view
   mode. Do not infer its identity from a Markdown stateboard.
2. Reconcile its prompt with `AGENTS.md`: it must distinguish `ready`, `owned`,
   and `due`; report material changes, blockers, recoveries, and operator
   decisions; use the current clean-root parallel authority helper only at a
   goal boundary; and avoid stale serial-test, fixed-worker-count, approval-gate,
   or routine-status language.
3. Update only that prompt using `automation_update`, then read the automation
   back. Preserve every non-prompt field exactly and do not trigger it.
4. Record the current automation alignment fact in the orchestration projection
   and refresh this file. Keep the report concise and do not create a second
   report, scheduler, or agent queue.

## Verification

Run a focused automation readback/redaction consistency check, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Align daily operating review automation`
