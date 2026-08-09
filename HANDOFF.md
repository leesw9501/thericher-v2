# TheRicher v2 Handoff

## Product Direction

TheRicher v2 is a private, reproducible US-equity research and KIS Paper
trading engine. The product loop is: causal market data -> frozen research
contract -> backtest/walk-forward evidence -> local-paper replay -> KIS Paper
execution evidence -> PnL attribution. KIS Paper is early execution evidence,
not a reward for a profitable model. `KIS_LIVE_*` is unavailable.

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the one current bounded
company objective. The role stateboards are current projections only; Git and
external artifacts retain history.

## Current Objective

`task-owned-kis-intraday-causal-observation-qualification-v1` is complete.
The caller-selected 2026-08-08 06:20 KST terminal
`intraday-head-20260807T2120007624227Z` reattached through the offline
source-safe reader as `complete` with a verified exact capture binding, but
that binding's cumulative coverage category is `incomplete`. The exact
QQQ/NAS and SPY/AMS M1 input is therefore `input_unavailable`: it does not
establish a completed session, decision-time availability, or provider
finality. The terminal's source-safe downstream statuses create no broker,
fill, PnL, alpha, or model conclusion. The required falsification-first Claude
request exhausted the local CLI's weekly quota, so its review is
`review_unavailable`, not agreement. No new reader was needed because the
existing hash-bound projection reproduces this narrow no-promotion decision.

The next objective is `task-owned-kis-intraday-causal-evidence-refresh-v1`.
Only the existing task may produce the next candidate; its next owned
invocation is 2026-08-11 00:29 KST. Reattach a caller-selected later terminal
and its exact bound evidence offline, then qualify only if every causal,
completed-bar, chronological-split, decision-time availability, and finality
condition is separately evidenced. Otherwise preserve a scoped
`input_unavailable` fact and let that task retain the next attempt. Before the
next invocation, the task-owned local path now writes one current-cache
availability receipt, binds its contract/receipt/precommit/summary hashes into
the terminal, and accepts a prospective pair attempt only when its immutable
contract matches the same four hashes. The offline reader recomputes the named
summary-file hash and rejects any mismatch;
even a matching pair remains `input_unavailable` until decision-time
availability and provider finality are separately observed. This adds no KIS
request, scheduler, broker route, model, GPU appointment, or Paper intent.
The Claude drift-check timed out, so this package is `review_unavailable`, not
Claude agreement.

`kis-paper-m1-historical-reach-probe-v1` is complete. Its one shared in-memory
KIS Paper client made one current-day M1 GET for each fixed QQQ/NAS and SPY/AMS
target, with the first target issuing one token and the second reusing it. Both
pages were accepted, terminal, and had no recognized continuation; no raw rows
were retained, no categorical error occurred, and no existing QQQ/SPY cache,
cursor, task, Docker service, account route, order route, or live route changed.
The final source-safe elapsed bucket was `under_5_seconds` for each target.
This establishes only that the exact blank-cursor, current-day starting
requests ended after one page. It does not establish provider-wide retention,
prior-day behavior, data qualification, decision-time availability, model
readiness, or Paper eligibility. The first actual run exposed an accounting-only
request-start classification defect; a Validation review also caught unsafe
artifact-root ordering, Windows reparse-point coverage, invalid-continuation
success classification, and empty-page recovery. All were corrected before the
final source-safe receipts. Claude did not return before the bounded review
window, so that check is `review_unavailable`, not agreement.

`kis-paper-m1-previous-day-scope-probe-v1` is also complete. The same bounded
two-target, one-client route made one explicit-previous-day M1 GET for each
target; both accepted pages were terminal, had no recognized continuation, and
contained only one exchange-date category. QQQ issued one token, SPY reused it,
both elapsed buckets were `under_5_seconds`, no categorical error occurred, and
the scope-isolated receipts retained no raw rows. Therefore neither exact
initial request scope currently opens a paginated historical M1 route. This is
not a provider-wide retention limit or a data/model/Paper qualification claim;
the remaining historical scope remains `unknown`. Claude again did not return
before the bounded review window, so that check is `review_unavailable`.

`kis-paper-m1-current-head-duplicate-recovery-v1` is complete. The existing
QQQ/SPY `session-capture` route now quarantines only an immutable, committed,
cursor-free head when a collected candidate conflicts with it. The original
snapshot remains immutable; the conflicting invocation stays rejected and does
not reach downstream consumers. A later task-owned compatible capture can then
append the fresh head exactly once. Partial heads, cursor-backed history,
malformed markers, and candidate-batch conflicts still fail closed. The exact
2026-08-07 06:20 KST terminal is legacy evidence and remains
`not_recorded_legacy`; it was neither rewritten nor reclassified. No KIS call,
task invocation, credential read, account route, or order route occurred.

`source-local-qqq-donchian-local-paper-pnl-attribution-v1` is complete. Its
immutable `20260807-donchian-pnl-r1` artifact reattests the exact fixed 20/10
Donchian mechanics parent, reproduces only the same completed QQQ/NAS M1
sessions in memory, and applies the existing FIFO local-paper accounting per
terminal-flat session. It records 115 closed segments, 230 `local_paper` fills,
gross delta `-41.984600`, fees `16.5045`, net delta `-58.489100`, zero open
quantity, and exact parent replay parity. The CPU smoke used no KIS,
credential, network, or external broker path. This negative fixed baseline is
not a profitability conclusion, candidate selection, predictive campaign, GPU
appointment, Paper input, or live/paper broker outcome. Evidence:
`D:\thericher-v2\model-artifacts\research\source-local-qqq-donchian-local-paper-pnl-attribution-v1\20260807-donchian-pnl-r1\summary.json`.
The bounded Claude drift-check timed out, so this record is
`review_unavailable`, not Claude agreement.

The next bounded objective is Execution
`private-kis-paper-operator-dashboard-v1`: build a loopback-only private
operator surface over the existing KIS Paper read-only account contract and
local emergency controls. It must never read `KIS_LIVE_*`, expose a public
service, or turn dashboard interaction into a broker order.

`intraday-qqq-offline-validation-reliability-v1` is complete. The exact
2026-08-07 04:24 KST QQQ session was a valid Paper-only `no_intent`, and its
offline validation artifact existed, but the immutable v3 payload omitted the
top-level `status: validated` required by the scheduler's exact-session
consumer. The v4 validator now binds that source-safe status into its identity
and writes a new contract namespace, preserving every v3 artifact unchanged.
It remains offline, network-disabled, credential-free, and unable to create a
broker, order, fill, PnL, alpha, model, or coverage claim. Focused tests,
parallel authority tests, Ruff, and both Compose configurations passed; the
validator service bind-mounts `src`, so no image rebuild was required.

The historical 04:24 terminal remains
`recovery/prospective_validation_payload_unavailable` and `legacy_unbound`; it
is not rewritten. `intraday-qqq-v4-scheduled-validation-observation-v1` is
now complete: the existing 2026-08-07 06:20 KST task ended with Scheduler
result `1`, and its exact task-owned pointer/immutable terminal agree on
`recovery/collection_exit_nonzero`. Its required same-run capture binding is
verified with `incomplete` cumulative coverage. The bound source-safe capture
receipt classifies both QQQ/NAS and SPY/AMS targets as
`rejected/minute_duplicate_conflict`; this is a collector recovery fact, not a
raw-data, quality, model, Paper, fill, PnL, or alpha result. Collection failed
before the guarded QQQ route, so the prospective session and v4 validator are
both `not_applicable`: v4 was not evaluated or failed on this run. No manual
KIS call, task invocation, credential read, or broker action occurred.

