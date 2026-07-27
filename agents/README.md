# Agent Stateboards

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the company objective. These
files are concise current projections for durable role lanes; they are not
reports, policy sources, or historical ledgers.

## Operating Model

```text
Operator -> Codex Orchestrator -> Role Agents
```

Codex decomposes one company objective into disjoint work packages and assigns
them to ready roles. Data, Research, and Execution may progress in parallel. A
blocked lane does not stop another ready lane. Codex integrates shared contracts,
verification, Git, recovery, and the next objective.

## Material Goal Blocks

When the company objective, rather than one lane, lacks a ready path because of
an external wait, unmeasured capability, or unresolved technical contradiction,
Codex records one compact `blocked-goal alternatives` entry in
`orchestration.md`. It gives the exact blocking fact, original plan, ready
alternatives, owners/resources, strongest kill test, and recovery action. Claude
reviews that one record from a falsification-first perspective; unavailable
Claude authentication is `review_unavailable`, not a hold. Codex then advances
every non-conflicting package inside standing authority.

This is not a report family, per-agent goal file, or substitute for explicit
operator authority over live capital, paid commitments, unclear rights, public
exposure, or a major runtime change.

For a material apparent operator decision, Claude and Codex may converge on a
recommendation and Codex may act only when that exact category is already
delegated, reversible, and no-cost. Agreement never creates authority for a
reserved live, paid, unclear-rights, public, or major-runtime action.

`orchestration.md` is owned by Codex, not a subordinate role. It holds only the
cross-lane view that no one role owns: resource conflicts, external waits, the
current bottleneck, and one reversible operating improvement. It links to lane
stateboards instead of copying their queues or history, and it cannot create a
second objective, approval step, or execution decision.

For private KIS Paper work, role agents record unavailable inputs and failed
runs as scoped evidence, not permission latches. All non-live private work,
including virtual orders and recurring schedules, is standing-authorized. A
historical marker, `raw_market_data_retained: false`, model result, or schedule
outcome cannot stop another correctly scoped ready lane or create an approval
wait. A false retention value is only a no-bytes fact for that historical
attempt; it is never a fixed state to clear. Only the exact unknown Paper
intent is reconciled before its own replacement; `KIS_LIVE_*` remains
unavailable.

## Active Durable Stateboards

- `data.md`: acquisition, canonical data, provenance, calendars, dataset
  manifests, splits, resampling, and data quality.
- `engine-research.md`: hypotheses, campaign contracts, CPU/GPU models,
  backtests, walk-forward validation, and analytical attribution.
- `execution.md`: local simulation, account/order/fill/position contracts,
  reconciliation, accounting PnL, risk, emergency behavior, and later KIS.
- `orchestration.md`: Codex-owned cross-lane resource and throughput view; not
  a Role Agent, implementation queue, or historical ledger.

## Independent And Invoked Roles

- Validation is a temporary independent role. It receives frozen inputs, writes
  linked evidence, and exits; it has no durable stateboard yet.
- Infra is invoked for Docker, GPU, dependencies, mounts, storage, CI, and
  runtime reproducibility.
- Throughput Review is an invoked, bounded operating check. It can inspect
  ready work, active-job ownership, resource contention, test feedback latency,
  and worker waits to propose one measured, reversible improvement for a named
  engine loop. It has no stateboard, independent queue, approval authority, or
  strategy/execution authority. At resume or after unexplained foreground idle,
  it records one `ready / owned / due` dispatch fact in `orchestration.md` and
  then exits.
- Review is a lightweight integration checkpoint. Claude challenges the
  bias-prone decision boundaries listed in `AGENTS.md`.

Historical `infra.md` and `review.md` stateboards are retired. Preserve them as
short pointers to Git/external evidence; do not reopen a standing queue without
repeated independent work.

## Capability Reality

- Engine Research has the single-shot
  `thericher-v2-engine-research-agent` worker.
- Data has the single-shot `thericher-v2-data-agent` worker.
- Execution has the goal-owned `kis-paper-canary` recovery worker and the
  `kis-paper-session` Docker worker for a narrow quote-derived virtual-paper
  buy-limit/reconciliation cycle. The latter may be invoked by one scoped local
  schedule; neither is a general scheduler or broker platform.
- Temporary Codex sub-agents can implement or review disjoint role work during
  an active Codex task.
- No repo-owned daemon, autonomous coordinator, or permanent LLM process
  currently exists. Codex may run an external goal-owned schedule under the
  current `AGENTS.md` policy; a schedule is not durable lane identity.

The stateboard is the durable lane identity. A runtime sub-agent or worker is a
bounded executor, not permanent memory.

For a quota, cooldown, or timer wait, the owned worker yields or is scheduled
for its next due time. Codex does not remain in a long foreground sleep while
another lane has ready work.

A genuinely unknown private non-live capability becomes a bounded
Data/Infra-capability probe, not an approval wait. A durable rate, retry, or
timer limit needs a source or measured result and a recalibration fact; an
existing evidence-backed control stays active until that fact changes. A failed
probe is scoped evidence, never a global lane pause.

## Stateboard Shape

Keep only current, high-signal sections:

- status and engine loop,
- ownership and prohibitions,
- resources,
- constrained-resource state and the exact idle reason when it changes the
  next action,
- current objective and ready queue,
- running work,
- operator help,
- durable knowledge,
- recovery,
- a few evidence pointers,
- next handoff.

Replace stale status instead of appending history. Details remain in Git at the
pre-compaction commit `8f416f8` and in external artifacts.

At a bounded handoff, update only the changed objective, ready/running item,
one evidence pointer, recovery class, and next action. This is the durable
handoff needed by the next temporary executor; it is not a per-agent work log.
Searchable run history remains in Git and the external evidence substrate.

## Role Records

Each durable role has a short current stateboard and a shared, searchable work
history. The stateboard answers what can run now and how to recover it. A
source-safe handoff event answers what bounded work happened: role, objective,
run or Git reference, phase, owned resource, recovery class, next action, and
evidence pointer. It must never contain raw data, secrets, account identifiers,
or broker bodies.

Until the shared ledger is implemented, a matching Git commit plus immutable
external receipt is the handoff event's durable evidence. Do not replace it
with per-agent journals, per-agent next-goal files, or a `throughput.md`
stateboard. The invoked Throughput Review writes its one current improvement to
`orchestration.md` and remains deliberately short-lived.

## Shared Memory

Each active role receives logical working-memory, permanent-knowledge, history,
evidence, and recovery views over one planned shared substrate:

```text
D:\thericher-v2\model-artifacts\_control\ledger\YYYY-MM.jsonl
D:\thericher-v2\model-artifacts\_control\catalog.sqlite
```

Until that substrate is implemented, stateboards and exact artifact pointers
are the recovery bridge. Do not create per-agent databases, vector stores,
history documents, daily goal files, or recovery reports.

Focused test feedback may use independent parallel processes or `pytest-xdist`
after the affected tests have no shared mutable artifact, control root, Docker
service, or environment dependency. The required serial `pytest -q` remains
the authoritative goal-boundary verification.

## Lifecycle

Start new work as a temporary role assignment. Create a stateboard only after a
role has a distinct authority boundary and recurring work across multiple Codex
tasks or owns an independent resource. Move an empty role to invoked/standby
status. Retire duplicate or stale roles without deleting the Git history that
explains them. Codex reviews this portfolio at each company-goal boundary and
may make these reversible lifecycle changes without waiting for routine
operator approval; authority, cost, credential, capital, and live-risk changes
still follow `AGENTS.md`.
