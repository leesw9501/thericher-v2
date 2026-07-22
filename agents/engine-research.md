# Engine Research Agent

## Working Memory

Own hypotheses, campaign contracts, model work, walk-forward evaluation, and
model-side PnL attribution. Current priority is useful KIS-native evidence and
bounded intraday research; GPU time follows a frozen eligible job rather than
becoming a goal by itself.

The local KIS Paper operations console is Execution-owned. Its runtime state and
directional pauses do not qualify, disqualify, or promote any research model;
research may keep preparing eligible breadth/depth/ensemble/replication work in
parallel with Paper operation.

The daily SPY lane now owns a deliberately transparent two-close momentum
baseline. It consumes only one hash-attested `SPY/AMS` D1 source that was first
locally available before the next execution session, emits a deterministic
`enter`, `exit`, or `abstain` receipt, and replays eligible synthetic decisions through
`source: local_paper`. It is an execution-learning reference, not a return,
selection, ensemble, or GPU-promotion claim.

## Intraday Input Contract

The KIS-native minute cache now supports one bounded chronological CPU baseline,
not an eligible model-promotion campaign. Its original 239-bar extended-session
pages remain hash-attested and KIS-reconstructible, and the reattested cache now
has 21 complete regular sessions each for QQQ/NAS and SPY/AMS. The 2026 calendar
window is explicit, but KIS bar open/close semantics remain unqualified and the
first nine-session validation region is too small for model selection.

The first QQQ run fixed the latest 20 complete sessions (2026-06-23 through
2026-07-21) into a 10 development / 1 unused-session purge / 9 validation split.
It ran `flat`, `always_long`, and `previous_bar_direction` through replayable
`local_paper` only. The external manifest is
`D:\\thericher-v2\\model-artifacts\\kis-intraday-cpu-campaign\\qqq-20260623-20260721-r1\\summary.json`.
All costed non-flat references were negative in both phases. This establishes a
baseline to beat, not an edge, model score, GPU qualification, or promotion.

The first feature-breadth continuation is complete at
`D:\thericher-v2\model-artifacts\kis-intraday-feature-breadth\qqq-20260623-20260721-feature-breadth-r1\summary.json`.
It uses the same source and target with 90 completed 1m bars, 18 completed 5m
bars, and 9 completed 10m bars. The regularized linear candidate trained only
on the 10 development sessions; `flat`, `fixed_momentum`, and
`regularized_linear` replayed only the next 5 comparison sessions through
`source: local_paper`. Their after-cost PnL was respectively `0`, `-231.5545`,
and `-131.3063`. The last 4 source sessions were not materialized or used for
selection. This evidence split limits a claim; it never pauses Paper work.

The fixed Docker PyTorch GRU smoke is complete at
`D:\thericher-v2\model-artifacts\kis-intraday-cuda-sequence-smoke\qqq-20260623-20260721-gru-smoke-r1\summary.json`.
It trained 2,990 development-only 90x3 sequences for 8 epochs on the RTX 4090
with PyTorch CUDA 12.8, moving loss from `0.69341975` to `0.69316453`. It wrote
no checkpoint, comparison/confirmation sample, prediction, or promotion claim.

The fixed three-architecture CUDA screen is complete at
`D:\thericher-v2\model-artifacts\kis-intraday-sequence-architecture-screen\qqq-20260623-20260721-sequence-architecture-r1\summary.json`.
Its immutable `precommit.json` recorded all three configurations and the
development-only input hash before comparison materialized. LSTM, causal TCN,
and compact attention each trained 2,990 90x3 development-only sequences for
8 epochs on the RTX 4090, then replayed the same five comparison sessions with
`source: local_paper`. After-cost PnL was `-639.3858`, `-5.9777`, and `0.0000`;
the joint result names no winner, selected architecture, ensemble, or promotion.
The four later sessions remain unmaterialized.

When those source facts are established, freeze this initial contract before any
model comparison:

- decision timestamp: end of the latest completed 1m bar only;
- feature windows: 90 x 1m, 18 x 5m, and 9 x 10m completed bars from the same
  KIS cache, with no provider mixing or gap filling. Keep 1h and 3h inactive
  until their required same-session contiguous coverage and session semantics
  are available;
- target: decide at a completed 1m close, enter at the next 1m open, and exit
  at the following 1m open, long-only. No target may look through a session
  boundary;
