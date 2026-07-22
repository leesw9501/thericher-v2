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

## Current Task Update

The first KIS-native intraday feature breadth loop is complete on the frozen
QQQ 20-session source. Its external CPU artifact is
`D:\thericher-v2\model-artifacts\kis-intraday-feature-breadth\qqq-20260623-20260721-feature-breadth-r1\summary.json`;
all three fixed candidates stayed non-positive after costs on the 5-session
comparison slice, so none was selected or promoted. Four later source sessions
remain unused for later research interpretation, not as a Paper or operator
approval barrier.

The fixed PyTorch CUDA GRU smoke completed on the RTX 4090 with 2,990
development-only sequences and a sanitized external summary at
`D:\thericher-v2\model-artifacts\kis-intraday-cuda-sequence-smoke\qqq-20260623-20260721-gru-smoke-r1\summary.json`.
It verified the mounted D: cache/artifact path and wrote no checkpoint or model
promotion result. The two local Docker schedules are installed and ready for
their next due sessions; all KIS Paper work remains standing-authorized.

The fixed LSTM, causal-TCN, and compact-attention CUDA screen completed under
the network-disabled `research` Docker profile on the same frozen 20-session
QQQ source. The immutable external precommit was written before comparison data
materialized; all three replays produced only `source: local_paper` fills.
After-cost PnL on the five descriptive comparison sessions was LSTM
`-639.3858`, causal TCN `-5.9777`, and compact attention `0.0000`. The summary
is at
`D:\thericher-v2\model-artifacts\kis-intraday-sequence-architecture-screen\qqq-20260623-20260721-sequence-architecture-r1\summary.json`.
There is no winner, model promotion, ensemble, or Paper-work implication.

The first local KIS Paper operations console is now implemented. It is bound to
`127.0.0.1:8787`, reads only sanitized account/canary/freshness projections, and
persists reversible `pause_buys`/`pause_sells` instructions in a separate local
control file. The web process has no KIS credentials, broker client, private
intent state, or market-data mount. The active canary/session consumes
`pause_buys` before configuration/network access; `pause_sells` is retained for
the later sell executor and cannot suppress a hard-risk exit. These are local
operations controls, not Paper authority or research-promotion gates.
When a due session ends before it creates an intent (for example a buy pause or
quote failure), it also refreshes the sanitized canary runtime as `unavailable`.
The console therefore reports a current no-intent state rather than preserving a
stale prior canary result; the exact safe reason remains only in external
session evidence.

The first autonomous Windows-scheduled cycle is now evidenced. The due
quote-session completed with a KIS-success-shaped response whose `last` and
`zdiv` fields were blank, so it recorded the safe no-intent
`quote_unavailable` / `quote_response_incomplete` outcome and submitted no
order. The current image will classify the same shape as
`quote_response_blank` without storing values or a response body. The due
intraday-head task then completed with one committed retained chunk each for
QQQ/NAS and SPY/AMS under its independent cache root; prospective preparation
correctly remains `pending` because zero complete QQQ sessions exist so far.
The console freshness projection is current and metadata-only. Existing
backfill evidence remains 14 retained chunks per stream (QQQ: 3 partial; SPY:
2 partial). `raw_market_data_retained: false` remains an historical fact only
and never blocks fresh collection, KIS Paper work, or a schedule. Both Windows
tasks remain `Ready` and invoke their named Docker profiles with `--build`.

An exact, Paper-host-pinned SPY `price-detail` structural diagnostic
(`HHDFS76200200`) then received another success-shaped mapping, but the required
last-price, decimal-scale, and tick fields were blank. The temporary diagnostic
emits only field-state categories and cannot create an intent or order. This
rejects that candidate as an execution price conversion; it does not pause
Paper orders, collection, schedules, or a later independently evidenced price
candidate.

The later official KIS sample cross-check established that SPY's AMEX contract
uses `AMS` for the price endpoints and `AMEX` for the order venue. The exact
`AMS/SPY` asking-price and price-detail calls then satisfied the in-memory
price-input contract: a fresh Korea-timestamped last price, matching decimal
scales, and a positive tick that aligned with the price. No quote value or raw
response was written. The resulting independent virtual canary reached its
persisted outcome path but remains `outcome_unknown` /
`reconciliation_unresolved`. Its same-run read-only reconciliation reported an
available account with zero open orders in the sanitized aggregate; it created
no buy or cancel order. This affects only that intent. The new recovery helper
will refuse a terminal or acknowledged-submitted state rather than widening a
read-only recovery into a cancellation or new submission.

