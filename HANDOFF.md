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
- Paper cadence, the number of distinct virtual intents, and recurring
  goal-owned schedules are routine engineering choices, not approval gates or
  one-shot quotas. An unresolved intent blocks only a replacement of that exact
  intent until reconciliation; it does not stop new distinct Paper work.
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

The local Norgate trial also contains a hash-attested static development panel
at
`D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`:
523 symbols, 483 common daily sessions, 252,609 OHLCV rows from `2024-07-18`
through `2026-06-22`. It is survivorship/availability selected with unverified
adjustment semantics. Its manifest permits development-training preparation
only; it is not model, GPU, ranking, paper-trading, PIT, or promotion evidence,
and it makes no PnL claim. Reuse its verified snapshot rather than parsing the
Norgate database or downloading another copy.

`data.norgate_trial_development_panel` now exposes that snapshot through
`load_verified_norgate_trial_development_panel_catalog`. It reuses the same
hash-attested panel bytes to construct immutable per-symbol D1 `CatalogedBars`,
preserves the original non-sequential candidate ranks, and returns the exact
source scope and limitations. Its local smoke verified 523 symbols, 483
sessions, 252,609 bars, and the original rank range 1 through 541 without any
Norgate SDK, credential, network, GPU, or artifact-root access.

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

An optional session ceiling re-attests the complete retained raw evidence but
only materializes `Bar` objects through that ceiling. This keeps frozen
development/validation consumers from carrying later historical bars in memory
while preserving raw-cache integrity checks.

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

The fixed L2 logistic trade-quality gate ran after commit `8a4c4a8` at
`D:\thericher-v2\model-artifacts\daily-three-etf-l2-trade-quality-gate-v1\kis-daily-trade-quality-20260722T170000Z`.
It fits 155 development selector entries (85 positive, 70 negative) and only
permits `enter` or `abstain` for the unchanged selector. The candidate improved
the observed validation mean return (`0.0001684` versus `-0.0004646`) and
drawdown (`0.06447` versus `0.07098`), but both its primary and 2 bp/side stress
bootstrap lower bounds were `0.0`. It is therefore `retired` without tuning,
promotion, or ensemble reuse. Every replay fill is `source: local_paper`.

The gate's core accepts only the 556-session prefix through its post-validation
embargo. The loader still re-attests every source raw file, fingerprint, and
committed row count, but does not construct later `Bar` objects for this
campaign.

The Norgate static panel is not a follow-on breadth or GPU candidate under its
current source scope. The next Data-owned task is only a reusable read-only
`Bar`-series loader that preserves those negative scope flags; it must not add
selector, model, PnL, KIS, or paper behavior.

### Execution

Local-paper replay and attribution are available. The first narrow KIS Paper
canary now has a virtual-host-only US whole-share buy-limit adapter, durable
intent state, no-retry reconciliation, and an accepted-order cancellation path.
Its goal-owned `kis-paper-canary` Docker profile writes private recovery state
to a dedicated volume and only sanitized account/canary state to the local web
runtime. The dashboard cannot transmit orders or receive KIS credentials.

The new `kis-paper-session` profile first fetches an allowlisted transient SPY
quote from the virtual host, derives a one-share nonmarket limit 25 bps below
that quote at KIS's reported decimal precision, and passes only the private
intent to the existing canary. It accepts only a successful KIS result and
rechecks limit expiry plus the weekday ET time window immediately before submit.
Quote values and derived prices stay out of runtime projections, evidence, Git,
and console output. The scoped external automation
`thericher-kis-paper-quote-session` runs it on weekday KST 23:35, which falls
inside that time window in both DST states. Its first Docker exercise was safely
off-session (`not_due`); the first due-session result will be recorded by the
schedule. The helper is not yet a full holiday/early-close calendar claim; the
next KIS-native intraday task must establish that semantics from source evidence.
This is a recurring execution path, not a general scheduler or a fresh approval
boundary.

The first virtual-token attempt on 2026-07-21 returned `auth_rejected` from
the KIS token boundary. The read-only console bridge later reached the account
route and returned `balance_rejected`; it sent no order. A rebuilt current
image wrote `20260721T222233665808Z-unavailable.json` with the expected
`read_only` output shape and the safe diagnostic `balance`, `VTTS3012R`, HTTP
`500`, and `EGW00201`. KIS's official sample repository identifies `EGW00201`
as exceeding the per-second request limit, which fits the bridge's rapid token,
open-order, three-venue balance, and orderable-funds sequence.

