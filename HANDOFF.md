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

`agents/orchestration.md` is Codex's cross-lane-only stateboard. It tracks
shared resource conflicts, external waits, the current bottleneck, and one
reversible operating improvement; it never copies lane queues, becomes a
second goal, or creates an approval step. A quota or timer wait belongs to its
owned worker or scheduler, so Codex continues other ready work instead of
remaining in a long foreground sleep.

For a genuinely unknown private non-live provider or throughput capability,
Codex uses a bounded probe before adding a durable throttle or operator hold.
Existing documented or measured controls remain active until source evidence or
the probe gives a recalibration fact. A failed probe affects only its input and
cannot pause an independent ready lane.

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
- The operator explicitly prefers autonomous forward progress over Paper
  process scaffolding. Do not create or revive a permission latch from a
  historical run marker, unavailable input, model result, raw-retention value,
  or schedule outcome. Preserve the fact, scope its recovery/no-intent result,
  and continue every independent correctly scoped action.
- This is standing approval for all non-live private work, including recurring
  KIS Paper data jobs and virtual submit/modify/cancel. Never represent a
  historical `raw_market_data_retained: false`, one-shot completion, blank
  response, or `safe_to_submit` value as a new operator decision or a global
  execution hold.
- The 2026-07-23 operator directive explicitly covers every private non-live
  action, including ordinary Paper trades. A no-bytes retention value is
  metadata for its own historical attempt only, never a fixed permission state
  or a reason to wait for a human before a fresh correctly scoped action.
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

This default-action policy also applies when a prior run has no retained bytes,
an unavailable input, or a failed recovery note. Preserve and scope that fact;
do not translate it into a new human release, global halt, or another lane's
permission condition.

## Current Task Update

The first receipt-linked daily SPY KIS Paper position lifecycle is complete.
Its forward head collector wrote one hash-attested `SPY` / `AMS` snapshot under
`D:\market_data\us_equities\kis_paper_private\daily-head\v1`, with 99
prior completed sessions through 2026-07-21. It excludes the current US
exchange date before persistence. The daily runner attests the first local
availability of one whole source, evaluates a transparent two-close receipt,
replays eligible decisions through `local_paper`, and can bind exactly one
virtual-paper buy or sell identity to a fresh independent `AMS` price proof.
Execution uses a fresh complete KIS Paper snapshot to allow only a flat-to-one
share entry or a one-share-to-flat exit; it does not infer inventory, fills, or
PnL from local intent. One receipt persists one side and first price proof, so
a changed quote or opposite-direction replay cannot produce another order. The
daily Docker service no longer auto-cancels a valid lifecycle limit order; the
standalone canary remains cancellation-oriented. The current Docker exercise
used `.env.example` and truthfully recorded `no_intent` /
`daily_receipt_not_current` with no credential, quote, account, or order call.
Windows tasks `thericher-kis-paper-daily-spy-head` (22:15 KST) and
`thericher-kis-paper-daily-spy-session` (23:50 KST) are installed Tuesday
through Saturday and use the current compose service at their next due run.

Their 2026-07-23 KST due run completed successfully. The head reattested one
prior-complete `SPY/AMS` source through 2026-07-22 without retaining the
current US exchange date. The session recorded the safe Paper-only
`no_intent` / `target_already_satisfied` outcome: it evaluated its receipt but
created no canary run or broker order. This is execution-coverage evidence
only; it does not claim a fill, PnL, or a model result.

The separate data-only `thericher-kis-paper-intraday-head` task has four weekly
KST triggers at 00:35, 02:35, 04:35, and 06:20, while retaining its existing
four-page-per-target cap and one Docker service. Its first expanded-cadence
cycle completed successfully. A metadata-only generation-8 inspection still
found zero complete QQQ sessions out of five: the 2026-07-22, -23, and -24
candidates held 239, 39, and 238 minutes of 390, with missing offsets
`0-5,245-389`, `0-350`, and `0-125,245,365-389`. Continuation is `mixed`, exact
and conflicting retained overlap are `none`, and the scoped last reason is
`minute_duplicate_conflict`; no raw minute file or price was opened. Those
varying gaps do not identify a source-backed page-size, duplicate, timestamp,
or cap recovery, so the cadence and strict selector remain unchanged. Only an
exact 390-minute QQQ union may become a future Research input; any short or
gapped union remains Data evidence only.

