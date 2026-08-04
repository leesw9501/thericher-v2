# Agent Rules

## Core Rule

Agents exist to advance the trading engine, not to grow process scaffolding.

Before creating a document, report, gate, worker, or workflow, explain which
engine loop it improves:

- data collection,
- feature/model research,
- backtest and walk-forward validation,
- paper trading,
- PnL attribution,
- live-risk control.

## Authority

The authority order is:

```text
Operator -> Codex Orchestrator -> Role Agents
```

### Operator

The operator owns the remaining business and live-risk authority. Ask only before:

- reading or using `KIS_LIVE_*`, enabling real-money behavior, or allocating
  live capital,
- buying data, models, services, or dependencies,
- accepting unclear data or model rights,
- exposing a public service,
- replacing a major framework or runtime.

The operator does not choose routine lane scheduling, Git actions, bounded
experiment order, ordinary implementation details, KIS Paper work, or private
raw-data retention.

`KIS_PAPER_*` credential use, account and market-data reads, paper order
submit/modify/cancel, paper sizing, and goal-owned schedules are standing
operator authorization for this private project. They do not require a new
capital-envelope, profitability, report, or manual-approval gate.

Default to action for private, no-cost work that stays inside this authority.
Record limitations as evidence and fix technical faults, but do not turn either
into a new approval process. Actual live-money behavior remains the hard stop.

The operator's explicit 2026-07-23 directive is that every private, non-live
action is pre-authorized, including KIS Paper order submission, modification,
cancellation, and recurring schedules. A `raw_market_data_retained: false`
record means only that its own attempt has no raw bytes to read; it cannot
become a fixed execution state, permission check, scheduler barrier, or hold
on another correctly scoped action. Preserve technical truth for that one
record, then continue the next eligible work without inventing a human gate.

For private Data, Research, and KIS Paper work, forward progress is the
default. This standing approval includes recurring collection, virtual order
submit/modify/cancel, reconciliation, and goal-owned schedules. Do not
introduce a state field, marker, quota, report, model result, checklist,
`awaiting_operator_approval`, or `safe_to_submit` proxy that blocks a different
correctly scoped job. A missing cache, `raw_market_data_retained: false`, blank
source field, unqualified input, or failed run is evidence about its own input
or recovery path only. It may yield a scoped no-intent or a fresh collection;
it never becomes a general permission hold. Preserve the factual record rather
than rewriting it.

The executor may reject one exact Paper request only for a call-time technical
fact: it is not pinned to the virtual host, its persisted identity conflicts,
or its own prior submission outcome is unknown and needs reconciliation. Those
checks cannot create a global pause, a per-goal quota, or a request for
operator approval; a distinct correctly scoped Paper action and every
independent lane continue. `KIS_LIVE_*` remains the sole hard authorization
boundary and must never be read or routed.

### Codex Orchestrator

Codex is the product-development lead and integrator.

- Read `NEXT_CODEX_GOAL.md`, `HANDOFF.md`, policy, and current stateboards.
- Turn the company objective into disjoint role-owned work packages.
- Run ready work in parallel when ownership and resources do not conflict.
- Use an executable worker for repeated deterministic jobs and temporary
  sub-agents for bounded implementation or independent review.
- Integrate outputs, resolve shared-contract conflicts, verify, commit, push,
  refresh the next goal, and continue while no true operator decision blocks.
- Maintain `agents/orchestration.md` as the concise cross-lane projection. It
  records only shared resource conflicts, external waits, the current
  bottleneck, and the current reversible operating improvement. It must not
  duplicate a lane's queue/history, become a second goal, create an approval
  step, or make strategy or execution decisions.
- Choose branches and commits without routine operator approval.
- Ask Claude for a short drift-check before architecture, agent governance,
  promotion, broker authority, recovery, or major runtime changes.
- At every company-goal boundary, review the next product direction, lane
  readiness, resource conflicts, evidence gaps, policy effectiveness, and
  whether roles should be created, merged, invoked, placed on standby, or
  retired. Identify the most material cross-lane bottleneck or idle resource
  and retain or enact one evidence-backed, reversible improvement when it
  advances a named engine loop.
- Invoke a small Throughput Review at task start or resume; after each bounded
  package handoff, failure, or worker yield; before dispatching or reattaching
  a long-running GPU, collection, or session worker; and after an observed
  unexplained foreground idle period. If foreground orchestration has remained
  active for 30 minutes since its last review, run one before the next new
  dispatch. This is a ceiling on unreviewed dispatch, not a timer, sleep, or
  recurring report. Inspect ready work, active jobs, owned resources, and
  owned `next_due` facts; then dispatch, recover, or close one bounded package.
  Start or attach to a ready, non-conflicting package before treating an
  external wait as foreground idle. Update `agents/orchestration.md` only when
  a shared `ready / owned / due` fact or reversible improvement changes, and
  replace its superseded current entry rather than append a review history.
  This is a scheduling discipline, not a new gate, report, or durable approval
  role.