- session behavior: abstain outside a Data-declared regular session or whenever
  any required source/resample bucket is missing, incomplete, or stale;
- cost model: 1 bp per-side fee plus 2 bps per-side slippage for the initial
  screen. Use a separately recorded stress pass later; these are research
  assumptions, not KIS fee claims;
- naive comparators: `flat`, `always_long`, and `previous_bar_direction`, all
  through the existing `local_paper` target contract only.

The original 239-bar observed cache cannot provide the 3h context window or a
chronological validation split. One complete 390-minute session can exercise
all resampling and local-paper replay cells, but it is still not sufficient for
GPU, candidate ranking, PnL claims, ensemble selection, or model promotion.

## Ready Queue

1. The current KIS-native comparative baseline is at
   `D:\thericher-v2\model-artifacts\kis-daily-comparative-validation-v1\kis-daily-comparative-20260722T100000Z`.
   It fixes the 694-session panel to 414 development sessions, two purge
   sessions, 138 validation sessions, two embargo sessions, and a 138-session
   final region. Each development/validation consumer receives an independent
   hash-bound Data slice; it cannot read purge, embargo, or holdout bars.
2. The final historical region is `burned_precontract`, not sealed: the prior
   595-session relative-strength smoke observed dates through the current panel
   end. The new comparative output is therefore historical execution evidence
   only, not a return, model-selection, or promotion claim. This does not block
   paper operation or new research; fresh paper/prospective observations become
   the next honest out-of-sample evidence.
3. The CPU run contains fixed relative-strength, cash, and fixed-quantity
   buy-and-hold comparators for each ETF. All fills are replayable
   `source: local_paper`; `run.json`, event hash, data hash, costs, and code
   revision are retained outside Git.
4. The first fixed CPU L2-logistic trade-quality gate is complete and retired.
   Its post-commit artifact is
   `D:\thericher-v2\model-artifacts\daily-three-etf-l2-trade-quality-gate-v1\kis-daily-trade-quality-20260722T170000Z`.
   It used 155 development selector entries (85 positive, 70 negative), and 58
   validation decisions. The candidate accepted 50 trades versus the selector's
   53, improved observed mean return (`0.0001684` versus `-0.0004646`), Brier
   (`0.252925` versus `0.253254` prevalence), and maximum drawdown (`0.06447`
   versus `0.07098`), but both the primary and 2 bp/side stress bootstrap lower
   bounds were `0.0`. Do not retune, promote, or ensemble this candidate.
5. Choose the next breadth campaign only from a data contract with a materially
   broader eligible universe or genuinely new prospective KIS Paper evidence.
   A later depth or ensemble candidate needs a distinct hypothesis and upstream
   out-of-fold evidence; do not use GPU merely to revisit this retired gate.
   The existing Norgate static 523-symbol trial panel is development-training
   preparation only, not a candidate for selector, model, GPU, PnL, or paper
   work under its current manifest scope.
6. The first fixed KIS-only intraday breadth and three-architecture CUDA screen
   are complete and no architecture is selected. Do not retune, choose, or
   ensemble from the five comparison sessions. The next depth candidate needs
   a separately frozen prospective KIS source contract; breadth expands only
   with new KIS-compatible coverage, while ensembles require independently
   generated out-of-fold predictions.
7. The first source-windowed CPU baseline is complete at
   `D:\\thericher-v2\\model-artifacts\\intraday-multitimeframe-baseline\\kis-private-intraday-2026-07-21-qqq-r1\\summary.json`.
   It exercised 390/78/39/6/2 bars at 1m/5m/10m/1h/3h and emitted only
   replayable local-paper fills. Treat it as interface evidence, not a score or
   model result; accumulate prospective sessions before freezing a campaign.
8. The prepared next prospective contract is
   `kis-intraday-prospective-head-observation-r1`: train only the already fixed
   QQQ 10-session historical development prefix, then observe the first five
   new complete 390-minute QQQ head sessions. Keep the KIS-compatible
   `90x1m`/`18x5m`/`9x10m` features, next-open/following-open long-only target,
   1 bp plus 2 bps costs, and fixed `flat`, `always_long`,
   `previous_bar_direction`, and `regularized_linear` controls. External-only
   evidence is a precommit, frozen-model receipt, one receipt per head session,
   and a five-session descriptive summary. It is not selection, retuning,
   ensembling, GPU-depth, or Paper-execution authority.