A bounded recovery hardening now rejects an entire candidate batch if its own
minute rows conflict, so an earlier page from that batch cannot become a
retained prefix or move a cursor. Explicitly marked legacy candidate-batch
conflict chunks remain audit evidence but are excluded from cache/session
consumption. The outer collector is complete only when it returns both expected
QQQ and SPY outcomes; a QQQ recovery may still run the existing QQQ-only
preparation child while the outer result truthfully remains incomplete. The
future offline observation accepts only canonical planned local-paper event
streams, and missing/mismatched Paper state stays categorical unavailable
evidence rather than a false submission or terminal claim.

The first receipt-linked Paper observer is now invoked automatically by the
scheduled daily SPY session after that same session has produced its exact
receipt-derived run ID; the separate `kis-paper-receipt-observer` Docker
profile remains available for exact manual replay. The session verifies the
receipt/run digest mapping, never scans for a latest run, and records only the
safe categorical observation under
`D:\thericher-v2\model-artifacts\execution\kis-paper-receipt-observation`.
It has no order submit/modify/cancel capability. An exact current open order
can establish `open`; a same-day ID sighting or aggregate position cannot
establish fill, cancellation, receipt attribution, or realized PnL, so the
first schema always retains `pnl_status: not_observed`. Missing, stale,
corrupt, and ambiguous facts are scoped to the receipt and never pause another
authorized Paper action. A read-only observer error becomes only a safe
`observer_unavailable` session fact and cannot change the original order
result.

The read-only `kis-paper-terminal-field-probe` Docker profile reads one
persisted SPY/AMEX Paper intent without creating a lock or mutating state, and
queries only an acknowledged submission's ET order date through fixed
`VTTS3035R`. The daily SPY session now invokes it automatically only after the
canary's exact receipt/run mapping and the ordinary receipt observer. Session
evidence embeds the existing categorical safe payload and a content-hash
artifact reference; a probe error is scoped
`terminal_field_probe_unavailable` and preserves the canary/observer outcomes.
The official sample names order/fill/remaining quantity, fill price/amount,
processing-status, revision/cancel, and order-time fields, but does not
qualify terminal enum, lineage resolution, or net-PnL semantics. The first
legacy cancelled-canary state predates the durable submission timestamp, so its
post-validation probe truthfully records `submission_time_missing` without a
KIS call. New acknowledged canaries retain that timestamp write-once through
later cancellation/reconciliation. The capability remains
`terminal_state_support: unqualified` / `pnl_status: not_observed`; it does not
pause future Paper work.

The 2026-07-25 exact-intent recovery audit confirmed that the existing observer
already handles an acknowledged durable intent absent from both the current
open-order snapshot and same-day ID lookup as `outcome_unknown` /
`reconciliation_status: ambiguous` /
`terminal_state_not_supported`. It neither alters the durable intent nor issues
an order request, and a synthetic replay proves the same result remains scoped.
Do not add a stale-order timer or terminal transition while the KIS source lacks
qualified terminal enum, amendment-ordering, and completion semantics.