`intraday-head-source-safe-collection-recovery-projection-v1` is now complete.
The new read-only host projection accepts only an exact task pointer, immutable
terminal `recovery/collection_exit_nonzero`, and its hash-bound same-run capture
receipt. It emits `rejected_duplicate_conflict` for the exact current receipt;
missing, malformed, unsafe, or binding-mismatched evidence becomes the distinct
source-safe `evidence_unavailable` fact, with no latest-receipt or mutable-index
fallback. It outputs no paths, rows, counts, prices, account fields, or secrets.
The focused reader, projection, and CLI checks passed 79 tests. Independent
review found and corrected the terminal-scope check; the required Claude CLI
challenge timed out as `review_unavailable`, not agreement or a hold.

`intraday-head-duplicate-conflict-provenance-v1` is now complete. Future
session-capture receipts record only the collector branch's categorical
`candidate_batch` or `retained_cache` origin and the retained-head disposition
`not_applicable`, `preserved`, or `quarantined`. The exact recovery reader
projects them only after the existing pointer/terminal/run/time/hash/coverage
binding passes. Historical receipts with both fields absent remain
`not_recorded_legacy`; partial, mixed-generation, unknown, and inconsistent
future fields fail closed as `evidence_unavailable`. No raw row, path, hash,
price, account, credential, KIS, task, order, model, or qualification surface
was added. Claude returned `supported-with-limits`; its non-destructive
quarantine and no-mutable-fallback limits are covered by tests. The task-owned
collector image was rebuilt without running it, so the next owned invocation
will use the new writer contract.

`source-local-session-reset-ema-mechanics-v1` is complete. Its immutable
`20260807-ema-mechanics-r2` external artifact binds the private
`kis.paper.private.intraday.qqq.nas.m1.*` catalog snapshot, selects the first
20 complete regular sessions within its explicit 2026 scope, and replays the
fixed session-reset 15/30 EMA through only the existing `source: local_paper`
seam. It records aggregate activation, replay, and terminal-flat evidence only;
the run is CPU-only and retains no raw prices, fills, PnL, performance,
selection, GPU, Paper-input, or broker claim. Evidence:
`D:\thericher-v2\model-artifacts\research\kis-intraday-session-reset-ema-mechanics-v1\20260807-ema-mechanics-r2\summary.json`.

`source-local-qqq-mtf-resampling-mechanics-v1` is complete. Its immutable
`20260807-qqq-mtf-r1` external Data receipt binds the verified QQQ/NAS
M1 catalog to the first 20 complete regular 2026 sessions and reports only
source-safe completed-bar geometry: M1 7,800, M5 1,560, M10 780, H1 120, and
H3 40. H1/H3 each explicitly drop the terminal 30-minute partial bucket for
every session; there are no incomplete buckets. It is CPU-only and creates no
provider, credential, broker, predictive, PnL, performance, selection, GPU,
Paper-input, or data-qualification claim. Evidence:
`D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-resampling-mechanics-v1\20260807-qqq-mtf-r1\summary.json`.

`source-local-qqq-mtf-window-feasibility-v1` is complete. Its immutable
`20260807-qqq-mtf-window-r3` external receipt binds the same 20-session
QQQ/NAS catalog and completed MTF mechanics receipt to the fixed 15:30 ET
`kis_baseline` profile: M1=30, M5=6, M10=3, H1=2, H3=2. It records only
aggregate causal-window geometry: 600, 120, 60, 40, and 40 completed window
bars respectively, with 20 explicit H1 and H3 terminal-partial exclusions.
The parent receipt hash is recomputed before use, so tampered or Git-resident
parent evidence is rejected. It remains source-local CPU input mechanics only
and creates no predictive, PnL, performance, selection, GPU, Paper-input, or
broker claim. Evidence:
`D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-window-feasibility-v1\20260807-qqq-mtf-window-r3\summary.json`.

The next bounded objective is shared Data/Engine
`source-local-qqq-mtf-window-matrix-v1` is complete. Its immutable
`20260807-qqq-mtf-matrix-r2` external receipt reattests the mechanics and
baseline-window parents before consuming the same 20-session QQQ/NAS local
catalog. It freezes the ordered `short`, `kis_baseline`, `one_hour`, `medium`,
`long`, and `extended` profiles at 15:30 ET, verifies every selected window
ends exactly at that cutoff, and retains aggregate geometry only. The fixed
profiles contain respectively 300/60/60/40/40, 600/120/60/40/40,
1200/240/120/40/40, 1800/360/240/40/40, 2400/720/240/40/40, and
3600/720/360/40/40 completed M1/M5/M10/H1/H3 window bars. Every profile
explicitly excludes 20 H1 and 20 H3 terminal partial buckets. It creates no
target, model, performance, selection, GPU, Paper-input, or broker claim.
Evidence:
`D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-window-matrix-v1\20260807-qqq-mtf-matrix-r2\summary.json`.

`source-local-ema-local-paper-pnl-attribution-v1` is complete. Its immutable
`20260807-ema-pnl-attribution-r1` artifact reattests the exact completed 15/30
EMA parent receipt, reconstructs only the same in-memory `source: local_paper`
replay, and applies existing FIFO realized-after-cost accounting independently
per terminal-flat session. It records 76 closed segments, 152 local-paper
fills, aggregate gross delta `-26.299200`, fees `10.8932`, and net delta
`-37.192400`; all fills are local-paper, all sessions are terminal-flat, and the
replay digest equals the parent. This is an exact 20-session retrospective
accounting result, not a decision-time-valid profitability, model-selection,
campaign, GPU, Paper-input, or broker conclusion. Evidence:
`D:\thericher-v2\model-artifacts\research\source-local-ema-local-paper-pnl-attribution-v1\20260807-ema-pnl-attribution-r1\summary.json`.
Focused EMA attribution checks passed 17 tests; the CPU-only local-cache smoke
completed without KIS, credential, or broker access; and the authority suite
passed 2,797 tests with 25 skips, plus Ruff and both Compose configurations.

`intraday-m1-collector-duplicate-conflict-recovery-v1` is complete. The
task-owned `session-capture` route already preserves an active causal head on a
retained-cache conflict; no speculative change to a live collector branch was
warranted while the exact 06:20 KST receipt remains
`not_recorded_legacy`. A new fake-client restart regression repeats the same
conflict and proves the active chunk, manifest bytes, raw bytes, head cursor,
and snapshot count remain unchanged. The source-safe Claude challenge was
`uncertain` because its isolated invocation could not inspect the workspace, so
it was not treated as agreement. The focused collector/capture/projection/CLI
suite passed 81 tests with no KIS, credential, account, order, or live route.

`kis-paper-iwm-m1-current-head-ingestion-v1` is complete. The isolated writer
passed fake-client CPU checks, then made one authorized IWM/AMS current-day
page request at 2026-08-07 01:46 UTC. It retained one immutable external
snapshot, observed no continuation, and left the QQQ/SPY task, cache, cursor,
and schedule untouched. It is source-local and non-promoting. Claude returned
an incomplete tool request rather than a verdict, so this implementation relies
on the focused local tests and is not described as Claude agreement.