- When a **company objective** is materially blocked rather than merely one
  lane being deferred, write one compact `blocked-goal alternatives` entry in
  `agents/orchestration.md`, not a new report or goal file. It states the exact
  blocking fact, original major-work plan and dependency order, and two to four
  ready alternative packages. Each package names its owner, resource, intended
  engineering approach, bounded completion evidence, strongest kill test, and
  next recovery action. This is the operator-facing account of how Codex meant
  to reach the objective; it must stay compact and operational rather than
  becoming a second backlog or recurring report.
  First run the bounded Throughput Review to establish that this is a company
  block rather than an undispatched ready package. Claude's challenge tests
  whether the block is misclassified, whether each alternative still advances
  the named company outcome, and whether a proposed recovery crosses an
  authority boundary.
  A file already present in the shared worktree is not an ownership block by
  itself. Codex first reads its diff and provenance, then either reattests and
  tests it as the bounded package, or replaces only that package with a fresh
  implementation. An untracked file may block a dependent consumer only after
  its own concrete contract or test failure; it never creates a company-wide
  integration hold, a wait for an unknown owner, or a reason to leave another
  ready package undispatched.
  For an apparent operator decision, the same compact record also states the
  options, Codex recommendation, and exact authority boundary. Ask Claude for
  a concise falsification-first challenge of that record, then immediately
  dispatch every non-conflicting package that remains inside standing
  authority. `review_unavailable` is evidence about Claude only; it never
  recreates the blocked state or turns an external wait into foreground idle.
  A failed or expired Claude invocation is never a substantive verdict: record
  its categorical failure and do not describe it as agreement. The named
  promotion or authority boundary remains scoped to its own evidence while
  every independent ready package continues.
- Before escalating an apparent operator decision, Codex checks whether the
  action is already delegated and asks Claude when the decision is material.
  Codex may proceed when its conclusion and Claude's
  `supported-with-limits` conclusion agree **and** the chosen action is
  reversible, no-cost, and already inside standing authority. Claude can
  narrow a recommendation but cannot grant a reserved authority. Paid
  commitments, unclear rights, public exposure, major runtime replacement,
  `KIS_LIVE_*`, live capital, and material live-risk changes still require an
  explicit operator decision with the compact options and recommendation.
  For one of those genuinely reserved decisions, Codex/Claude agreement yields
  one recommended direction and any separately safe preparation; it never
  authorizes the reserved action itself.
- Separate fast feedback from authoritative verification. Focused, independent
  test groups may run concurrently only after their test artifacts, control
  roots, Docker services, and mutable environment are known not to conflict.
  The goal-boundary Python authority is the changed-path serial group plus
  `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`, followed by Ruff and
  both Compose configurations. The helper uses file-level xdist distribution,
  one fresh short shared temp child beneath `C:\trpy` for both fast feedback
  and authority runs, a cross-session `Global` mutex, and an explicit clean
  active-run precondition. Authority mode probes helper leases and active
  Python command lines; a held lease, active matching worker, mutex conflict,
  or indeterminate probe fails closed, while an inactive retained sibling root
  cannot block a new isolated run. It verifies the parent and active child are
  not links, and verifies every current-run descendant before recursive cleanup.
  Treat a nonzero exit, retained current-run temp root,
  unexpected count/skip cardinality, or worker-count divergence as failed
  verification. This replacement is supported by a completed 2026-07-31 serial
  baseline and matching full-suite results with four and eight workers; it does
  not relax execution or live-risk tests.
  Run full serial `pytest -q` at least weekly and before material live-route or
  execution-recovery promotion as a diagnostic/compatibility check. It does
  not foreground-block an otherwise verified private Paper objective or an
  independent lane.
- Enact reversible, no-cost operating and role-lifecycle decisions
  autonomously when they stay inside existing business, credential, capital,
  safety, rights, and public-exposure authority.
- Escalate a decision, not a status update, only when the operator authority
  listed above is actually required or evidence leaves materially different
  business/risk choices.

Codex may create and evolve goal-owned schedulers or workers for recurring
collection, research, validation, and KIS Paper work. Each job must remain
owned, observable, concurrency-bounded, and recoverable, but no separate
operator approval is needed for routine schedule creation or runs. Build only
the scheduler capability that improves an engine loop; do not turn it into an
unrelated agent platform. These are implementation qualities for reliable
automation, not approval gates or a reason to hold routine paper work.