The Codex app automation `thericher-daily-operating-review` is active at 08:10
KST. It inspects the previous scheduled outcomes through sanitized evidence,
continues ready no-cost lane work, and publishes only the concise operator
summary described in `AGENTS.md`. The KIS quote-session and intraday-head
workers are owned only by their named Windows Scheduled Tasks; duplicate Codex
worker automations were removed so one due time cannot issue duplicate KIS
Paper calls. The daily review does not grant live authority.

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

The latest authorized bounded IWM retry on 2026-07-22 again returned the safe
`daily_response_invalid` result with no retained rows. This is a source-quality
fact for that IWM page, never a KIS Paper permission, scheduler, or retention
latch for QQQ, SPY, new intraday work, account calls, or Paper orders.

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

The first reusable KIS-native intraday cache is now at
`D:\market_data\us_equities\kis_paper_private\intraday\v1\index.json`.
It uses the Paper-only 1m endpoint and persists immutable provider-field
snapshots, manifest/raw hashes, exact overlap fingerprints, and a resumable
`NEXT`/`KEYB` cursor. Its first bounded run retained two pages each for
`QQQ/NAS` and `SPY/AMS`: 239 exact-deduplicated 1m rows per stream with one
boundary overlap per symbol. The offline loader creates canonical `Bar` values
from KIS's explicit Korea date/time fields and reuses explicit-session 5m, 10m,
1h, and 3h resampling. It performs no network or credential access.

The first observed range is extended-session evidence only: QQQ covers 20:01
through 23:59 UTC and SPY covers 19:58 through 23:59 UTC on 2026-07-21. The
loader's 239 bars per stream were complete under the collection-time rule, but
regular-session, holiday/early-close, exchange timestamp, and source
open-versus-close semantics are still unqualified. This blocks only a claim of
a regular-session research campaign, not continued cache collection, local
paper smoke work, or another Paper action.

A Docker-profiled follow-up cycle advanced the same cursors without a secret
file mount. One further bounded continuation chunk now brings the current
offline reattestation to 718 unique 1m bars for each stream: QQQ spans 12:02
through 23:59 UTC and SPY 11:59 through 23:59 UTC on 2026-07-21. Inspect the
external index before another run; it is authoritative. The first retained v1
manifests use the earlier, equivalent completed-bar-rule spelling. The loader supports
only that exact legacy form plus the explicit current form; do not rewrite the
immutable snapshots merely to normalize metadata.

The separate prospective head path now writes under the sibling
`D:\\market_data\\us_equities\\kis_paper_private\\intraday-head` root and does
not mutate the historical cursor. `us_equity_2026_session` provides explicit
2026 regular and early-close windows from the published Nasdaq/NYSE calendars;
it does not infer a session from a schedule or KIS field semantics. The first
complete QQQ regular-session replay used 390 retained 1m bars on 2026-07-21.
Its CPU local-paper baseline completed all 1m/5m/10m/1h/3h cells with replayable
`source: local_paper` fills only. The sanitized summary is external at
`D:\\thericher-v2\\model-artifacts\\intraday-multitimeframe-baseline\\kis-private-intraday-2026-07-21-qqq-r1\\summary.json`.
It proves cache-to-replay plumbing, not profit, source open/close semantics, or
an eligible chronological model campaign.

The reattested historical cursor cache now has 21 complete regular 2026 sessions
for each `QQQ/NAS` and `SPY/AMS`, spanning 2026-06-22 through 2026-07-21.
The first frozen QQQ chronological CPU campaign selected the latest 20 sessions
(2026-06-23 through 2026-07-21), with 10 development sessions, the unused
2026-07-08 purge session, and 9 validation sessions. Its external sanitized
manifest is
`D:\\thericher-v2\\model-artifacts\\kis-intraday-cpu-campaign\\qqq-20260623-20260721-r1\\summary.json`.
All six naive replay cells were `local_paper` and reconstruct from matching JSONL
and SQLite evidence. The costed `always_long` and `previous_bar_direction`
references were negative in both phases; this is an underpowered descriptive
baseline, not a model result, promotion, or profitability conclusion.

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