`kis-paper-iwm-m1-current-head-replayability-v1` is complete. Its local-only
reader verifies the snapshot's target, canonical manifest/raw/content hashes,
row shape, timestamp conversion, and generic M1/M5/M10/H1/H3 resampling. The
original v1 receipt does not bind a snapshot identity, so the actual retained
snapshot replays only as `completion_evidence_unavailable`: it emits no
completed Bars or buckets rather than assigning an unproven collection time.
The writer now emits a v2 source-safe receipt that binds the immutable snapshot
content digest, and the reader accepts a completed Bar only through that exact
binding. Independent Validation caught the pre-binding defect and a linked
artifact-directory creation risk; both have focused regression coverage. The
Claude drift check timed out as `review_unavailable`, not agreement.

`kis-paper-iwm-m1-bound-observation-v2` is complete. One authorized isolated
IWM/AMS current-day page request was accepted, observed no continuation, and
reused the already-retained immutable snapshot. Its new v2 receipt binds that
snapshot's content digest. The offline replay accepted the exact bound pair and
reported 120 completed M1 bars, 8 completed M5 buckets, 1 completed M10 bucket,
and no complete H1/H3 bucket. This is aggregate source-local mechanics only:
provider finality and decision-time availability remain `not_observed`, and no
model, Paper input, account, order, or QQQ/SPY state changed. Claude again
returned an incomplete tool request rather than a verdict, so it is
`review_unavailable`; independent Execution review confirmed the one-page
market-data-only route and its cache-isolation kill condition.

`iwm-m1-v2-observation-ledger-v1` is complete. The offline selector lists only
source-safe immutable IWM receipt metadata and requires a caller-selected
opaque observation ID for CLI replay; it never falls back to a mutable latest
record. The actual v2 observation reattached alongside the legacy v1 receipt
and replayed the same aggregate 120 completed M1, 8 M5, and 1 M10 bucket with
no H1/H3 bucket. Independent Validation found a time-order versus hash-order
duplicate-check defect before integration; the order-independent fix and
regression passed. The selector made no provider, credential, QQQ/SPY,
account, order, Paper, model, GPU, PnL, or qualification change. Claude's
request produced no usable verdict, so it remains `review_unavailable` rather
than agreement.

The next bounded objective is Data-owned
`iwm-m1-prospective-observation-append-v1`: make the isolated IWM/AMS
current-head route append-safe. Identical content may reference its immutable
snapshot again, while changed content must become a distinct immutable
observation instead of silently overwriting or mixing a prior head. This
remains a prospective source-local path; historical M1 coverage requires a
separate endpoint-reach package.

`iwm-m1-prospective-observation-append-v1` is complete. The existing isolated
writer now returns the opaque selected observation ID on a successful opt-in
collection; successful v2 observations append only to the selector root, while
unavailable or rejected source-safe outcomes go to a separate outcome root.
The selector ignores only an owned stale staging filename and the exact
pre-append source-safe failure shape; it still rejects malformed or ambiguous
final evidence. Raw snapshots remain content-addressed: equal content reuses
the snapshot, while changed content becomes another immutable revision.
Each successful physical collection receipt remains separately selectable; an
exact repeat after the snapshot is already retained becomes idempotent. Focused
tests cover repeated content, changed heads, failure isolation, interrupted
receipt publication, restart, link rejection, and explicit replay. One bounded
KIS Paper IWM/AMS page attempt was accepted, reused the existing snapshot, and
its exact new v2 receipt replayed offline. The current inventory is one legacy
incomplete receipt plus two bound observations; completed local geometry remains
120 M1, 8 M5, 1 M10, and no H1/H3 bucket. The observed one-page attempt
completed within the `5-10s` elapsed bucket with no categorical error or
continuation. It adds no historical-reach, finality, model, Paper, account,
order, PnL, or QQQ/SPY claim. The Claude request did not return a usable
verdict before the bounded review window, so it is `review_unavailable`.

The next bounded objective is Data-owned
`kis-paper-m1-historical-reach-probe-v1`: measure the exact QQQ/NAS and
SPY/AMS KIS Paper M1 endpoint reach, continuation, and pace with a tiny
target-isolated serial probe. It must preserve the existing scheduled collector
and treat every source-limited outcome as scoped evidence rather than a
provider-wide conclusion.

The orchestration projection is now compact and current-only: it retains the
company objective, ready/owned/due work, bottleneck, reversible improvement,
and recovery action in 57 lines while Git and external artifacts retain
history. Claude's required governance check timed out as `review_unavailable`,
not agreement or a hold; independent consistency checks retained all due and
recovery facts. The existing daily operating-review automation now uses that
projection and the clean-root parallel authority helper. Its prompt alone was
updated; identity, 08:10 daily schedule, active status, model, project target,
and workspace were read back unchanged, with no secret-like value present.

`same-cycle-target-allocation-v1` is now complete. Its pure helper preserves
caller order, requires a consistent shared snapshot and unique market/symbol
identities, invokes the existing scale-then-cap rule serially, and consumes
capacity only for accepted enters. It neither ranks symbols nor releases
capacity for an unexecuted reduction/exit, and it has no data, model, state,
local-Paper, KIS, or broker surface. The Claude check again timed out as
`review_unavailable`; 14 focused tests and the 2,707-pass, 25-skip authority
suite passed. The next bounded objective adds a minimal source-safe binding
from a terminal receipt to its exact same-run cumulative-coverage receipt;
it changes no scheduler, KIS route, Paper order behavior, or model eligibility.

`kis-paper-virtual-lifecycle-canary-v2` remains completed through the existing,
task-owned deterministic canary. The resulting virtual-Paper lifecycle is
execution evidence only, never a model, fill-quality, PnL, or profitability
result.

The existing `thericher-kis-paper-quote-session` Windows task completed its
2026-08-05 23:35 KST invocation with Task Scheduler result `0`. Its exact
scheduled-session receipt `paper-session-20260805T143501171367Z` is
`canary_completed`, requiring the direct lifecycle receipt
`canary-20260805T143501171367Z`. The independent offline validator and exact
projector both classify that lifecycle as `cancelled` with `clean`
reconciliation and `not_eligible` attribution. This is a categorical
cancelled-and-clean virtual-Paper result, not a broker fill, PnL, or model
result. Its later 2026-08-07 23:35 KST task-owned receipt
`paper-session-20260807T143501281497Z` independently reattaches as
`canary_completed` at `intent_recorded`, bound only to direct lifecycle
`canary-20260807T143501281497Z`. That lifecycle is `not_submitted` with
`not_submitted` sizing, `not_observed` submit response, `unresolved`
reconciliation, and unavailable attribution. It is not a submit, fill, PnL,
or model result and creates no manual-recovery action. The existing task owns
the next opportunity at 2026-08-10 23:35 KST; do not manually invoke or
duplicate it.

The existing `thericher-kis-paper-quote-session` Windows task completed its
2026-08-04 23:35 KST invocation with Task Scheduler result `0`. Its exact
scheduled-session receipt is `paper-session-20260804T143501870818Z`, which
reattaches only `recovery_required/prior_submission_unresolved` to the
preserved run `canary-20260722T184759527919Z`; the independent lifecycle
validator also reports `outcome_unknown/unresolved`. This is not a new
lifecycle, broker, fill, no-intent, or PnL result. Do not manually invoke,
infer an outcome, or duplicate the task; the later 2026-08-07 receipt is the
current exact lifecycle evidence and the next task-owned opportunity is
2026-08-10 23:35 KST.