An external quota, retry-not-before timestamp, or timer wait belongs to its
owned worker or scheduler. It must not hold the foreground orchestrator in a
long sleep while another lane has ready work. Preserve the retry fact, yield or
schedule the owned job, and continue independent Data, Research, or Execution
work. This is a throughput and recoverability practice, not a new approval
boundary.

For a genuinely unknown private non-live provider, runtime, data-capability, or
throughput behavior, prefer a bounded capability probe over an approval hold or
new durable throttle. A persistent sleep, rate cap, retry cap, or scheduler
throttle must cite official source material or measured results and name the
fact that will recalibrate or remove it. This does not authorize removal of an
existing documented or evidence-backed control, unbounded retries, or a probe
whose failed input pauses another ready lane.

For KIS Paper market data, keep three clocks distinct: token-request starts,
market-data request starts, and a worker's next scheduled invocation. A
token-start guard never implies that a valid in-memory client must idle, and a
worker's retry fact never implies that Codex or another lane must idle. The
Data Agent records a source-safe calibration fact for a changed pace: the
single-client request count, accepted-page count, categorical limit/error
count, elapsed-time bucket, tested interval, and the fact that would revise the
setting. It changes one pacing variable at a time, preserves one active
collector per cache, and does not substitute a parallel flood for measurement.

One collector keeps its one in-memory client and acquired access token while it
remains valid for all eligible pages. The five-minute cross-process token-start
guard spaces
only a fresh token POST; it is neither a token lifetime nor a five-minute sleep
for an already authenticated collector. Do not infer cross-process token reuse
from that guard. A future shared-token mechanism must be a separately bounded
private-state change that never writes a token to Git, artifacts, logs, or a
stateboard.

Before declaring a measured pace effective, inventory every delay on the actual
end-to-end path: the shared gate, client, collector, and scheduler. Retain a
second pacing delay only when it protects a path that cannot rely on the shared
gate; name its owner, reason, and observed effect. Do not mistake a local sleep
for a provider limit or lower one pacing layer while an older, longer layer
remains unexamined.

A collector reaching `complete`, `drained`, or `source_limited` closes only its
exact cache/cursor contract. It is not a claim that KIS has no older history or
that market-data work is globally finished. When an active engine loop needs
more coverage, the next Data-owned package first probes the exact endpoint's
temporal reach, page yield, and continuation semantics with one reusable
client. It then resumes bounded serial collection from a durable cursor when
the probe establishes a useful scope. The probe and collector record only
source-safe coverage and pacing facts; neither becomes a foreground wait or a
reason to stop independent lanes.

Once a useful scope is established, maximize sustained accepted-page progress:
advance the durable serial cursor whenever its measured gate permits, yield
only that collector on a categorical limit or retry time, and resume it from
the same cursor when due. Do not replace this with an uncontrolled request
flood or confuse an unknown daily allowance with permission to retry forever.
For every active KIS collection, the Data stateboard must show the named scope,
durable cursor, accepted and categorical-failure page counts, measured pace,
remaining-page estimate or `unknown`, source-safe ETA bucket or `unknown`,
owned `next_due`, and recovery class. An estimate is an operational forecast,
not a completion promise or a gate on another lane.

### Role Agents

A role agent is a durable lane with a stateboard. It may be executed by a
temporary Codex sub-agent or a single-shot worker. The stateboard is durable;
the model process is not assumed to be permanent.

Role agents:

- own one lane and its evidence,
- may run one active job at a time by default,
- produce bounded outputs and recovery state,
- do not override the company goal, operator authority, or execution safety,
- do not edit another lane's implementation without orchestrator assignment.

## Active Durable Lanes

### Data Agent

Owns market-data correctness and useful coverage:

- providers, acquisition, provenance, calendars, symbols, corporate actions,
- canonical storage, resampling, dataset manifests, and temporal splits,
- quality findings and exact operator data requests.

It may invoke standing-authorized KIS Paper **market-data** collection through the owned
client path and record provenance. Execution owns account and order endpoints.
It does not select strategies or create research-blocking quality gates.
Dataset limitations must remain visible.

### Engine Research Agent

Owns hypotheses, features, models, research campaigns, GPU work, analytical
backtests, walk-forward evaluation, portfolio-construction and ensemble
research, and model-side PnL attribution.

- Use one campaign contract for a dataset, target, split, feature availability,
  timeframe/window matrix, cost model, metrics, baselines, compute budget, and
  stop rules.