The first immutable baseline receipt now has external evidence at
`D:\thericher-v2\model-artifacts\kis-paper-baseline-receipt\qqq-20260623-20260721-receipt-r1\receipt.json`.
It binds the frozen QQQ/NAS KIS-only 20-session input plus the current observed
capability contract and truthfully reports `abstain` / `unqualified` /
`input_unavailable`. Its local-paper preparation is a sanitized no-intent, not
a Paper permission hold. The pure bridge separately proves that an eligible
receipt preserves its exact decision identity through a replayable
`source: local_paper` fill and can prepare an existing KIS Paper canary decision
only when Execution supplies matching venue, sizing, and final-limit proof.
No KIS call, credential read, raw price, or artifact-in-Git behavior occurred.

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
the matching directional pause before configuration/network access; a
`pause_sells` instruction cannot suppress a hard-risk exit. These are local
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
summary described in `AGENTS.md`. The KIS daily-SPY head/session, quote-session,
and intraday-head workers are owned only by their named Windows Scheduled Tasks;
duplicate Codex worker automations were removed so one due time cannot issue
duplicate KIS Paper calls. The daily review does not grant live authority.

## Current Data State

`kis-paper-private-daily-backfill-v1` is the active KIS-native daily cache:

- cache/index: `D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json`
- data-bearing mappings: `QQQ/NAS`, `SPY/AMS`, and `IWM/AMS`
- current logical cursor state: QQQ/NAS is `complete` at `20070820` with 27
  chunks, SPY/AMS is `complete` at `20070821` with 26 chunks, and IWM/AMS is
  `source_limited` at `20231010` with ten chunks
- current three-target common intersection: 694 completed sessions; the
  separately verified QQQ/SPY-only intersection has 4,756 sessions from
  2007-08-21 through 2026-07-17
- stored fields: `MODP=0_unadjusted`; corporate-action semantics remain an
  explicit data limitation.
- `thericher-kis-paper-daily-backfill` is installed for 07:00 KST Tuesday
  through Saturday. It runs a finite data-only catch-up of up to 48 daily
  chunks or six hours after the intraday head and before the local operating
  review; it has no account or order route.
- Every KIS Paper market-data worker shares the external
  `D:\market_data\us_equities\kis_paper_private\collection-control-v1`
  request gate. It starts ordinary requests at least 1.25 seconds apart and
  records only timing facts; a categorical KIS rate limit imposes a shared
  60-second cooldown. A separate atomic token-start gate permits one token POST
  every five minutes across short-lived workers. An unavailable token window
  exits without an HTTP request or worker sleep. Neither state stores
  credentials, response bodies, account facts, or raw rows.
- The Docker profile completed an actual 199-row `SPY/AMS` chunk on 2026-07-23
  using only its injected Paper app-key/app-secret pair. Its image does not
  mount `.env`; the shared market-data loader accepts only a complete named
  Paper pair, rejects a partial pair or live mode, and leaves host `.env`
  parsing as its strict fallback.
- The 2026-07-25 shared-token measurement completed a single-client Docker
  QQQ/NAS chunk with one token attempt, two daily pages, and 199 retained rows
  from `20210107` through `20200326`; a preceding bounded run committed the
  matching SPY/AMS chunk. A catch-up attempted before its five-minute token
  window returned `token_spacing_pending` without an HTTP request or sleep.
  After per-chunk request accounting was corrected, the next reused-client run
  drained 33 chunks, completed QQQ and SPY, and recorded no rate-limit cooldown.
  This confirms token coordination and throughput rather than a credential
  fault, and remains an exact Data recovery fact, not a global collection,
  Paper, or scheduler hold.

IWM expansion stops at the current lower boundary. An actual KIS page below it
contained one internally inconsistent OHLC row; the strict parser rejected the
page rather than silently admitting its other rows. The 694-session common
panel is clean and usable now. After two consecutive zero-row
`daily_response_invalid` results at the same cursor, the active daily cache
marks only that IWM source cursor `source_limited` and continues selecting
ready QQQ/SPY work. Do not repeatedly query the source-limited IWM page until
a different official endpoint or a separately evidence-backed row-quality
contract resolves it.

The newly complete QQQ/SPY-only D1 intersection was re-attested offline at
4,756 common sessions from 2007-08-21 through 2026-07-17. Its index hash is
`sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660`
and its dataset hash is
`sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718`.