`data.kis_paper_intraday` now provides a network-free verified 1m loader for
the first QQQ/NAS and SPY/AMS cache snapshots. A local-paper multitimeframe
smoke consumed the QQQ loader with 1m, 5m, 10m, and 1h cells; all emitted only
replayable `local_paper` fills, while the short cache correctly skipped the 3h
execution cell. This is a consumption smoke, not an after-hours strategy or
profit claim.

A source-windowed follow-up baseline has now consumed a complete 390-minute QQQ
regular session through all five configured timeframes. The active Windows task
`thericher-kis-paper-intraday-head` remains a separate data-only path, so it
does not compete with the existing quote-derived Paper session.

`select_complete_kis_paper_private_intraday_sessions` is the Data-owned offline
selection boundary for an ordered tuple of full regular sessions. It rejects
closed/early-close sessions, duplicates, unordered dates, missing intraday
minutes, and non-KIS catalogs before deriving a new hash-bound `CatalogedBars`
identity. It does not read credentials or make a network call.

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

The first intraday chronological CPU campaign is complete. Its contract fixes
90 completed in-session 1m context slots, signals only at offsets 89-387,
next-bar-open entry/following-bar-open exit, 1 bp per-side fee, 2 bps per-side
slippage, and `flat`/`always_long`/`previous_bar_direction` local-paper
references. Overnight gaps are allowed only at exact consecutive declared
`SessionWindow` boundaries; a missing in-session minute or a target crossing a
session boundary fails. Attempt labels separate immutable external evidence if
a run needs restarting. The 9-session validation region is too small for model
ranking, ensemble selection, or a profitability claim, but is sufficient to
begin the next bounded feature/candidate preparation work.

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
and console output. The Windows Scheduled Task
`thericher-kis-paper-quote-session` runs it on weekday KST 23:35, which falls
inside that time window in both DST states. Its first Docker exercise was safely
off-session (`not_due`); the first due-session result will be recorded by the
schedule. Its eligibility now delegates to the explicit 2026 Nasdaq/NYSE session
adapter: holidays and out-of-scope dates return `session_unavailable` before
credential access, and early closes stop at their declared close. This is a
technical route guard, not a Paper authority gate.
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

On 2026-07-22 at 15:27 ET, a new independent virtual canary reached a safe
`acknowledged_order_reference` submit category, completed its requested
cancellation, and reconciled cleanly. The category-only lifecycle projection
now exposes that result as a replayable `kis_paper` / `paper_only` fact with a
`cancelled` lifecycle state and `not_eligible` attribution status. It contains
no broker body, order identifier, account value, quote, or credential, and the
host-only projector does not call KIS. This proves one virtual execution
lifecycle, not a model result, realized PnL, or a new gate. The source `last`
may be sub-tick; only the final rounded-down submit limit must satisfy the KIS
tick. This keeps transient provider precision from becoming an artificial
execution pause.

## Legacy Simplification

Terminal historical KIS capability probes were removed from the executable
surface. Their external summaries remain immutable historical evidence only.
There is no reusable one-shot reservation or a fixed raw-retention marker in
the active path: current collectors record whether raw data was actually
written, and cache collection is allowed by default. A historical marker can
never disable a new correctly scoped KIS Paper data, account, order, or
scheduler job. In particular, `raw_market_data_retained: false` means only
that the old snapshot has no raw bytes; it is not a consent hold and a later
due collection proceeds normally. The active intraday collector and offline
reader ignore such a legacy marker without a cache snapshot before attestation,
deduplication, cursor handling, or bar consumption. This remains the default
under standing Paper authority, rather than an exception requiring a new
operator confirmation.

## Recovery

At task start or after interruption, inspect active jobs and external indexes,
then classify each as `resume`, `restart`, `reconcile`, `complete`,
`unrecoverable`, or `operator`. A missing/corrupt snapshot is a technical
recovery issue, not a reason to recreate approval process. Unknown broker
submission state requires reconciliation before a replacement paper order.

## Next Handoff

Advance the authoritative objective in `NEXT_CODEX_GOAL.md`. The older canary
intents remain immutable recovery evidence, but do not create a global one-shot
quota or stop new distinct Paper work. At each boundary, review the data
contract, execution route readiness, research queues, GPU eligibility, disk
capacity, and role ownership; make reversible no-cost changes autonomously and
escalate only a real remaining operator boundary.