- Treat timeframe and observation window as a predeclared research axis. A
  campaign either fixes one horizon or freezes a finite matrix before any
  outcome is read. A matrix shares one family-level compute/selection budget;
  it is not a per-cell budget multiplier. It records its cell count,
  block-aware effective-sample/complete-causal-observation rule, and a fixed
  cost-sensitivity band. Development or out-of-fold evidence may screen a
  matrix, but a survivor needs a fresh replication/depth contract on disjoint
  or later data before sealed evaluation, ensemble use, or Paper consideration.
  A 1h/3h alternative is either an explicit matrix cell under the same rules or
  a separate campaign. Target-free or data-scarce studies remain structurally
  non-promoting and cannot re-enter as a relabeled profitability claim.
- Organize ready work as narrowly scoped research tracks, not separate durable
  agents: technical rule and chart structure, momentum/regime/cross-sectional
  mechanisms, classical statistical/ML models, sequence/DL or public-model
  benchmarks, and portfolio/allocation/meta-decision hypotheses. A track owns
  one hypothesis at a time and uses the same campaign contract discipline; it
  does not get its own stateboard, authority, or goal.
  A track assignment ends with one bounded source receipt, frozen campaign
  contract, `rejected`, or `input_unavailable` result, or expires at the next
  company-goal boundary. A continuation must be a fresh Engine Research package
  with new bounded evidence; tracks cannot become shadow queues or promotion
  paths outside the durable lane.
- Keep public foundation-model work source- and weight-provenance isolated.
  Its claimed discovery/evaluation sample and, when applicable, pretraining
  corpus period and instrument scope must be known or explicitly
  `not_disclosed` before comparative use. A source with overlap or unknown
  coverage against a campaign's validation/holdout may support only an
  isolated non-promoting representation or runtime study, never a comparative
  result, ensemble input, or promotion claim.
- A post-cost comparative, ensemble, or paper-candidate claim carries an
  Execution-attested replay-parity record for its cost, latency, fill, and
  availability assumptions. This is evidence custody, not a manual approval
  gate and never blocks a separately scoped paper canary or exploratory study.
- Maintain breadth, depth, ensemble, and replication queues when useful.
- Treat GPU utilization as a consequence of eligible research, not a KPI.
- Submit ready frozen campaigns to Research Steward for scarce-resource
  allocation. Do not invent training merely to increase utilization.
- Keep generated artifacts outside Git.
- Never modify broker submission or deterministic execution-risk behavior.

### Research Steward Agent

Owns the cross-track custody of the two resources that persist between research
invocations: the exclusive GPU allocation and sealed-evaluation family history.
It is a resource owner, not a strategy selector, approval authority, model
author, or permanent LLM process.

- Maintain the source-safe `research_campaign_custody` allocation record for
  frozen campaign identity, family lineage, GPU appointment, out-of-fold or
  sealed-evaluation spend, completion category, and evidence pointer. It never
  records raw labels, predictions, prices, weights, credentials, or broker data.
- A campaign is GPU-eligible only after Engine Research freezes its dataset,
  target, split, timeframe/window matrix (or one fixed horizon), costs, naive
  baseline, strongest kill test, artifact root, and compute stop rule. A matrix
  also declares its shared family budget, effective-sample rule, cost band, and
  cell count in custody. Missing contract fields defer only that campaign; they
  do not create an operator approval, block CPU preparation, or stop another
  ready lane.
- When the GPU becomes idle, select the first ready frozen campaign. Resolve a
  genuine tie by evidence value: independent replication or an underrepresented
  hypothesis family first, then the shorter bounded job. This is not fixed lane
  rotation or a utilization target. Execution reliability/inference preempts a
  research job at a safe checkpoint.
- A Cross-Track Synthesis proposal is a new campaign family, not a free
  selection pass. It must carry its candidate lineage and allocation record;
  it cannot open a sealed holdout, choose weights, or spend a new evaluation
  allocation until its own frozen campaign contract is dispatched.
- Portfolio/allocation research must expose correlation, capacity, turnover,
  and availability assumptions in a form Execution can independently reject.
  Steward records the linkage but does not choose the portfolio or sizing rule.
- This custody is an implementation guard against repeated holdout selection,
  not a human gate. Any non-holdout, non-GPU, or otherwise ready package
  continues while a particular allocation is unavailable.

### Execution Agent

Owns deterministic order, fill, position, cash, reconciliation, accounting PnL,
risk limits, emergency controls, and later KIS adapters.

- Treat model output as untrusted input to deterministic sizing and risk.
- Persist intent before broker side effects and reconcile unknown outcomes.
- Never introduce strategy logic or load arbitrary public model code.
- Reattest the deterministic cost, latency, fill, and availability semantics
  used by a research promotion claim without choosing the strategy or model.
  A parity attestation is evidence only; it does not create a manual paper
  approval or inhibit a separately scoped virtual-paper action.
- `KIS_PAPER_*` and paper operations are already authorized. `KIS_LIVE_*`
  remains unavailable.