9. `prepare_kis_intraday_prospective_head_observation.py` now turns the
   independent head index metadata into the same contract's first five-session
   precommit and planning receipt. With fewer than five complete QQQ regular
   sessions it returns a retriable `pending` fact and writes no artifact. It
   reads no raw bars, credentials, network, KIS route, GPU, model, or replay;
   it is preparation for the future observation, not a research-quality gate.
   Its first post-schedule run on 2026-07-23 found zero complete sessions and
   five still required; that does not alter breadth, depth, ensemble, or
   replication queues.

## GPU Policy

One GPU job may run at a time. GPU time follows an eligible frozen dataset and
campaign contract; it is not a utilization quota. CPU preparation, data work,
and execution implementation continue in parallel. Store checkpoints, logs,
and generated artifacts only under `D:\thericher-v2\model-artifacts` or
`/app/model_artifacts`.

Runtime checked 2026-07-22: `thericher-v2-research:latest` exposes one RTX 4090
to PyTorch `2.7.0+cu128` (CUDA 12.8, cuDNN 90701). The host `uv` environment has
no `torch`, so an eligible GPU campaign uses the research container until a host
runtime is intentionally added.

The first actual CUDA job also proved that the read-only `/app/market_data`
mount and writable `/app/model_artifacts` mount work together. Keep one GPU job
at a time and leave the next fixed job ready whenever its contract is sound.

## Durable Knowledge

- Daily raw-price data has an explicit corporate-action limitation.
- The former daily 756-session target improved comparative validation; it never
  blocked KIS Paper connectivity or a deterministic paper canary. The active
  694-session panel is a documented source-limited input, not a repaired one.
- A split label must record historical exposure honestly. `burned_precontract`
  constrains only the interpretation of that historical suffix; it is never a
  KIS Paper, scheduler, or operator-approval gate.
- An unavailable dataset, negative result, or `abstain` receipt constrains only
  that research claim or exact decision. It cannot become a KIS Paper
  permission latch or pause independent data, execution, breadth, or depth
  work.
- A learned node emits timestamped evidence and proposed target state, never a
  broker request.
- Validation evidence can reject a claim without becoming a manual approval
  process for other independent work.
- The first KIS paper canary takes a deterministic explicit buy decision only;
  it is deliberately independent of learned-model or GPU readiness.
- The L2 gate is intentionally CPU-only: this small daily panel cannot justify
  GPU training. A later GPU sequence candidate needs its own frozen prospective
  campaign rather than widening this candidate after seeing results.
- The L2 gate core accepts only the hash-bound prefix through the post-validation
  embargo. Its loader re-attests complete raw source files but does not
  materialize the later burned suffix as `Bar` objects. That boundary is a
  leakage control, not a KIS Paper or research-queue approval gate.
- The KIS intraday contract uses the provider's Korea timestamp as the UTC
  conversion basis and keeps exchange timestamp semantics visibly unqualified.
  This avoids silently inventing a US daylight-saving calendar from an observed
  source field.
- Multi-session validation accepts overnight gaps only at the exact close/open
  pair of consecutive declared `SessionWindow` values. A caller cannot nominate
  a bare timestamp to hide a missing intraday minute, and no target may cross a
  declared boundary.
- Campaign attempt labels create separate immutable work/artifact paths after an
  interrupted run. They are recovery identities, not a scheduler, approval, or
  model-selection mechanism.

## Recovery

Campaign artifacts must name dataset, code, split, cost, model, and result
identity. A missing checkpoint/summary is `restart`, not a partial model result.
Ask Claude only at the defined leakage, sealed-holdout, surprising-result,
ensemble, or promotion decision boundaries.

## Immutable Decision Receipt

The active fixed baseline can now project its existing `TargetExposureProposal`
into a Research-owned immutable receipt through
`thericher_v2.research.decision_receipt`. The receipt is deliberately narrower
than its source: it holds only opaque campaign/model/proposal references, an
exact `sha256:` input-manifest reference, deterministic decision identity,
`enter`, `exit`, or `abstain`, input status, UTC decision validity, and a closed reason
class. It does not carry source bars, features, scores, prices, quantities,
symbols, account facts, source/provider payloads, or the proposal reason.

The Data-side input manifest must bind the provider and capability contract.
Its complete digest, never a shortened display reference, is the authoritative
join key. A changed capability/provider contract must remain an
`unqualified` proposal and therefore becomes an explicit
`abstain`/`input_unavailable` receipt. `future`, missing, stale, incomplete,
or other unready input behaves the same way. Ready `hold` and `reduce`
proposals remain abstentions; ready `enter` and `exit` proposals carry explicit
eligible receipt classes for the Execution-owned target-position adapter.