The matching 2026-08-04 23:50 KST daily SPY session receipt is exactly
`daily-spy-20260804T145002356832Z`: `no_intent/quote_unavailable`, with no
run identity and both receipt observer and terminal-field probe
`not_attempted`. It is a categorical daily-session no-intent only, not a
broker, fill, or PnL fact. The 22:15 KST daily-head task exited `0` but still
has only the static `producer_path_missing` consumer trace. The 06:20 KST
intraday-head task exited `20`; its exact safe runtime is
`intraday-head-20260804T2120059626443Z`,
`recovery/prospective_session_id_unavailable`. That anomaly is local to the
downstream session binding; its later 2026-08-06 06:20 KST scoped recovery is
recorded in the current outcome above.

The current daily-SPY session image preserves `quote_unavailable` only for a
fresh quote-fetch failure and emits `receipt_preparation_unavailable` for a
local receipt/limit-preparation failure. This changes neither the preserved
08-04 receipt nor any Paper call, intent, or schedule. Its 141 focused
execution tests and the 2,573-pass, 23-skip parallel authority suite passed;
the existing single `IgnoreNew` task was rebuilt for 2026-08-05 23:50 KST.

Engine Research independently re-retrieved QuantConnect LEAN's Apache-2.0
Donchian channel source and prepared a pure session-reset `20/10` long/flat
rule with causal, contiguous completed-bar tests. Its separate model-side
adapter requires caller-declared exposure, confidence, and TTL before emitting
only a `TargetExposureProposal`, and caps ready-target validity at the declared
session close; it never creates an order. Both modules
perform no I/O and have no KIS, broker, data-collection, backtest, GPU, or
Paper connection. This is only a source-verified engineering baseline: the
source has no adopted market evaluation claim and the current data remains
insufficient for a campaign, profitability, or promotion conclusion.
Hermetic injected-bar tests now compose a Donchian breakout and later breakdown
through the existing research receipt and `source: local_paper` next-bar
fill/replay path; insufficient history yields no local intent. They create no
runtime route, KIS call, campaign, PnL result, or promotion claim.
Target-derived local-paper intents now retain their bounded `valid_until`
through durable replay: late submission or next-bar fill is categorically
rejected, while an already recorded fill remains exactly replayable.

At 03:16 KST on 2026-08-05, one exact read-only historical terminal-field
probe ran for the preserved legacy state. It used only a virtual token and the
history GET route, returning `history_observed_derived_date` with an absent
identity row. Because its ET day is derived from a tightly checked legacy
creation timestamp, that result is not a no-order, cancellation, terminal,
fill, or PnL conclusion; the legacy state remains `outcome_unknown`.

The quote-session runner now recovers only an exact replayed run from its own
durable state. A distinct new run retains the shared lock and its fresh
account/open-order reconciliation, which blocks a current matching open order
before submit. It no longer scans or mutates unrelated historical state files.
The old state is preserved, not relabeled clean. At 03:50 KST, a new
source-free Claude drift review returned `supported-with-limits`: it supports
the virtual-host, durable-intent, lock, fresh-account/quote, and current
open-order kill tests, but it leaves unqualified a distinct historical unknown
that is not yet visible in KIS's current open-order view and a runner failure
between submit and reconciliation. Those are scope limits, not an inference of
an order or a global Paper hold. Temporary Validation independently classified
that concern as a documented scope limit, not a pre-23:35 task contract
violation; its strongest missing evidence is delayed broker visibility after a
prior distinct unknown. Focused fake-route tests cover same-run recovery,
old-state preservation, and current-open-order no-submit behavior.

Verification for this recovery package passed 129 focused execution tests and
the authority parallel suite with 2,543 passed and 23 skipped. Full Ruff and
all required Compose configurations passed, and the current `kis-paper-session`
image was rebuilt for the existing task. A separate serial `pytest -q`
diagnostic exceeded the desktop ten-minute command limit and is not a passing
result; the already-passing authority suite remains the required verification
for this private Paper change.

The offline projector now also accepts one explicit session ID. It rejects
links, `.`/`..`, mismatched IDs, and non-writer evidence shapes, emits a
distinct session fact without its evidence path, and never scans for a latest
artifact. A pre-canary runtime whose safe ID is `paper-session-*` can bind that
exact receipt. For `prior_submission_unresolved`, the prior direct-canary
runtime remains `outcome_unknown`/`unresolved`; it is not overwritten by a
generic session runtime and still requires direct lifecycle reattachment.

The 23:15 D1 stability observer and retimed intraday-head worker also remain
task-owned with `IgnoreNew` concurrency. The D1 observer completed its first
23:15 KST receipt as `stable`: one `dailyprice` GET, no retry or foreground
wait, and an independently verified 15--90-minute snapshot comparison. It is
observational only, with `provider_finality: not_observed`, and cannot qualify
an Engine or Paper consumer. The next intraday-head collection is task-owned at
00:29 KST on 2026-08-07.

On its next successful collection, the existing retimed intraday-head worker
also dispatches the already implemented QQQ 90-minute observed/provisional
baseline before slower observers can exhaust its two-minute freshness budget.
It preserves the worker observation timestamp, so a retained candidate replay
bar that began earlier yields the scoped `decision_after_replay_bar` no-intent
rather than a backdated local fill. The virtual-only receipt canary and
network-disabled exact-session validator remain separate; there is no new
schedule or broker route. It may record a scoped `no_intent` or lifecycle fact,
never an alpha, PnL, or promotion result. The source-free Claude challenge
timed out (`review_unavailable`), while the host dispatcher simulation and
focused execution tests passed.

## Current Lane Facts

### Data

- Market data remains under `D:\market_data`; generated artifacts remain under
  `D:\thericher-v2\model-artifacts`.
- The latest 04:24 KST intraday-head receipt is
  `recovery/prospective_validation_payload_unavailable` with Scheduler result
  `20`: collection `exit_zero`, exact QQQ Paper-only session `no_intent`, and
  offline validation `unavailable`. It has no broker lifecycle, fill, PnL,
  alpha, or model meaning. Its terminal receipt has no same-run capture-receipt
  hash/digest binding, so coverage is deliberately not inferred. The existing
  task owns 06:20 KST; no manual invocation follows.
- One authorized standard-Tiingo-EOD retrieval completed at 2026-08-04 23:13
  UTC for the fixed `SPY`/`QQQ`/`IWM` scope. Its immutable external snapshot
  has 39 normalized rows through source date 2026-07-28 and reattests offline
  without a token or network path. It is future-lineage only: it cannot
  qualify historical D1 controls, model training, ranking, Paper input, or an
  order action.
- The KIS current-head collector last closed as the scoped
  `minute_duplicate_conflict` from a stale `retained_cache` candidate; the
  historical quarantine remains evidence only. Its 2026-08-05 02:31 KST
  collection exited zero, then its downstream QQQ session could not bind an
  exact ID, producing scoped recovery `20` with no broker action. Do not infer
  its downstream stage or manually rerun it. The former 04:31 KST task's terminal
  receipt is separately `recovery: collection_exit_nonzero`: its fresh token
  start followed the 04:30 SPY-prefix collector inside the existing
  cross-process five-minute token-start guard. Its downstream QQQ/Paper stages
  are all `not_applicable`, and the existing worker owns the 06:20 KST retry.
  Its terminal writer now advances one task-owned current
  pointer only after the immutable source-safe receipt exists. The host
  projector reattaches that pointer only when its exact non-link receipt hash,
  run identity, observed timestamp, and terminal category agree; it makes no
  KIS, Docker, network, or credential call and never selects a latest artifact.