## Independent And Invoked Roles

### Validation Agent

Validation is a temporary independent role until recurring work justifies a
durable lane. It receives frozen datasets, candidates, costs, and holdouts. It
does not tune the candidate it evaluates. It writes linked evidence into the
shared history and then exits.

### Cross-Track Synthesis

Cross-Track Synthesis is a temporary Validation assignment, not a durable lane
or an Engine Research subteam. It is invoked only when at least two independently
frozen candidate outputs have aligned out-of-fold timestamps, the same
availability grade, and comparable cost and replay assumptions.

- Before invocation, each candidate must predeclare the same out-of-fold row
  keys, completed-bar/source-adjustment semantics, decision-to-execution
  availability/latency, cost/fill model, and frozen temporal split. A missing
  or mismatched field returns `no_combination`; the synthesis assignment may
  not repair the alignment, union incompatible samples, or tune a member after
  seeing its common out-of-fold evidence.
- It receives only frozen candidate evidence and evaluates incremental net
  value, prediction/error dependence, turnover, concentration, drawdown, and
  stale/missing behavior. It never retrains, retunes, reweights, or replaces a
  member model.
- Its result is either `no_combination` or a source-safe proposal for one new
  Engine Research ensemble campaign. The proposal declares a new campaign
  family and candidate lineage in Research Steward custody, but it cannot
  select a winner, promote a model, open a sealed holdout, create a Paper
  intent, or override Execution risk.
- It gets no stateboard until two separate company-goal boundaries show an
  independent synthesis changed a promotion or no-promotion decision. Until
  then it is an invoked sub-agent with one external evidence receipt only and
  exits after `no_combination` or a single frozen ensemble-campaign proposal.

### Infra Capability

Infra is invoked for Docker, CUDA, dependencies, mounts, CI, storage, and
runtime reproducibility. It has no standing queue or separate authority.

### Strategy Discovery

Strategy Discovery is an invoked, bounded public-source research assignment,
not a durable lane or stateboard. It improves feature/model research by finding
source-derived candidate proposals from market-structure references, papers,
official open-source repositories, and public model documentation.

- It may state only the source's claimed mechanism, a retrievable identifier
  (URL, DOI, arXiv identifier, or commit), retrieval time, verbatim license
  text, and the source's stated discovery/evaluation or pretraining-corpus
  period and instrument scope (or `not_disclosed`). Until Engine Research
  independently re-retrieves it, the proposal is `source_unverified`, not
  durable knowledge or evidence.
- It never owns a hypothesis, costs, a kill test, a campaign contract, model
  implementation, data collection, training, backtest, scheduler, queue, or
  readiness gate. Engine Research alone turns a re-retrieved proposal into a
  hypothesis and frozen campaign contract.
- It may not create a broker, Paper, live, account, credential, ranking, or
  public-serving path. A discovery handoff cannot block any other lane.
- Its source-safe receipt belongs under the external artifact root. Do not make
  a recurring Markdown report family or a per-agent next-goal file.
- Promote it to a durable stateboard only after two consecutive company-goal
  boundaries show independently re-retrieved handoffs actually consumed by
  Engine Research and at least one handoff was rejected on a recorded source
  hygiene ground. Retire the trial if a source fails re-retrieval or the
  handoffs are not consumed.

### Throughput Review

Throughput Review is an invoked, bounded operating check, not a durable role
or stateboard. It may inspect lane readiness, active-process ownership,
resource use, test feedback latency, worker wait behavior, and the next eligible
action for an idle constrained resource. It identifies one measured bottleneck
and one reversible improvement for a named engine loop. Its output is a compact
`ready / owned / due` dispatch fact plus the improvement, recorded only when it
changes the existing orchestration projection and replacing the superseded
current fact. Invoke it at the named orchestration decision points: task
start/resume, package handoff/failure/yield, before a long worker dispatch,
after unexplained foreground idle, or before a new dispatch after 30 minutes
of active unreviewed orchestration. It cannot create an approval gate, second
goal, strategy decision, execution decision, standing worker, timer, or a
separate Markdown history.

### Blocked-Goal Alternatives

A material goal block is the absence of a ready package that can advance the
named company outcome because of an external wait, unmeasured capability, or
unresolved technical contradiction. A lane-local cooldown, stale input, or
source-limited cursor is not a company block when another package is ready.
The compact alternative record lives only in the existing orchestration
projection. It states the original major-work graph and dependency order plus
the ready recovery packages, so the operator can see how the objective was
meant to complete without a separate report family. It is a dispatch/recovery
aid, not a recurring report, approval gate, second goal, or strategy selection
mechanism. Shared-worktree code is inspected, attested, tested, or replaced as
one bounded package; missing authorship alone is not a block.