The price-free Tiingo Standard EOD sidecar is now immutable at
`D:\market_data\us_equities\kis_paper_private\daily-corporate-actions\snapshot=2026-07-24-qqq-spy-tiingo-events-v1`.
It exact-matches those KIS sessions, carries 78 QQQ and 76 SPY normalized
dividend/split event facts, and has dataset hash
`sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3`
and manifest hash
`sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d`.
Neither the sidecar nor its paired
`D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-mask.json`
receipt retains raw Tiingo responses or prices. This is only retrospective
price-return plumbing: it is not total return, point-in-time evidence, a model,
GPU input, strategy result, or Paper decision.

Claude's first 2026-07-25 verdict was `unsupported` before source-attested
event dates. Its follow-up was `supported-with-limits`: before any daily naive
baseline, re-attest both hashes, audit every event boundary against the KIS
series, and freeze or reject a conservative `+-1`-session buffered mask. That
source-contract work does not halt collection, prospective minute work, local
paper replay, or KIS Paper operation.

The 2026-07-23 bounded IWM retry confirmed a fourth exact zero-row
`daily_response_invalid` result at the unchanged cursor, so the index now
marks only that source cursor `source_limited`. The same worker immediately
continued QQQ and committed 199 rows. This is a source-quality fact for IWM,
never a KIS Paper permission, scheduler, or retention latch for QQQ, SPY, new
intraday work, account calls, or Paper orders.

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

`data.norgate_development_qualification` now re-attests that exact frozen
snapshot and writes only the single sanitized receipt
`D:\thericher-v2\model-artifacts\norgate-development-qualification\r1-3d0841b90ddfd8d8\qualification.json`
(`sha256:1f5ddec5cd1bc94fddbfde9de22e6480480f3daa28e0a03913a0d8d5d299a9d4`).
It records source hashes, aggregate counts, scope, limitations, reversal facts,
and one declarative `20`-return D1 interface (`t-20..t`, decision at `t`,
next-open to following-open outcome timing). It persists no source rows,
symbols, dates, OHLCV values, feature vectors, labels, prices, PnL, or broker
data. The qualified result is development-only; model, GPU, campaign, ranking,
PIT, Paper, PnL, and live flags remain false. A source hash/scope/receipt
schema change rejects reuse, and an unqualified source receives no usable
interface. Claude's `supported-with-limits` review confirms containment only:
static-survivorship selection, unverified adjustments, trial retention, and the
absence of a sanctioned promotion route remain material limits.

The worker writes a raw snapshot and manifest before atomically moving a
cursor. The scheduled catch-up reuses one Paper client for its finite run and
relies on the shared request gate rather than a daily quota assumption. A
terminal historical minute cursor is recorded as `source_exhausted` without a
new request; the separate head cache remains the normal path for fresh minutes.
Inspect the live index before a new run because it is authoritative.

On 2026-07-25, the separately rooted
`intraday-historical-probe\v1` performed the documented blank-`KEYB` first
request for QQQ/NAS and SPY/AMS. Each retained one 120-row 1m page whose
observed KIS timestamp range was `20260724T100800` through `20260724T120700`,
with terminal continuation and no next cursor. It demonstrates only the current
normal-start endpoint capability. Do not invent an arbitrary historical `KEYB`
seed, mutate the ordinary historical cursor cache, or generalize this result to
another endpoint. The raw snapshots remain local beneath the probe root.

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
file mount. That offline reattestation found 718 unique 1m bars for each
stream: QQQ spans 12:02 through 23:59 UTC and SPY 11:59 through 23:59 UTC on
2026-07-21. Inspect the external index before another run; it is authoritative.
The first retained v1
manifests use the earlier, equivalent completed-bar-rule spelling. The loader supports
only that exact legacy form plus the explicit current form; do not rewrite the
immutable snapshots merely to normalize metadata.