- A metadata-only QQQ row-key inspection then established that the successful
  pages covered 09:32--11:31, 11:32--13:31, and 15:20--15:59 ET, while the
  missing mid-session range was caused by the 04:31 guard collision. After
  Claude returned `supported-with-limits`, Codex re-registered the same
existing single-action, four-run `IgnoreNew` task at 00:29, 02:28, 04:24,
and 06:20 KST. The 04:24 time leaves 5m30s before the prefix control and
six minutes before the prefix collector. The scheduled four-run session is the
sole coverage setup; the terminal 06:20 KST session capture is the kill test: its
observed-ET cumulative coverage must show 390 completed regular-session
minutes without guard/concurrency failure. The rebuilt existing image emits
this metadata-only cumulative projection from the local index/manifests while
preserving separate exact-run coverage; it excludes adjacent dates and is not
a causal, finality, Engine, or Paper input. DST/pre-market behavior remains
unproven; this is a reversible current-season repair, not an input promotion.
  Focused schedule checks (18) and the full parallel authority suite
  (2,571 passed, 23 skipped) passed after task registration.
- New `session-capture` executions preserve an existing causal head snapshot
  when a later post-close candidate conflicts, and reject that candidate
  pending bounded reconciliation. They do not auto-prefer revised post-close
  values or create a model input. The rebuilt Docker image carries this change;
  Claude's source-safe check was `supported-with-limits` and 65 focused
  collector/session-capture tests passed.
- The existing KIS M1 cursor chains for QQQ/NAS and SPY/AMS are terminally
  `source_exhausted` after their retained 2026-06-22 through 2026-07-21 spans
  (about 20,000 rows per target). The offline reattachment issued no market
  request and created no snapshot. This is an exact route/cursor fact, not a
  general KIS historical-retention claim; do not invent a timestamp seed.
  A source-safe geometry assessment finds 21 shared complete 09:30--15:29 ET
  sessions, enough only for a source-local non-promoting 5--90 minute preflight;
  decision-time availability and model/Paper eligibility remain false. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-m1-cursor-session-geometry-v1\assessment.json`.
- The offline QQQ local-retention helper binds a verified catalog to exact index
  metadata. Its runtime-window projection binds one ready 90-bar input manifest
  to a named `decided_at` and reports local availability only when the selected
  bars were retained no later than that time. It rejects source/lineage,
  conflict, candidate-conflict, and incomplete-row mismatches; provider
  decision-time availability and finality remain `not_observed`. The named QQQ
  prospective route now consumes it before any KIS client interaction, ending
  as a scoped no-intent when local retention is missing or late. It remains
  outside model training, GPU allocation, PnL, and general Paper eligibility.
- A one-page, current-day-only KIS Paper IWM/AMS M1 capability probe was
  accepted. Query, client, and transport boundaries all prohibit previous-day
  and continuation use, and the probe discarded returned rows. This establishes
  only a provisional current-page route; it does not establish historical reach,
  venue correctness, session finality, decision-time availability, a qualified
  dataset, or model/GPU/Paper eligibility. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe\iwm-ams-candidate-assessment-20260804-r1.json`.
- A bounded metadata-only probe of the existing Yahoo intraday-starter M1
  manifest is `input_unavailable` for the new five-minute ORB source family:
  it has an eight-day request span, one successful symbol, and no explicit
  regular-session or decision-time-availability field. It is not reopened as a
  raw-data scan, provider qualification, campaign, model, GPU, PnL, or Paper
  input. Evidence:
  `D:\thericher-v2\model-artifacts\data\yahoo-intraday-starter-orb-input-probe-v1\assessment.json`.
- `thericher-kis-paper-spy-prefix-negative-control` and
  `thericher-kis-paper-spy-prefix-feasibility` completed their 2026-08-05
  04:29:30 and 04:30 KST attempt. The negative control was clean; the exact
  SPY/AMS M1 run accepted one page with 119 completed prefix minutes, 241
  missing, an invalid seam, and no next cursor. The legacy receipt did not
  retain a safe terminal continuation category, so the offline projection marks
  it `not_recorded_legacy`; it cannot distinguish a blank/absent response
  signal from an unrecognized nonblank one. New exact runs retain only a safe
  category, never a raw response-header value. It used one in-memory client,
  one token attempt, and one minute-page attempt. This is an exact pagination
  observation, not a provider-wide KIS conclusion. Its existing worker owns
  the next attempt. Its existing collector/observer images were rebuilt and
  the same tasks re-registered for the safe-category contract; trigger times,
  `IgnoreNew`, and zero restart count are unchanged. The cache can establish
  only post-collection availability, never retrospective decision-time
  availability.
- The daily pair-forward cache is `cache_current` only for its named source
  contract. The metadata-only QQQ readiness observer is independent and has no
  qualified future-window record.
- The installed 22:15 KST SPY D1 head task currently produces a verified
  prior-session cache snapshot, not a capability/qualification or a
  provider-finality/decision-time availability fact. Its static trace is
  `producer_path_missing`. The reviewed
  `thericher-kis-paper-daily-spy-stability-observer` is installed for 23:15
  KST on weekdays and owns the first distinct, exact-scope D1 comparison. It
  uses the shared KIS request/token gates, a nonblocking external receipt lock,
  and at most one virtual-Paper `dailyprice` attempt after a verified
  15--90-minute-old snapshot and successful authentication. Its first
  task-owned 23:15 KST receipt is `stable`: one GET, no retry or foreground
  wait, and an independently validated two-read row-hash match. `stable` can
  mean only matching prior-session row hashes; it always retains
  `provider_finality: not_observed` and remains Engine-unreadable. Do not build
  a consumer bridge from it alone. Evidence:
  `D:\thericher-v2\model-artifacts\data\daily-spy-input-readiness\static-trace-20260804-r1\assessment.json`.
- The broad KIS D1 current-listing panel is a source-local research control,
  not a point-in-time, adjusted, corporate-action-qualified, or Paper-ready
  dataset. Historical minute reach remains endpoint-limited.
- Norgate NDU is running and its new aggregate capability receipt is
  `qualified_for_offline_research` only. The latest verified fixed-ETF D1
  snapshot came from a 1990--2026 request but contains only 512 common sessions
  from 2024-07-18 through 2026-08-03 and 1,536 rows. This measures the trial's
  current useful daily reach; do not repeat the same full-history request
  without a changed provider fact. Its source-safe structural receipt attests
  only the raw-file geometry and manifest/hash contract, not eligibility. The
  trial does not establish PIT, ranking, model, GPU, PnL, or Paper eligibility.
  Its raw snapshot remains under `D:\market_data`; use it only through its
  source-local contract. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-fixed-etf-d1-structural-integrity-v1\assessment=bf7d5fceae6b2d345dc75132a6e361f79799e6fb419498d8091f180306aaf1aa\assessment.json`.
- The same 512-session Norgate snapshot now has one explicit, double-read
  current-build conformance receipt with 1,536 reference and active bars and
  zero divergences. A hash-bound dividend-marker hygiene sidecar independently
  verifies 24 nonzero markers, 72 exclusions, and 55 distinct masked date
  groups. These results prove neither vendor correctness, publication timing,
  PIT eligibility, adjustment/corporate-action semantics, nor consumer
  eligibility. The proposed range diagnostic is now `input_unavailable` on an
  exact sample-budget kill test: its 20-observation window yields 277 eligible
  date-group rows with a longest contiguous run of 37, below its declared
  382-group split budget. Claude independently returned `unsupported` on that
  arithmetic constraint; the matching external sidecar retains its own
  source-safe evidence. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-active-build-revision-v1\revision-current-512-20260804-r1\receipt.json`.