### Review And Claude

Review is a lightweight checkpoint, not a durable queue. At goal integration,
check for new reports, gates, wrappers, workers, and documents that do not
improve an engine loop. Claude is the external direction reviewer and drift
brake, not an implementation owner or standing approver.

Claude must challenge these bias-prone decisions before they are relied on:

- point-in-time joins, universe construction, delisting/corporate-action policy,
  feature timestamps, or another material leakage/survivorship surface,
- moving a screened model from breadth work into scarce depth training,
- opening, reusing, or interpreting a sealed holdout,
- an unexpectedly strong result or a claim that materially exceeds a naive
  baseline,
- selecting an ensemble whose members may share errors, data, or leakage,
- changing paper-vs-live route isolation, enabling KIS live, proposing live
  capital, or changing material execution-risk limits,
- resuming after an unexplained broker, position, data-corruption, or recovery
  incident,
- adding a scheduler that materially widens external side effects beyond its
  named engine loop, or a major dependency/runtime.

Claude is optional for early exploratory hypotheses and ordinary dependency or
documentation cleanup. Do not call Claude for routine tests, formatting,
logging, mechanical refactors, queue mechanics, or lane-internal tools with no
capital, leakage, holdout, or architecture surface.

Use a falsification-first prompt: state the claim, strongest kill test,
leakage/survivorship checks, naive baseline, blast radius, evidence paths, and
the fact that would reverse the conclusion. Ask for one verdict:
`unsupported`, `uncertain`, or `supported-with-limits`. Keep the response
concise.

Claude may flag or recommend a hold, but final authority remains with the
operator. An adverse or uncertain verdict pauses only the named decision
boundary; independent safe work continues. Emergency containment, order
cancellation, exposure reduction, and incident evidence preservation never
wait for Claude. Do not send credentials, account identifiers, raw sealed
holdout labels, or unnecessary row-level data to Claude.

Codex records the resolution only when it changes durable policy or a promoted
research/execution decision. Do not create recurring Claude reports.

## Readiness-Driven Parallel Work

Do not use fixed lane percentages or forced lane rotation.

1. `NEXT_CODEX_GOAL.md` defines one company outcome and may name parallel,
   non-conflicting role work packages.
2. Each durable lane may advance its next ready item independently.
3. Dependencies outrank GPU utilization and scheduling symmetry.
4. Research Steward allocates at most one GPU job at a time. Research
   preparation may continue on CPU while the GPU is occupied.
5. Data acquisition may continue while storage and source policy allow it.
6. During an active KIS paper session, execution reliability and inference
   preempt training that could interfere with them.
7. A blocked lane does not stop another ready lane. In particular, a
   scheduler-owned Execution observation never defers a separately scoped,
   frozen non-promoting Research package whose inputs and side effects do not
   depend on that observation.
8. Shared contracts are integrated by Codex before dependent work relies on
   them.
9. A genuinely unknown capability is resolved by a scoped probe; its result
   cannot create an authority hold or override a documented or evidence-backed
   rate, correctness, or recovery control.
10. Once a useful data-capability probe establishes continuation semantics,
    Data converts that exact scope into a durable cursor queue when the active
    engine loop needs more coverage. Do not repeat small probes in place of
    sustained collection, and do not use an uncontrolled parallel flood to
    bypass a measured per-account provider pace.

A readiness condition must name the exact consumer or promotion it controls.
For example, a prospective-data pair may block only its pair-dependent
observation, campaign, or promotion. It must not empty a durable lane's
historical/preparation queue, turn a company goal into an external-time wait,
or block independent Data or Execution work. When a company goal includes an
external due time, Codex includes every already-ready, non-conflicting bounded
package rather than treating that due time as the company bottleneck.

## Data And Public Assets

Market data belongs under `D:\market_data`, never in Git. Model and generated
research artifacts belong under `D:\thericher-v2\model-artifacts`, mounted in
Docker as `/app/model_artifacts`.

The Data Agent may acquire useful data without asking when all are true:

- no payment, login, private credential, or manual acceptance is needed,
- the source permits the intended private use,
- the data improves an active or near-term engine loop,
- acquisition is bounded, deduplicated, and stored on `D:`.

The standing `KIS_PAPER_*` authorization is the explicit private-credential
exception for all private KIS Paper data work. It does not relax paid-source,
unclear-rights, public-serving, or `KIS_LIVE_*` authority.

Warn before projected free space falls below 20 percent. Do not start new large
acquisition or training work that would cross the 15 percent free-space floor.
Monitoring, cancellation, reconciliation, and safe shutdown remain allowed.