On 2026-07-23, the current official KIS sample's response-header continuation
contract corrected the historical minute cursor parser: `tr_cont` `M`/`F`
means continue with `NEXT=1`, while `output1.next` remains metadata. A bounded
Paper data-only Docker cycle then committed 100 `QQQ/NAS` and 69 `SPY/AMS` rows
and cleared both historical cursors. This is a source-contract recovery, not a
Paper authority condition; the separate prospective head cache remains the
normal source for new sessions.

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
current source scope. Its reusable read-only `Bar`-series loader is complete
and preserves those negative scope flags; it adds no selector, model, PnL,
KIS, or Paper behavior.

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

The first fixed QQQ/SPY D1 control run is complete at
`D:\thericher-v2\model-artifacts\kis-daily-masked-naive-validation\kis-daily-masked-naive-validation-v1.json`,
with content hash
`sha256:e2ad842d852fe647f7de6367955f7a48f27f08508e32816f98f3c473ffcffbf6`.
It re-attested the qualified audit before materializing the 3,806-session
development/purge/validation/embargo prefix, ran exactly 12 fixed control cells,
and replay-checked 21,294 `source: local_paper` fills. The artifact has no raw
market fields or retained event log, and the untouched 950-session tail was not
materialized.

Claude's independent verdict is `supported-with-limits` for plumbing only. The
single favorable SPY validation cell is inconsistent with its SPY development
cell and the other three cells, so it is not a signal, model seed, promotion,
or Paper-input fact. The next authoritative objective must preserve that
boundary while advancing a separate ready engine loop. At each boundary, review
data contract, execution route readiness, research queues, GPU eligibility,
disk capacity, role ownership, and the latest reversible throughput improvement;
escalate only a real operator boundary.

The static Norgate receipt is also closed as development-only evidence. It can
provide no candidate rows, model/GPU queue item, Paper intent, or historical
universe assertion. Do not reopen its legacy raw-derived feature artifact; a
future model-ready lane needs a separately eligible prospective KIS contract.
The exact-intent Paper recovery audit is likewise closed: retain the existing
read-only observer's bounded ambiguity rather than adding stale-order automation
until qualified terminal source semantics exist.

The existing scheduled `thericher-kis-paper-intraday-head` task now has one
post-durable, sequential metadata-only handoff. When its exact QQQ target result
is `collected` or `recovered`, it starts the prospective QQQ preparer with a
fixed `scheduled-head-v1` identity even when the independent SPY target has a
scoped collection failure. That SPY failure keeps the overall collection result
`incomplete`, so collection health and the QQQ preparation input remain
separate. The child receives no KIS, account, order, dashboard, or live
environment values and has a ten-second containment timeout. `pending` or
`preparation_unavailable` is an observation about that preparation attempt only;
it cannot alter the already completed collection, cache cursor, or freshness
projection. At five complete QQQ sessions, the preparer writes and later
validates/reuses exactly one external precommit and planning-receipt pair bound
to the first five selected session dates and their row-fingerprint digest. It
has not created a model, GPU job, Paper order, or profitability conclusion.

The pair-bound offline consumer is now implemented and synthetically verified.
It accepts only a Data-loader-sealed first-five pair whose selected QQQ dates
and row-fingerprint digest match both before and after local cache reads. The
pair's full head-index hash remains preparation-time provenance, so a later
append or independent SPY metadata update does not invalidate the frozen
selection; a selected-row change fails closed. It fits the fixed regularized
linear control only on the ten historical sessions, and evaluates the four
fixed local-paper candidates in memory. External evidence contains only
identity-bound, sanitized decisions/fills and hashes: no raw bars, prices,
order identifiers, source paths, PnL, credentials, network call, KIS call, GPU
work, selection, promotion, or broker action. A safe partial replay may restart;
a tampered complete receipt fails without overwrite. The real pair is still
absent, so the host and network-disabled research-container commands both
truthfully return `preparation_pair_missing`. A Claude drift-check retry is due
at the next material decision boundary because the local Claude OAuth session
expired; that external tooling fact does not block this bounded implementation.
