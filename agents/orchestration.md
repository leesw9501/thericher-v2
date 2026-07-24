# Codex Orchestration Stateboard

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is Codex's current cross-lane projection, not a fourth Role Agent, a
second objective, an implementation queue, or a historical ledger.

## Scope

Improve the engine loops by keeping independent ready work moving while an
external data, compute, or execution resource waits. Link to role stateboards
instead of copying their queues, evidence, or recovery narratives. Never make
strategy, model-promotion, broker, capital, or live-risk decisions here.

## Current Cross-Lane View

- Company objective: follow `NEXT_CODEX_GOAL.md`; do not restate or replace it.
- Shared bottleneck: Data is calibrating durable KIS Paper token reuse/pacing
  and actual historical-minute capability so collection can use the observed
  throughput rather than a fixed conservative assumption. This is Data-owned;
  its exact queue remains in `data.md` and independent collection may continue.
- Resource posture: Data collection may proceed independently of frozen model
  campaigns. GPU work waits only for an eligible frozen Research contract, not
  for a timer or another lane's unavailable input.
- External waits: provider quota, retry, and scheduled-session waits are owned
  by their named worker or existing scheduler. They do not occupy the
  foreground orchestrator.

## Current Operating Improvement

Replace foreground quota/timer sleeping with a recorded next-due worker state
or an existing goal-owned schedule. While that worker waits, Codex dispatches
another ready, non-conflicting lane package. A long-running test or active
collection may continue in its own worker; it is not an orchestrator wait.

## Review Triggers

Review this projection at task start, after interruption, and at each company
goal boundary. Check only cross-lane facts: active work, resource conflict or
idle capacity, external waits, and the one improvement above. Replace stale
facts instead of appending history.

## Recovery

Classify an external wait as `resume` with its next due time. If a worker is
stuck, restart or reconcile that worker without pausing a distinct ready lane.
Use Git and external artifacts for detailed history; this file keeps no run log.

## Next Handoff

At the next integration, verify that no provider cooldown or timer sleep holds
Codex while a ready Data, Engine Research, or Execution package can proceed.