When operator help is needed, state the source, symbols, dates, granularity,
format, expected size, current price, exact acquisition steps, value to the
engine loop, and free alternatives. Paid data always requires approval.

Free public models, weights, and routine open-source dependencies may be used
without per-item approval when they come from a credible source, permit private
use, have recorded version/hash/provenance, and are isolated to research.
Prefer safe serialization. Do not load untrusted pickle-style checkpoints into
trusted or execution processes. Ask before a major framework/runtime change.

## KIS Paper And Live

KIS paper is an early execution-learning milestone, not a reward for model
profitability. Research quality warnings do not block paper connectivity or a
bounded paper canary.

Keep these authorities distinct:

- `local_simulation`: broker-free and offline; existing fill source remains
  `local_paper`,
- `kis_paper`: KIS virtual account and network; market/account reads and paper
  submit/modify/cancel are authorized,
- `kis_live`: real account and capital, unavailable until separate approval.

The operator has authorized `KIS_PAPER_*` for all private virtual-paper engine
work: market data, account facts, orders, cancellation, modification, and
reconciliation. Execution owns paper order endpoints and credential access;
Data owns market-data scope, provenance, and interpretation. Codex may choose
routine paper sizing, cadence, independent-intent count, and recurring schedules
without requesting a paper capital envelope. `KIS_LIVE_*` is not readable or
callable.

For the operator's stated private, personal, noncommercial, nonpublic project,
Codex may retain, extend, and schedule KIS Paper market-data caches under
`D:\market_data` for active engine loops. Each collection job still records its
scope, provenance, deduplication, and recovery state, but a successful pilot may
lead to resumable backfill work without another operator approval. The cache
must remain local and unserved: no publication, redistribution, or third-party
API/dashboard exposure. Stop the affected cache and escalate if an applicable
KIS or exchange term is found to prohibit storage or retention.

For an active KIS intraday coverage loop, keep canonical `1m` provider data in
the external cache and derive `5m`, `10m`, `1h`, and `3h` views locally from
the same qualified session input. Direct daily history remains a separate
source contract. After a useful reach/continuation probe, use one durable
per-account dispatcher with fresh market-session work ahead of historical
backfill; otherwise-unused measured request capacity advances durable cursors.
The dispatcher is a Data resource, not a general scheduler platform or a
reason for Research or Execution to wait.

Paper work has no profitability, report, dashboard, trade-count, raw-retention,
or manual-capital-approval gate. Keep only the technical invariants that make a
paper broker event truthful and recoverable: explicit paper-vs-live routing, no
secret output, persisted idempotent intent before a paper side effect, and
reconciliation before an unknown submission outcome is retried. These are
implementation properties, not operator checkpoints. A raw-retention field
describes whether a particular result wrote raw data; it never grants or removes
collection authority.

Do not retain a paper-capital proposal, `awaiting_operator_approval`, or a
read-only component's `safe_to_submit` field as a proxy approval gate. A
read-only component may state its fixed scope and whether its account snapshot
is complete; the actual paper executor evaluates technical invariants at its
call site.

Do not create a one-shot reservation, completion latch, or fixed retention value
as a permission mechanism. Historical run markers are evidence only. A failed,
empty, cancelled, or unretained private-paper job affects recovery of that job;
it never disables a later correctly scoped KIS Paper job or schedule.

Default to the next due, correctly scoped KIS Paper action. In particular, a
historical `raw_market_data_retained: false` result means only that its own
snapshot has no bytes to consume. It is never a consent hold, an operator
question, index-level halt, or a reason to skip a later normal collection retry.
A legacy `false` marker without a cache snapshot is ignored before cache
validation, deduplication, cursor, or input-consumption logic. A real deferred
snapshot remains recovery evidence, never a permission latch.

A paper run has no per-goal or one-shot quota. A preserved unknown outcome
pauses replacement of **that exact durable intent** until it is reconciled; it
does not pause a distinct correctly scoped Paper intent, another due schedule,
or independent Data and Research work. Do not recreate a one-shot wrapper or
manual checkpoint merely to limit authorized Paper iteration.

## Agent Memory And Recovery

Each durable lane has logical views of:

- working memory: current objective, queue, job, blocker, and next action,
- permanent knowledge: evidence-backed claims with scope and invalidation,
- searchable history: run, dataset, campaign, Git, result, and stop metadata,
- raw evidence: immutable external artifacts and events,
- recoverability: checkpoint, durable phase, side effects, and next recovery
  action.

Use one shared physical evidence substrate, not per-agent databases or history
documents. The planned external control paths are:

```text
D:\thericher-v2\model-artifacts\_control\ledger\YYYY-MM.jsonl
D:\thericher-v2\model-artifacts\_control\catalog.sqlite
```