References are supplied by the durable campaign/input registry as opaque,
high-entropy identities. The receipt module must not derive them from raw data
or a low-cardinality identifier. Its deterministic `decision_id` hashes only
these opaque references plus its safe categorical/timestamp fields, so replay
never reads a clock, credential, cache, or external service. The current
research package initializer still imports legacy modules; that import-layout
fact is outside this narrow receipt module and must be addressed separately if
process-level import isolation becomes an execution requirement.

The first external receipt is
`D:\thericher-v2\model-artifacts\kis-paper-baseline-receipt\qqq-20260623-20260721-receipt-r1\receipt.json`.
It is reproducible from the frozen QQQ/NAS 20-session KIS-only input and its
observed capability contract. Because that contract has no trusted production
baseline qualification, the actual result is `abstain` / `unqualified` /
`input_unavailable`; its local-paper preparation is therefore a scoped
no-intent. This is useful input-status evidence, not a Paper restriction or a
claim about model quality. Focused synthetic replay proves the same immutable
receipt shape can carry eligible `enter` and `exit` transitions through
`source: local_paper`.

## Sanitized Paper Lifecycle Consumer Contract

Future Paper PnL attribution consumes one immutable, sanitized fact per
research-originated intent. It is an Execution-produced public contract, not a
broker client, order command, account snapshot, or replacement for the
authoritative private reconciliation record. Its engine-loop value is to keep
four causes separate when a Paper observation is later linked to a research
campaign:

- `model`: opaque `campaign_id`, `model_revision`, `decision_id`, and
  `decision_class` (`enter`, `exit`, or `abstain`) identify what proposed the
  action without exporting features, scores, weights, or predictions;
- `timing`: UTC `decision_at`, `valid_until`, and categorical lifecycle timing
  (`not_submitted`, `submitted`, `open`, `filled`, `cancelled`, `rejected`, or
  `outcome_unknown`) distinguish a stale/late/unresolved observation from a
  model outcome. Optional latency is a bounded bucket, never a broker timestamp
  or raw response;
- `sizing`: `sizing_status`, requested-versus-accepted notional ratio bucket,
  and closed deterministic reason codes distinguish a risk/sizing reduction
  from a model decision. Raw quantity, price, cash, buying power, and account
  values are excluded;
- `execution`: fixed `route: kis_paper`, `paper_only: true`, reconciliation
  status, fill/realization status, and an opaque external evidence reference
  distinguish broker/execution uncertainty from realized evidence. It must
  never claim `source: local_paper` and must not contain broker order IDs,
  account identifiers, tokens, raw KIS payloads, or raw fill values.

Required common fields are `schema_version`, an opaque deterministic
`intent_ref`, `observed_at`, the four groups above, and a closed
`attribution_eligibility` value: `not_eligible`, `pending_reconciliation`,
`open`, `realized`, or `unavailable`. `realized` means only that Execution has
privately reconciled a closed lifecycle and published a sanitized attribution
receipt; it is not a profitability, promotion, or Paper-permission gate.
Research joins this fact to its own immutable decision receipt by the full
opaque receipt digest when `attribution_ref` is present, otherwise by the
existing canary references. It retains those facts outside Git and reports
incomplete facts as execution coverage rather than imputing PnL.

The initial consumer is read-only and descriptive: no broker import, network,
credential read, retry, cancel, sizing change, or model retune is permitted.
`outcome_unknown` remains attributable as an execution/reconciliation gap and
does not block another independent campaign or Paper intent. Contract changes
need an Execution-owned fixture plus a focused Research consumer test; until
then this section is the queue specification, not an implementation request.

The pre-batch SQLite smoke artifact that stopped at a host timeout is
`restart` evidence only and must not be interpreted. The later completed smoke
under the same external artifact root is the usable local-paper replay.

## Next Handoff

Keep KIS regular-session minute coverage accumulating and maintain the
breadth, depth, ensemble, and replication queues without creating a report
family. For the next Paper observer, consume only an authoritative sanitized
Execution lifecycle fact and leave `pnl_status: not_observed` unchanged until
KIS completion evidence supports more. Do not turn a small current comparison
slice or one Paper observation into selection or Paper-work authority.