- A current local-client tail probe resolves the `US Equities` update timestamp
  to exactly one active data root,
  `D:\market_data\us_equities\norgate_us_platinum_trial`. Its predeclared
  2026-06-23 through 2026-08-04 D1 window has 29 common SPY/QQQ/IWM sessions,
  below its separate 126-session minimum, so its status is
  `input_unavailable`. It validates client/root binding only: it neither
  rebuilds the frozen snapshot nor changes model, GPU, PnL, or Paper
  eligibility. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-trial-tail-readiness-v1\tail-active-build-20260804-r2`.
- An official free-source check found no single public panel that establishes
  point-in-time membership including delistings, corporate-action semantics,
  and daily OHLCV. SEC Market Structure and EDGAR can be bounded sidecars only,
  not a qualified model or Paper input. Its 2025 Q4 sidecar ZIP is 22.4 MB, but
  a scripted probe needs a designated contact User-Agent; no data was retained.

### Engine Research And Stewardship

- No frozen, input-qualified campaign is ready. The RTX 4090 is free by design;
  do not manufacture training to fill it.
- The completed Granite TTM R1 run is a structural CPU/CUDA compatibility
  receipt only. It has no market input, forecast score, model selection,
  checkpoint promotion, ensemble, or Paper consequence.
- The existing Chronos-T5 Tiny R4 CPU/CUDA zero-shot diagnostic was reattached
  after its verifier was repaired for legacy manifest record ordering.
  Its static Norgate development-panel input, hidden pretraining scope, and
  contract keep it source-local, non-PIT, non-promoting, and ineligible for
  Paper, model selection, or further GPU allocation. Its CUDA diagnostic did
  not surpass the fixed zero-return directional baseline. Evidence:
  `D:\thericher-v2\model-artifacts\research\chronos-t5-tiny-norgate-d1-probe-v1\chronos-t5-norgate-d1-actual-r4`.
- Chronos-T5 Small is an independently retrieved Apache-2.0 source-only
  candidate. Its forecast input is documented, but its pretraining
  period/financial-instrument scope and hidden-representation interface are not
  disclosed. It has no downloaded weights, execution, campaign, GPU, ensemble,
  Paper, or profitability consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\chronos-t5-small-20260804-r1\source-retrieval.json`.
- Moreira and Muir's volatility-managed exposure is independently retrieved as
  a source-only sizing candidate. Its monthly realized-variance mechanism
  needs a future frozen causal D1 baseline and qualified later evaluation
  input; it has no campaign, GPU, PnL, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\volatility-managed-exposure-20260804-r1\source-retrieval.json`.
- The independently retrieved extreme intraday shock-reversal mechanism is a
  source-only event-triggered mean-reversion candidate. The project lacks its
  source-style liquidity/spread inputs, 60-session per-symbol seasonal M1
  baseline, completed-bar availability evidence, and candidate-specific replay
  parity, so it has no campaign, GPU, PnL, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\kis-intraday-extreme-shock-reversal-20260804-r1\source-retrieval.json`.
- The independently retrieved session-reset VWAP directional-state source is
  `source_only_input_unavailable`. Its source-native state holds to a later
  VWAP-side change or session close, not the discovery handoff's fixed
  30-minute horizon. The current M1 cache lacks observed decision-time
  availability and candidate-specific replay parity, so it has no campaign,
  code, GPU, PnL, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\qqq-session-vwap-state-continuation-20260804-r1\source-retrieval.json`.
- The independently retrieved five-minute opening-range-breakout source is a
  distinct `source_only_input_unavailable` technical-rule candidate. Its
  source-native screened form needs a contemporaneous multi-symbol universe,
  prior 14-session liquidity/ATR facts, and relative opening-range volume; the
  current two-ETF, 21-session M1 cache lacks those inputs and observed
  decision-time availability. It has no campaign, code, GPU, PnL, or Paper
  consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\us-equity-five-minute-orb-20260804-r1\source-retrieval.json`.
- Closed or non-reusable historical families include QQQ MTF consensus,
  first-30/final-30 momentum, MTF logistic, lower-tail quantile preflight,
  Tiingo rotation/sequence controls, and static broad-D1 benchmarks. The Tiingo
  raw-D1 source now also has a 330-marker/990-row external hygiene sidecar;
  this does not change its non-PIT, non-Paper scope. A later research package
  must state a distinct hypothesis, causal source, temporal split, cost model,
  baseline, kill test, and data lineage.
- The fixed prospective SPY MTF baseline remains a data-timing control only.
  It needs a future qualified source receipt before any model, GPU, or Paper
  interpretation.

### Execution

- The canary is virtual-host-only at
  `openapivts.koreainvestment.com:29443`, HTTPS, no redirects, and the existing
  quote/account/order/cancel allowlist.
- It persists one durable intent before a broker effect, uses a shared state
  lock, requires a fresh account/open-order view and fresh quote-derived limit,
  rejects matching open orders, uses `cancel_after_submit`, and reconciles an
  exact unknown only on a same-intent replay. A distinct run does not scan or
  mutate historical state files; it relies on its own current open-order check.
  It never reads a live route.
- The at-most-one-concurrent-submission claim is scoped to the existing single
  host-owned state root and shared `.canary_execution` lock. The 23:35 KST
  quote-session checkpoint and separate 23:50 KST daily-SPY receipt session
  both use that root, so they cannot submit at the same time and a matching open
  order blocks a fresh canary. Their lifecycle purposes remain distinct. No
  copied/restored state root, second machine, or out-of-band runner is
  installed; those would be outside this task's contract, not a general Paper
  hold.
- The offline validator accepts completion only for `paper_only`, terminally
  cancelled, cleanly reconciled, freshness-valid evidence. The credential-free
  loopback dashboard cannot call a broker or submit an order; authenticated
  local emergency and pause controls may change only their local control state.
  Its account projection omits prices and order identifiers.
- The private dashboard is reattested in Docker. Direct serving accepts only
  `127.0.0.1`; the container's `0.0.0.0` listener requires the explicit
  `--allow-container-bind` exception and Compose publishes it only as
  `127.0.0.1:8787`. Its actual local UI rendered unavailable Paper facts rather
  than invented values, and a pause-buy/resume-buy UI round trip changed only
  persisted local control state. The requested concise Claude drift-check timed
  out, so its outcome is `review_unavailable`, not a dashboard decision.