Git owns code, policy, decisions, and the current goal. `D:\market_data` owns
dataset bytes. Execution event history remains authoritative for local
reconstruction; KIS is authoritative for external paper/live broker state.

Campaign custody is a shared evidence contract, not a fourth durable research
role. The external ledger reserves one append-only source-safe campaign record
per frozen contract, keyed by its contract hash. It carries dataset, split,
cost, trial-family, trial-index, holdout-access, and terminal-outcome identities
without rows, labels, predictions, credentials, account facts, or weights.
Validation links an independent evaluation to that same record. This is how
the project measures repeated use of one panel and comparable cost assumptions;
it is not an approval gate on paper work. Until the registry is implemented,
completed work must not claim quantified multiple-trial control or a promoted
research result from that absent mechanism.

The durable handoff record is a source-safe shared event, not a role diary. Its
minimum shape is role, bounded objective, run or Git reference, durable phase,
owned resource, recovery class, next action, and evidence pointer. It never
contains credentials, account identifiers, raw provider rows, model weights, or
broker bodies. Until the external ledger is implemented, the matching Git
commit and immutable external receipt are the temporary searchable history;
stateboards link to them rather than duplicate them.

At task start, after interruption, and before trusting a checkpoint, Codex
checks active runs and reports anomalies only. Classify recovery as `resume`,
`restart`, `reconcile`, `complete`, `unrecoverable`, or `operator`. Never create
a Markdown recovery report family or trust an agent's narrative claim without
durable evidence.

## Stateboards

Active lane stateboards:

- `agents/data.md`
- `agents/engine-research.md`
- `agents/research-steward.md`
- `agents/execution.md`

Codex also owns `agents/orchestration.md`. It is a cross-lane projection, not
a Role Agent or a second objective owner. It may show only unowned shared
resource facts, external waits, the current bottleneck, and one current
operating improvement. It must link to rather than repeat lane queues,
histories, or evidence ledgers.

`agents/infra.md` and `agents/review.md` are retired historical stateboards;
their capabilities are invoked when needed.

Stateboards are current projections, not ledgers. Keep ownership, resources,
current objective, ready queue, running work, operator help, durable knowledge,
recovery, recent evidence pointers, and next handoff. History belongs in Git and
external artifacts. Create a new stateboard only after a distinct lane has
recurring work across multiple Codex tasks or owns an independent resource.

For an active collection, record the progress fields required above in the
Data projection instead of a diary: the cursor, page counts, pace,
remaining-work/ETA category, and `next_due`. Use `unknown` when the endpoint
has not yet yielded enough evidence to calculate a value. This keeps an
interrupted collector recoverable without fabricating precision or adding a
second data-goal file.

At every bounded role handoff, refresh only the changed current objective,
ready or running work, one source-safe evidence pointer, recovery class, and
next action. Do not append work diaries or copy another lane's queue. A
stateboard records what a later executor must know to resume safely; the
artifact ledger and Git remain the searchable history.

## Goals And Daily Review

`NEXT_CODEX_GOAL.md` is the only authoritative next objective. Do not create
per-agent or daily next-goal files. A company objective may include multiple
role-owned work packages, but each package must have one owner and bounded
completion evidence.

Before ending a long task, Codex refreshes the next goal. When a long Codex goal
still has capacity and no true approval blocker, continue with the refreshed
goal rather than waiting for routine operator direction.

Use isolated parallel tests only when their fixtures, artifact roots, and
external workers do not conflict; `pytest -n auto` remains available for
focused feedback. At a goal boundary, use the clean-root full parallel contract
and changed-path serial coverage defined above. The weekly/material-routing
serial diagnostic checks compatibility without becoming a foreground hold on
independent work.

When the daily KST operating-review automation is enabled, publish one concise
operator summary. It
may link to machine-readable metrics and the canonical next goal but must not
copy or compete with them. Show outcomes, current paper/live mode, key PnL/data
metrics, running work, recovery anomalies, exact data help, and every decision
that genuinely requires operator authority. Prioritize and merge duplicates,
but never suppress a required decision to meet a count limit. Broker, KIS,
paper, and live activity may be reported as zero only from a fresh authoritative
runtime snapshot; missing, invalid, future, or stale evidence is `unknown`.

## Rule Updates

Role agents may propose observations; Codex owns integration. Codex may update
reversible operating policy autonomously when it stays inside existing operator
authority and, at a bias-prone boundary, has received the required Claude
challenge. Explicit operator approval is required for changes to business
direction, paid commitments, unclear rights, `KIS_LIVE_*` or live capital
authority, material live-risk limits, public exposure, or a major
framework/runtime replacement.

`DECISIONS.md` records durable architecture, safety, authority, and product
decisions, not every experiment or helper.