The virtual read-only transport now applies an injected monotonic `1.0`-second
minimum gap only to valid external requests. Its first request is immediate;
rejected requests do not consume a slot, while a failed external attempt does.
The next rebuilt bridge completed at
`20260721T223701135634Z-complete.json` after about six seconds, with sanitized
facts `position_count: 1`, `open_order_count: 0`, and USD currency labels. It
sent no order. The canary's separate direct transport now uses the same
injectable source pacing. Its first current-image virtual run,
`canary-20260721T225034Z`, completed its initial reconciliation and then ended
as `outcome_unknown` with `submit_transport_unknown`. The safe evidence has no
broker order reference; that is not proof that the submit side effect did not
reach KIS. The one allowed exact-run recovery has now completed without an
order-route request. Its sanitized evidence has an available account, zero open
orders, zero completion rows, no matching open/completion entry, and still
`outcome_unknown` / `reconciliation_unresolved`: the missing order reference
prevents a clean absence claim. Do not retry or replace this run. A later fresh
canary may be a separate run after safe submit-failure diagnostics are added;
it is not a retry of this intent. This is execution recovery, not a capital,
research, or one-shot policy gate. Continue to exclude `msg1`, broker bodies,
account identifiers, and secrets. Safe evidence is under
`D:\thericher-v2\model-artifacts\execution`; never inspect or copy private
recovery state into Git.

The first independent paced canary, `canary-20260721T232137Z`, now reached an
available, clean reconciliation with zero open orders and completion rows, then
received a KIS submit rejection. Its closed result is `submit_kis_rejected` and
it has no order reference. The program preserves the run as `outcome_unknown`
instead of guessing a broker state; it is not retried in this objective. The
next bounded improvement is to project only a strictly allowlisted KIS-style
submit code when one exists, so the rejection can guide the next independent
canary without retaining response text or opening a raw-broker artifact path.

The next independent run, `canary-20260721T233837Z`, exercised the strict
upstream-code projection. KIS again returned `submit_kis_rejected` after clean
initial reconciliation, but supplied no valid short `msg_cd`, so
`submit_upstream_code` is `null`. The official KIS sample confirms the current
US-paper buy route, `VTTT1002U`, and submitted field set; do not guess a mapping
change. Its price sample exposes `last` and `zdiv`, so the next canary should
derive a valid private limit from a current virtual quote and execute during a
known US regular-session window. That is a runtime condition, not an approval
gate; preserved runs remain untouched.

The canary now persists its cancellation choice with the private intent,
serializes sibling run IDs through one state-root lock, resumes cancellation of
an acknowledged matching open order after a restart, and treats any non-success
submit response as `outcome_unknown` rather than a clean rejection. A matching
completion record after cancellation also remains unresolved until a later
attribution contract exists. These are execution correctness properties, not
new paper approvals or reporting gates.

## Legacy Simplification

Terminal historical KIS capability probes were removed from the executable
surface. Their external summaries remain immutable historical evidence only.
There is no reusable one-shot reservation or a fixed raw-retention marker in
the active path: current collectors record whether raw data was actually
written, and cache collection is allowed by default. A historical marker can
never disable a new correctly scoped KIS Paper data, account, order, or
scheduler job. In particular, `raw_market_data_retained: false` means only
that the old snapshot has no raw bytes; it is not a consent hold and a later
due collection proceeds normally.

## Recovery

At task start or after interruption, inspect active jobs and external indexes,
then classify each as `resume`, `restart`, `reconcile`, `complete`,
`unrecoverable`, or `operator`. A missing/corrupt snapshot is a technical
recovery issue, not a reason to recreate approval process. Unknown broker
submission state requires reconciliation before a replacement paper order.

## Next Handoff

Advance the authoritative objective in `NEXT_CODEX_GOAL.md`: build the first
KIS-native intraday cache and consume its first honest bars in the Paper-input
contract while the scoped session schedule records its first due outcome. The
three older canary intents remain immutable recovery evidence, but do not create
a global one-shot quota or stop new distinct Paper work. At each boundary,
review the data contract, execution route readiness, research queues, GPU
eligibility, disk capacity, and role ownership; make reversible no-cost changes
autonomously and escalate only a real remaining operator boundary.