- The named `kis-readonly` bridge completed one actual KIS Paper account refresh
  at `2026-08-07T05:41:03.199117+00:00`. Its fact-minimized external receipt is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge\20260807T054103199117Z-complete.json`;
  it records only paper/read-only capability, currencies, and counts. The
  loopback dashboard immediately read it as `available`. This created no order,
  quote, market-data, or live request. The runtime snapshot still expires after
  five minutes, so availability is not a lasting account assertion.
- The installed `thericher-kis-paper-snapshot-observer` Windows task is the
  sole recurring owner of this same bridge. It starts in a bounded weekday KST
  window, repeats every four minutes inside the five-minute snapshot TTL, uses
  Task Scheduler `IgnoreNew`, a named host mutex, and a bridge-level advisory
  runtime-volume refresh lock. Its installed Task XML passed a direct ten-check
  action/cadence/concurrency/state reattestation without a KIS, Docker,
  credential, or account-artifact read. The credential-free inspector returns
  the known 2026 session close and the runner rechecks it immediately before Docker, so it
  skips an invocation with four minutes or less remaining. The current
  off-session check returned only
  `outside_regular_session` and made no Compose or KIS call. A busy bridge
  preserves its prior snapshot and creates no evidence artifact. Every later
  eligible refresh remains task-owned. Tagged `complete` and `unavailable`
  bridge outcomes now write an immutable external observer receipt that binds
  the marker, categorical outcome, and timestamp to the final bridge receipt's
  SHA-256; it carries no account facts or diagnostics. The reader requires the
  hash plus matching bridge marker/status/time/reason; the bridge CLI emits its
  marker only after that check and the runner compares it to its fresh UUIDv4.
  The current Docker bind mount passed an isolated no-network hard-link and
  collision-rejection probe. A missing receipt is unknown, and the marker is
  only assumed-honest-host observer evidence rather than proof of a Windows
  Scheduler launch; this host's Task Scheduler Operational log is disabled.
  The host-only `reattest_kis_paper_snapshot_observer.py` requires one exact
  observer sidecar path, recomputes its bound bridge hash, and prints only the
  categorical read-only fact; it never selects a newest receipt or calls KIS,
  Docker, the dashboard, or a credential path. Its missing/tampered outcome is
  `observer_evidence_unavailable`, not a rerun instruction.
  The caller-selected sidecar
  `D:\thericher-v2\model-artifacts\execution\kis-paper-snapshot-observer\20260807T141607347092Z-7c9fb50a-81bb-40a8-b72f-49b3e492d773-complete.json`
  reattached as `complete` at `2026-08-07T14:16:07Z` with `read_only` scope and
  no submit capability after its bridge SHA-256 and marker/status/time binding
  passed. The credential-free loopback dashboard `/health` returned only `ok`
  and `broker_calls: false`; no account fact was read. This is marker-present
  observer provenance under the assumed-honest host, not cryptographic proof
  of Scheduler origin; Task Scheduler Operational logging is disabled.
  The required Claude schedule and correction challenges timed out, so record
  `review_unavailable`, not agreement or a new hold.
- The local dashboard now replays FIFO realized-after-fee PnL only from closed
  `source: local_paper` lots. It leaves open lots unvalued and excludes every
  KIS account/broker fact, so it is descriptive simulator accounting rather
  than a fill-quality, profitability, model, or execution-risk input. The
  related Claude request returned unrelated stale task text, so classify that
  review as `review_unavailable`, not as agreement or a decision boundary.
- The latest safe private-state inventory has no `submitted` or
  `cancel_started` canary phase. Historical unknowns remain scoped to their own
  reconciliation paths; only an exact matching pending canary defers the next
  matching quote session.
- The host lifecycle projector and independent offline lifecycle validator now
  require a direct non-link receipt path and matching requested/recorded
  `run_id` before emitting a sanitized fact; missing or unsafe evidence remains
  `unavailable`/exit-2. Their 82 focused tests use no broker or credentials.
  The short Claude design check produced no verdict (`review_unavailable`), so
  this source/test repair does not alter the scheduled task or execution
  authority.
- `quote-session`, `daily-spy-head`, and `daily-spy-session` are explicitly
  Monday--Friday KST. This restores Monday US-session coverage without changing
  services, order logic, sizing, or KIS routes.

## Current Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Execution | Exact 08-07 scheduled receipt is `canary_completed/intent_recorded`; direct lifecycle independently validates as `not_submitted/unresolved`, attribution unavailable, with no submit, fill, PnL, or model result. The 08-05 `cancelled/clean` result remains historic. Next owned canary opportunity is 2026-08-10 23:35 KST |
| SPY D1 stability observation | Data | Exact 08-07 receipt `d1-stability-20260807T141501Z-attempt-04-c5e2cd1a0693` is `stable`: one unadjusted GET, zero retry/foreground wait, provider finality `not_observed`. It remains observational only. Next owned observation is 2026-08-10 23:15 KST |
| Current-head receipt binding | Data / Execution | The exact 06:20 KST pointer/terminal is `recovery/collection_exit_nonzero` with a verified `incomplete` same-run capture binding. Its historic targets now project as `not_recorded_legacy`; future receipts carry collector-time duplicate-conflict provenance through the same exact bound chain. QQQ/v4 remain `not_applicable`. |
| SPY paginated-prefix capability | Data | First exact receipt is `measurement_incomplete_or_invalid`: clean control, one accepted page, invalid seam, no next cursor; legacy terminal signal is `not_recorded_legacy`, and the rebuilt existing worker owns the next attempt |
| Session-reset Donchian mechanics | Engine Research | Completed immutable source-local `2026-08-06-r1` preflight from the deterministic first 20 complete QQQ/NAS M1 sessions. Causal prefix hashes, `source: local_paper` replay, terminal-flat mechanics, and explicit no-rule-activation classification pass; no PnL/performance output, GPU, promotion, or Paper-input consequence |
| Session-reset EMA state rule | Engine Research | Pure 15/30 completed-M1 long/flat rule and rule-specific structural target adapter. Hermetic receipt-to-`local_paper` entry/exit/pending-restart replay verifies causal/warmup/hold/expiry controls and next-bar-open pricing; deterministic local execution now rejects a late-accepted historical fill. No source-local data replay, campaign, GPU, PnL, or Paper-input consequence |
| Private Paper dashboard | Execution / Infra | Completed Docker reattestation: explicit container-bind exception, host loopback publish, secret-free unavailable rendering, and pause/resume UI round trip. It created no broker route or order. The existing read-only snapshot observer is the only recurring refresh owner. |
| Read-only Paper account snapshot | Execution / Infra | Completed one actual `kis-readonly` refresh: categorical `complete`, external fact-minimized receipt, immediate loopback dashboard `available`, no order or live route. The bounded five-minute-TTL observer is installed and task-owned. |
| Read-only Paper account observer | Execution / Infra | Completed task-owned evidence: caller-selected immutable sidecar `20260807T141607347092Z-7c9fb50a-81bb-40a8-b72f-49b3e492d773-complete.json` reattached as `complete` at `2026-08-07T14:16:07Z` after bridge SHA-256 and marker/status/time binding. Loopback dashboard `/health` returned only `ok` and `broker_calls:false`; no account fact was inspected. This is assumed-honest-host marker provenance, not cryptographic Scheduler proof; Operational logging is disabled. The four-minute observer remains the sole recurring read-only owner. |
| GPU research | Research Steward | Idle because no eligible frozen campaign exists |

An external wait belongs to its worker. Do not foreground-sleep, add a duplicate
schedule, or turn a source result into an approval hold while another lane is
ready.

## Current Recovery And Review Facts

- The repo worktree still has no current runtime projection. The exact external
  2026-08-04 scheduled-session receipt and independent offline validator agree
  only on the preserved legacy `outcome_unknown/unresolved` recovery state;
  this is not evidence of a new canary lifecycle.
- The 2026-08-04 recovery review returned `supported-with-limits`: keep the
  preflight exact-scope, prohibit a fresh submit from recovery, preserve a
  remaining ambiguity as a session-scoped result, and retain the shared lock.
  It is a challenge result, not authority or a broker outcome.
- A later Claude CLI call returned `unsupported` from a mismatched workspace:
  it cited absent `docs/` and `attestations/` paths and a stale Git history,
  while the current tree contains the canary module, projector, and allowlist
  tests. Classify that response as `review_invalid_workspace`, not as a
  substantive adverse verdict or a canary hold. No execution boundary changed.
- A current canary drift review first returned `uncertain`, then
  `supported-with-limits` after source-free code/test reattestation of direct
  virtual-host transport, pre-submit durable state, prior-run recovery, and
  broker-timestamp quote age. Its remaining limit is the shared host-owned state
  root and its exact-run recovery path, not a claim that only one virtual-Paper
  scheduler exists. A post-submit process interruption remains scoped to that
  durable intent and does not become a general execution hold.
- Today's source-free Claude challenge is `uncertain` because it inspected no
  implementation or state. Independent static Review found the registered
  task/Compose surface shares the guarded root and exact virtual host/route
  client, while the generic direct CLI's configurable state root remains a
  manual-entrypoint limit outside the installed-task scope. It changes no
  route, task, authority, or current worker ownership.
- A separate 2026-08-04 D1 bridge drift review returned `uncertain`: the bridge
  must not infer provider finality from a cached snapshot or write an
  Engine-readable observed-only result until a distinct availability/stability
  producer and exact verification predicate exist. A revised bounded stability
  producer received `supported-with-limits`; independent review caught and then
  verified repairs for auth-attempt accounting, shared KIS gates, and its
  cross-process receipt lock. No bridge was implemented.
- The Codex app monitor editor also timed out. Its active result monitor runs
  Monday--Friday at 23:45 KST; installed Windows tasks remain the primary
  evidence. Retry future edits only through the official app API, never by
  editing its TOML directly.
- An official KIS GitHub recheck confirms the existing typed minute route's
  continuation shape: `tr_cont` `M`/`F` leads to `NEXT=1`, `PINC=1`, request
  `tr_cont=N`, and an oldest-bar-derived `KEYB`. The current four-page SPY
  prefix worker already performs that bounded capability probe, so no manual
  rerun or collector rewrite is pending. The former 04:31 KST token-start
  collision did not by itself justify a post-guard retime. The subsequent
  metadata-only QQQ page-range measurement supplied the required
near-boundary evidence, so the same task was re-registered at 04:24 KST
alongside the earlier 00:29/02:28 windows. Claude returned
`supported-with-limits`; the terminal task-owned session capture must prove
the 390 completed-offset result through its observed-ET cumulative
metadata-only projection. DST/pre-market behavior remains unproven.

## Verification And Git

- The observed-ET cumulative session-coverage receipt package passed 22
  focused capture/coverage/backfill/schedule tests, then `2,571 passed,
  23 skipped` through `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`,
  full Ruff, and default, intraday-head, and readonly Compose configurations.
  The rebuilt existing intraday-head image is ready for the next task-owned
  session; this verification is local and does not substitute for its KIS
  coverage outcome.

- The recovery package passed `113` focused execution/schedule/dashboard tests,
  then `2448 passed, 23 skipped` through
  `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`, plus full Ruff and
  all required Compose configurations. These are local-contract checks, not a
  substitute for the task-owned current broker result.
- The current pre-session reattestation additionally passed 137 focused
  canary/intent/quote/receipt/lifecycle/dashboard/schedule tests with no broker
  or credential access. It confirms the deterministic boundary only, not a
  current lifecycle outcome.
- The independent local-PnL package passed 32 focused local-paper/dashboard/
  attribution tests, then `2499 passed, 23 skipped` through the normal parallel
  test helper, full Ruff, and all three required Compose static configurations.
  Those checks use no KIS call or credential read and do not replace the
  scheduled lifecycle-canary evidence.
- The private dashboard package passed `23` focused dashboard/control/snapshot
  tests, including direct non-loopback rejection, then a local Docker rebuild,
  loopback-port inspection, unavailable-state render, and pause/resume UI
  round trip. It performed no KIS call, credential read, broker call, or order.
- The actual Paper account-refresh package passed `55` focused dashboard,
  snapshot, and read-only-client tests. The new end-to-end rejection test proves
  that a failed bridge refresh replaces a prior complete snapshot with
  unavailable dashboard state and never leaks a raw broker marker. The actual
  Compose `kis-readonly` one-shot returned `complete`; its external receipt is
  fact-minimized and its dashboard check emitted only categorical status and
  position/open-order counts.
- Recent commits: `d0223ab` hardens exact Paper-canary recovery, `da12ccd`
  aligns same-date KST Paper task weekdays, and `a6a51a9` records worker
  throughput.
- `a13c195` preserves retained causal head data when a post-close capture
  conflicts, while leaving the fresh candidate non-promoting pending separate
  reconciliation evidence.
- Historic stateboard and handoff entries remain searchable in Git. Immutable
  source-safe receipts, model manifests, and runtime evidence remain external
  under `D:\thericher-v2\model-artifacts`; raw market data remains on `D:`.
- The latest known pre-current canary session evidence is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-canary-session\paper-session-20260801T143501387961Z\evidence.json`.
  Granite structural runtime evidence is under
  `D:\thericher-v2\model-artifacts\research\granite-ttm-r1-isolated-runtime-smoke-v1`.

