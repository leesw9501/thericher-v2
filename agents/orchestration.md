# Codex Orchestration Stateboard

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is Codex's current cross-lane projection, not a fourth Role Agent, a
second objective, an implementation queue, or a historical ledger.

## Scope

Improve the engine loops by keeping independent ready work moving while an
external data, compute, or execution resource waits. Link to role stateboards
instead of copying their queues, evidence, or recovery narratives. Never make
strategy, model-promotion, broker, capital, or live-risk decisions here.

## Throughput Rule In Effect

Treat a genuinely unknown private non-live capability as a bounded probe with a
defined scope and reversal fact, not an approval wait. Keep an existing
documented or measured rate/retry control until source evidence or the probe
supports a change. A quota or cooldown remains the named worker's `next_due`,
and a failed probe is evidence only for that input, never a pause on another
ready lane.

## Current Cross-Lane View

- Company objective: follow `NEXT_CODEX_GOAL.md`; do not restate or replace it.
- Shared fact: the QQQ/SPY daily event-boundary consumer is complete. Its
  aggregate external receipt re-attested the 4,756-session source and used only
  the 3,806-session prefix, with replayable local-paper fills and no tail or
  raw-event retention. The inconsistent control result is closed plumbing
  evidence, not a model direction. This does not hold prospective intraday
  collection, Paper execution, or the existing frozen baselines.
- Shared fact: the existing Norgate static panel now has a one-file,
  development-only qualification receipt. It closes an ambiguity rather than
  opening a new model lane: the receipt has no rows/values and its negative
  model, GPU, Paper, PnL, PIT, and live scope is re-attested on every reuse.
- Resource posture: Data collection may proceed independently of frozen model
  campaigns. GPU work waits only for an eligible frozen Research contract, not
  for a timer or another lane's unavailable input.
- External waits: provider quota, retry, and scheduled-session waits are owned
  by their named worker or existing scheduler. They do not occupy the
  foreground orchestrator.

## Current Operating Improvement

Replace foreground quota/timer sleeping and unmeasured permanent throttles
with a recorded next-due worker state plus bounded, result-driven calibration.
For local replay work, keep existing simulator semantics but use bounded
in-memory temporary batches, flush them only for replay verification, and
delete them before artifact persistence. While a worker waits, Codex dispatches
another ready, non-conflicting lane package. A long-running test or active
collection may continue in its own worker; it is not an orchestrator wait.

At each active checkpoint, compare observed latency, idle resources, repeated
failure modes, and evidence quality. When one scoped, reversible improvement
has a clear engine-loop benefit, integrate it before the next company-goal
boundary; otherwise retain the simpler path.

## Review Triggers

Review this projection at task start, after interruption, and at each company
goal boundary. Check only cross-lane facts: active work, resource conflict or
idle capacity, external waits, and the one improvement above. At a goal
boundary, identify the largest material bottleneck or idle resource and retain
or make one reversible evidence-backed improvement. Replace stale facts instead
of appending history.

## Recovery

Classify an external wait as `resume` with its next due time. If a worker is
stuck, restart or reconcile that worker without pausing a distinct ready lane.
Use Git and external artifacts for detailed history; this file keeps no run log.

## Next Handoff

At the next integration, verify that the completed D1 receipt is not reused as
a model-selection input, and verify that no provider cooldown, schedule, or
timer sleep holds Codex while a ready Data, Engine Research, or Execution
package can proceed. Also verify that the static Norgate receipt is not being
mistaken for a source of model-ready feature rows.
