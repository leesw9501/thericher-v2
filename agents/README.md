# Agent Stateboards

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the company objective. These
files are concise current projections for durable role lanes; they are not
reports, policy sources, or historical ledgers.

## Operating Model

```text
Operator -> Codex Orchestrator -> Role Agents
```

Codex decomposes one company objective into disjoint work packages and assigns
them to ready roles. Data, Research, Research Steward, and Execution may
progress in parallel. A blocked lane does not stop another ready lane. Codex
integrates shared contracts, verification, Git, recovery, and the next
objective.

## Team Directory

Canonical English role identifiers remain the only keys in code, ledger
records, paths, and policies. The Korean names below are display aliases for
operator conversation and concise reports.

| Operator name | Canonical role | Stateboard | Primary responsibility |
| --- | --- | --- | --- |
| Product Development Lead (`제품개발 총괄`, `총괄`) | Codex Orchestrator | `orchestration.md` | Decompose work, integrate evidence, resolve cross-lane conflicts, verify, commit, and continue the company objective. |
| Market Data (`시장데이터 담당`, `데이터`) | Data Agent (`data`) | `data.md` | Acquire, qualify, store, and expose useful market-data inputs. |
| Trading Engine Research (`매매 엔진 연구 담당`, `엔진`) | Engine Research Agent (`engine_research`) | `engine-research.md` | Test hypotheses, features, rules, ML/DL models, portfolios, and attribution. |
| Research Resource and Evaluation (`연구 자원 및 평가 관리자`, `GPU/평가`) | Research Steward Agent (`research_steward`) | `research-steward.md` | Allocate the exclusive GPU and protect campaign-family and sealed-evaluation custody. |
| Paper Execution (`페이퍼 실행 담당`, `실행`) | Execution Agent (`execution`) | `execution.md` | Own deterministic simulation, KIS Paper routes, reconciliation, accounting, and risk behavior. |

Temporary assignments keep their canonical names and have no standing
stateboard: Validation (`독립 검증 담당`), Cross-Track Synthesis (`통합 연구
검증`), Strategy Discovery (`전략 탐색 담당`), Infra Capability (`기술 환경
담당`), Review and Claude (`반증 검토`), and Throughput Review (`진행 효율
점검`). They report through their invoking durable role and exit after their
bounded evidence is delivered.

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
  backtests, walk-forward validation, analytical attribution, and the named
  rule/chart, momentum/regime, classical ML, sequence/DL, and
  portfolio/allocation research tracks.
- `research-steward.md`: source-safe cross-track custody for the exclusive GPU,
  campaign families, and sealed-evaluation allocation. It cannot select a
  strategy, tune a model, or create an operator approval step.
- `execution.md`: local simulation, account/order/fill/position contracts,
  reconciliation, accounting PnL, risk, emergency behavior, and later KIS.
  It also independently reattests the execution-cost parity of any promoted
  Research claim without selecting the strategy.
- `orchestration.md`: Codex-owned cross-lane resource and throughput view; not
  a Role Agent, implementation queue, or historical ledger.

Research tracks remain queues inside `engine-research.md`; they are not durable
agents. Research Steward is durable because it owns a cross-track mutable
resource and evidence that must survive between objectives. Strategy Discovery,
Validation, and Cross-Track Synthesis remain invoked until their work itself
meets that same boundary.

## Independent And Invoked Roles

- Validation is a temporary independent role. It receives frozen inputs, writes
  linked evidence, and exits; it has no durable stateboard yet.
- Infra is invoked for Docker, GPU, dependencies, mounts, storage, CI, and
  runtime reproducibility.
- Strategy Discovery is an invoked public-source research assignment. It can
  produce a source-derived candidate proposal, but Engine Research alone may
  turn that proposal into a hypothesis or campaign. It has no stateboard until
  two consecutive goal boundaries show independently re-retrieved proposals
  being consumed and one source-hygiene rejection demonstrates that the intake
  is discriminating.
- Cross-Track Synthesis is an invoked temporary Validation assignment. It sees
  only aligned frozen out-of-fold evidence from two or more candidates and can
  propose, but never tune or promote, one ensemble campaign. It has no
  stateboard until repeated independent synthesis changes a promotion decision.