## Next Handoff

1. The caller-selected 2026-08-08 06:20 KST QQQ/NAS and SPY/AMS chain is
   closed `input_unavailable`: its exact capture binding is verified but
   cumulative coverage is `incomplete`, with no decision-time availability or
   provider-finality fact. Let the installed
   `thericher-kis-paper-intraday-head` task own its next 2026-08-11 00:29 KST
   run. Reattach only a later caller-selected exact terminal, capture, and
   prospective chain; do not manually invoke KIS, Docker, the task, or an
   alternate collector.
2. Preserve the exact 2026-08-07 `canary_completed/intent_recorded` session
   fact and direct `not_submitted/unresolved` lifecycle result as virtual-Paper
   execution evidence only. Do not infer a submit, fill, PnL, or model outcome,
   manually invoke a replacement, or duplicate the existing task. The next
   opportunity is 2026-08-10 23:35 KST.
3. Preserve the exact 2026-08-07 D1 `stable` observation as source-safe
   observational evidence only: its one-GET/zero-retry outcome still has
   provider finality `not_observed`, so never treat it as a consumer or
   provider-finality bridge.
4. When Data produces a fresh qualified causal input, freeze the next distinct
   Engine contract and let Research Steward allocate GPU only if it is eligible.
5. At a company-goal boundary, run required verification, commit/push, replace
   `NEXT_CODEX_GOAL.md` with one material next objective, and refresh only the
   changed current facts in these projections.
