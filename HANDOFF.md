# TheRicher v2 Handoff

Use this as the current company-state projection. Git holds prior policy and
code history; `D:` roots hold raw data and generated evidence.

## Start Here

Repository: `C:\Users\Public\Documents\thericher-v2`

Run:

```powershell
.\scripts\start_next_codex_task.ps1
```

Then follow `NEXT_CODEX_GOAL.md`. Authority is:

```text
Operator -> Codex Orchestrator -> Role Agents
```

Codex assigns disjoint Data, Engine Research, and Execution work, integrates
the results, verifies, commits, pushes, refreshes the next single objective,
and continues without waiting for routine direction.

## Product Direction

The product is a private engine that can learn toward repeatable US-equity
profits. Its loop is data -> features/models -> realistic validation -> KIS
Paper -> PnL attribution -> cautiously considered live capital.

The target architecture is a target-position policy graph:

```text
opportunity selection -> per-symbol multi-timeframe evidence
                      -> enter / hold / reduce / exit policy
current positions ----> target-weight allocation
target deltas --------> deterministic risk -> persisted broker intent
```

The graph is developed incrementally so PnL can identify whether selection,
timing, sizing, exits, or fills caused a result. Research evidence improves
claims; it is not an approval chain for virtual-paper work.

## Standing Authority

- All private `KIS_PAPER_*` work is authorized: market and account reads,
  positions, open orders, submit/modify/cancel, reconciliation, routine paper
  sizing, raw market-data retention on `D:`, and goal-owned schedules.
- Do not ask the operator again for paper capital, a report, dashboard state,
  a trade count, profitability, or an individual KIS Paper call.
- `KIS_LIVE_*` must never be read. Existing and future KIS clients must be
  hard-wired to the virtual-paper host and reject a live route.
- Data and models stay local and private: raw market data in `D:\market_data`,
  generated artifacts in `D:\thericher-v2\model-artifacts`, never in Git.
- Do not buy data or services, accept unclear rights, or publish a service
  without a separate operator decision. These are the remaining business
  boundaries, not paper-development gates.

Technical controls remain mandatory because they make paper evidence usable:
paper-only route selection, no secret output, idempotent intent before a broker
side effect, and reconciliation before retrying an unknown outcome. They are
implementation requirements, not approval checkpoints.

## Current Data State

`kis-paper-private-daily-backfill-v1` is the active KIS-native daily cache:

- cache/index: `D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json`
- data-bearing mappings: `QQQ/NAS`, `SPY/AMS`, and `IWM/AMS`
- usable chunks: QQQ five committed, SPY six committed, IWM three committed
  plus one hash-attested partial page; deferred snapshots remain evidence only
- current common intersection: 694 completed sessions
- stored fields: `MODP=0_unadjusted`; corporate-action semantics remain an
  explicit data limitation.

IWM expansion stops at the current lower boundary. An actual KIS page below it
contained one internally inconsistent OHLC row; the strict parser rejected the
page rather than silently admitting its other rows. The 694-session common
panel is clean and usable now. Do not repeatedly query that blocked IWM page
until a different official endpoint or a separately evidence-backed row-quality
contract resolves it.

The worker writes a raw snapshot and manifest before atomically moving a
cursor. Its two-minute shared retry after a token event is observed source
transport pacing, not a permission or model-quality gate. Inspect the live
index before a new run because it is authoritative.

## Lane State

### Data

`data.kis_paper_daily` re-attests index/manifest/raw hashes, cursor seams,
path safety, and conflicting overlap before returning the same-source common
panel. Its partial page is usable only when its first page was fully validated;
the later IWM source-quality failure remains excluded. The former 756-session
target is a validation preference, not a KIS Paper or smoke-execution
authorization.

### Engine Research

The 694-session KIS-native comparative CPU run is under
`D:\thericher-v2\model-artifacts\kis-daily-comparative-validation-v1\kis-daily-comparative-20260722T100000Z`.
Its contract hash is
`sha256:ca11faa8341cdfab97b8f98bb64e33d7a5c779019de324595f58fd619d6c0810`.
It creates independent 414-session development and 138-session validation
slices, separated by two-session purge and embargo ranges, and runs fixed
relative-strength, cash, and fixed-quantity buy-and-hold references through
replayable `local_paper` only. Run manifests record data/event hashes, costs,
and code revision outside Git.

The nominal 138-session historical holdout is marked `burned_precontract`.
The earlier 595-session smoke observed dates overlapping that suffix, so the
new output is honest retrospective execution evidence, not a return,
model-selection, or promotion claim. This is not a blocker for KIS Paper or
new research: prospective paper observations are the next clean out-of-sample
source.

### Execution

Local-paper replay and attribution are available. KIS Paper submission is
authorized but no complete paper order transport exists yet; its next
implementation must be paper-host-only, persist intent, and reconcile broker
outcomes. The credential-free local dashboard may display sanitized state but
cannot transmit orders.

## Legacy Simplification

Terminal historical KIS capability probes were removed from the executable
surface. Their external summaries remain immutable historical evidence only.
There is no reusable one-shot reservation or a fixed raw-retention marker in
the active path: current collectors record whether raw data was actually
written, and cache collection is allowed by default. A historical marker can
never disable a new correctly scoped KIS Paper data, account, order, or
scheduler job.

## Recovery

At task start or after interruption, inspect active jobs and external indexes,
then classify each as `resume`, `restart`, `reconcile`, `complete`,
`unrecoverable`, or `operator`. A missing/corrupt snapshot is a technical
recovery issue, not a reason to recreate approval process. Unknown broker
submission state requires reconciliation before a replacement paper order.

## Next Handoff

Advance the authoritative objective in `NEXT_CODEX_GOAL.md`. At its boundary,
review the data contract, execution route readiness, research queues, GPU
eligibility, disk capacity, and role ownership; make reversible no-cost changes
autonomously and escalate only a real remaining operator boundary.