- Throughput Review is an invoked, bounded operating check. It can inspect
  ready work, active-job ownership, resource contention, test feedback latency,
  and worker waits to propose one measured, reversible improvement for a named
  engine loop. It has no stateboard, independent queue, approval authority, or
  strategy/execution authority. Codex invokes it at task start/resume, each
  bounded package handoff/failure/yield, before a long GPU/collection/session
  dispatch, after unexplained foreground idle, or before a new dispatch after
  30 minutes of active unreviewed orchestration. This is event-driven rather
  than a timer. It updates `orchestration.md` only when a current `ready /
  owned / due` fact or reversible improvement changes, then exits.
- Review is a lightweight integration checkpoint. Claude challenges the
  bias-prone decision boundaries listed in `AGENTS.md`.

Historical `infra.md` and `review.md` stateboards are retired. Preserve them as
short pointers to Git/external evidence; do not reopen a standing queue without
repeated independent work.

## Capability Reality

- Engine Research has the single-shot
  `thericher-v2-engine-research-agent` worker.
- Research Steward has no independent worker, coordinator, model runtime, or
  broker route; Codex invokes its bounded allocation work against the shared
  external custody record.
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

Replace stale status instead of appending history. Details remain in Git history
and in external artifacts.

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

Until a generic role-handoff record is implemented in the shared ledger, a
matching Git commit plus immutable external receipt is the handoff event's
durable evidence. Do not replace it with per-agent journals, per-agent
next-goal files, or a `throughput.md` stateboard. The invoked Throughput Review
writes its one current improvement to `orchestration.md` and remains
deliberately short-lived.

## Operator Activity Reports

When the operator asks `에이전트별 활동사항 보고해`, Codex prepares one concise,
source-safe report for the previous 72 hours by default, or for a requested
period. It reads the durable role stateboards for current work and recovery,
then matches them to recent Git commits and linked external evidence. The
report gives each durable role's completed or advanced work, material
difficulty, material recovery, and next ready action or owned external wait.

Record a resolved problem only when its cause, repair, or prevention is useful
to a later recovery. Keep it to the current stateboard's recovery/evidence
pointer and the matching Git or artifact reference; do not append a narrative
role diary. A report is delivered in the current chat and is not written back
to a stateboard, Git, or a new report artifact family. It must never include
credentials, account identifiers, raw provider rows, model weights, or broker
payloads.

At a bounded role handoff, Codex refreshes the changed stateboard's current
objective, recovery class, next action, and evidence pointer. Git retains its
older stateboard snapshots, while immutable external artifacts retain the
underlying evidence. This is the long-term reporting and recovery history until
a source-safe generic handoff record is added to the existing shared external
ledger with a tested schema; do not create a separate per-agent history store.

A GPT or Codex scheduled task may prompt this same on-demand report every two
or three days, but the chat is a delivery channel rather than the historical
source of truth. The schedule must not create a second goal, report artifact,
or approval gate.

## Shared Memory

Each active role receives logical working-memory, permanent-knowledge, history,
evidence, and recovery views over one planned shared substrate:

```text
D:\thericher-v2\model-artifacts\_control\ledger\YYYY-MM.jsonl
D:\thericher-v2\model-artifacts\_control\catalog.sqlite
```

Until generic role handoffs are implemented in that substrate, stateboards and
exact artifact pointers are the recovery bridge. Do not create per-agent
databases, vector stores, history documents, daily goal files, or recovery
reports.

Focused test feedback may use independent parallel processes or `pytest-xdist`
after the affected tests have no shared mutable artifact, control root, Docker
service, or environment dependency. At a goal boundary, follow `AGENTS.md`:
run the changed-path serial group and the clean-root full parallel runner, then
Ruff and both Compose configurations. Full serial `pytest -q` remains a weekly
and material-routing compatibility diagnostic.

## Lifecycle

Start new work as a temporary role assignment. Create a stateboard only after a
role has a distinct authority boundary and recurring work across multiple Codex
tasks or owns an independent resource. Move an empty role to invoked/standby
status. Retire duplicate or stale roles without deleting the Git history that
explains them. Codex reviews this portfolio at each company-goal boundary and
may make these reversible lifecycle changes without waiting for routine
operator approval; authority, cost, credential, capital, and live-risk changes
still follow `AGENTS.md`.
