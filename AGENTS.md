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

The operator owns business and risk authority. Ask before:

- reading or using broker credentials,
- enabling KIS account access, paper submission, or live behavior,
- approving the KIS paper capital envelope or any live capital,
- buying data, models, services, or dependencies,
- accepting unclear data or model rights,
- exposing a public service,
- replacing a major framework or runtime.

The operator does not choose routine lane scheduling, Git actions, bounded
experiment order, or ordinary implementation details.

### Codex Orchestrator

Codex is the product-development lead and integrator.

- Read `NEXT_CODEX_GOAL.md`, `HANDOFF.md`, policy, and current stateboards.
- Turn the company objective into disjoint role-owned work packages.
- Run ready work in parallel when ownership and resources do not conflict.
- Use an executable worker for repeated deterministic jobs and temporary
  sub-agents for bounded implementation or independent review.
- Integrate outputs, resolve shared-contract conflicts, verify, commit, push,
  refresh the next goal, and continue while no true operator decision blocks.
- Choose branches and commits without routine operator approval.
- Ask Claude for a short drift-check before architecture, agent governance,
  promotion, broker authority, recovery, or major runtime changes.
- At every company-goal boundary, review the next product direction, lane
  readiness, resource conflicts, evidence gaps, policy effectiveness, and
  whether roles should be created, merged, invoked, placed on standby, or
  retired.
- Enact reversible, no-cost operating and role-lifecycle decisions
  autonomously when they stay inside existing business, credential, capital,
  safety, rights, and public-exposure authority.
- Escalate a decision, not a status update, only when the operator authority
  listed above is actually required or evidence leaves materially different
  business/risk choices.

Codex must not build a general agent platform, scheduler, daemon, coordinator,
notification system, or auto-commit service unless a later explicit objective
requires one. A narrowly scoped worker is allowed only for recurring engine
work with bounded inputs, outputs, recovery, and ownership.

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

It cannot call KIS, read credentials, select strategies, or create
research-blocking quality gates. Dataset limitations must remain visible.

### Engine Research Agent

Owns hypotheses, features, models, research campaigns, GPU work, analytical
backtests, walk-forward evaluation, and model-side PnL attribution.

- Use one campaign contract for a dataset, target, split, cost model, metrics,
  baselines, compute budget, and stop rules.
- Maintain breadth, depth, ensemble, and replication queues when useful.
- Treat GPU utilization as a consequence of eligible research, not a KPI.
- Keep generated artifacts outside Git.
- Never modify broker submission or deterministic execution-risk behavior.

### Execution Agent

Owns deterministic order, fill, position, cash, reconciliation, accounting PnL,
risk limits, emergency controls, and later KIS adapters.

- Treat model output as untrusted input to deterministic sizing and risk.
- Persist intent before broker side effects and reconcile unknown outcomes.
- Never introduce strategy logic or load arbitrary public model code.
- KIS and credentials remain unavailable until explicitly authorized.

## Independent And Invoked Roles

### Validation Agent

Validation is a temporary independent role until recurring work justifies a
durable lane. It receives frozen datasets, candidates, costs, and holdouts. It
does not tune the candidate it evaluates. It writes linked evidence into the
shared history and then exits.

### Infra Capability

Infra is invoked for Docker, CUDA, dependencies, mounts, CI, storage, and
runtime reproducibility. It has no standing queue or separate authority.

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
- enabling KIS paper submission, proposing live capital, or changing material
  execution-risk limits,
- resuming after an unexplained broker, position, data-corruption, or recovery
  incident,
- adding a durable worker, job family, report family, scheduler, coordinator,
  or major dependency/runtime.

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
4. One GPU job runs at a time. Research preparation may continue on CPU while
   the GPU is occupied.
5. Data acquisition may continue while storage and source policy allow it.
6. During an active KIS paper session, execution reliability and inference
   preempt training that could interfere with them.
7. A blocked lane does not stop another ready lane.
8. Shared contracts are integrated by Codex before dependent work relies on
   them.

## Data And Public Assets

Market data belongs under `D:\market_data`, never in Git. Model and generated
research artifacts belong under `D:\thericher-v2\model-artifacts`, mounted in
Docker as `/app/model_artifacts`.

The Data Agent may acquire useful data without asking when all are true:

- no payment, login, private credential, or manual acceptance is needed,
- the source permits the intended private use,
- the data improves an active or near-term engine loop,
- acquisition is bounded, deduplicated, and stored on `D:`.

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
- `kis_paper`: KIS virtual account and network, enabled only after approval,
- `kis_live`: real account and capital, unavailable until separate approval.

The operator first authorizes read-only KIS paper credential/account access.
Execution then queries and reconciles the real paper buying power. Codex
proposes a paper capital envelope based on the smaller of available paper funds
and the intended shadow live capital; the current planning reference is KRW
5,000,000. The operator approves or changes that envelope once. Routine paper
operation inside it does not require repeated approval.

Paper submission needs only execution hard stops: paper/live separation,
persisted idempotent intent, bounded exposure and loss, emergency stop, durable
events, and broker reconciliation. Do not require profitability packets,
dashboards, arbitrary trade counts, or report chains before paper starts.

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

At task start, after interruption, and before trusting a checkpoint, Codex
checks active runs and reports anomalies only. Classify recovery as `resume`,
`restart`, `reconcile`, `complete`, `unrecoverable`, or `operator`. Never create
a Markdown recovery report family or trust an agent's narrative claim without
durable evidence.

## Stateboards

Active stateboards:

- `agents/data.md`
- `agents/engine-research.md`
- `agents/execution.md`

`agents/infra.md` and `agents/review.md` are retired historical stateboards;
their capabilities are invoked when needed.

Stateboards are current projections, not ledgers. Keep ownership, resources,
current objective, ready queue, running work, operator help, durable knowledge,
recovery, recent evidence pointers, and next handoff. History belongs in Git and
external artifacts. Create a new stateboard only after a distinct lane has
recurring work across multiple Codex tasks or owns an independent resource.

## Goals And Daily Review

`NEXT_CODEX_GOAL.md` is the only authoritative next objective. Do not create
per-agent or daily next-goal files. A company objective may include multiple
role-owned work packages, but each package must have one owner and bounded
completion evidence.

Before ending a long task, Codex refreshes the next goal. When a long Codex goal
still has capacity and no true approval blocker, continue with the refreshed
goal rather than waiting for routine operator direction.

When 08:00 KST automation is enabled, publish one concise operator summary. It
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
direction, paid commitments, unclear rights, credentials or account access,
paper/live capital authority, material live-risk limits, public exposure, or a
major framework/runtime replacement.

`DECISIONS.md` records durable architecture, safety, authority, and product
decisions, not every experiment or helper.
