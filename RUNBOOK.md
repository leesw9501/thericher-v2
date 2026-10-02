# Runbook

## Independent QQQ Unit Cycle

`scripts/run_kis_paper_qqq_unit_cycle.py --cycle-id qqq-unit-20261003-v1`
defaults to no-credential/no-write preview. After shared-runtime authority and
compatible Paper-image deployment, explicit `--execute` uses the existing
`kis-paper-daily-spy-session` service, sample Compose env and named Paper-only
credential loader. No new task/service. Keep this one cycle ID on recovery.
One client/token,24 visits/15-second observation cadence/1,200-second worker
bound; parent timeout stops only its exact labeled container. Summary exposes
categorical status/counts and opaque identity, never private prices/order IDs.
Shared private budget V2 retains the original10-percent basis and both owners;
legacy SPY remains charged/unknown. Deploy compatible budget writers first.
`unit_cycle_complete` needs exact full BUY and SELL plus owned-flat account
reconciliation. No-intent, rejection, cancellation, task exit or absent history
is not a filled round trip. Fees/settled cash/net PnL remain unobserved.

An explicit distinct `--entry-request-id` may append one fresh BUY only after
every earlier BUY in that same cycle is positively rejected/closed. Reuse the
same request tag on restart; never select a new tag automatically. Exact QQQ/
NASD orderable funds at the ORIGINAL limit are required immediately before any
BUY, including a restart without a tag. Original unbound intent recovery uses
its retained decision receipt, exact price/TTL/fingerprint, not a refreshed
quote. Unknown outcomes remain reconciliation-only. No new tagged runtime has
yet occurred; deploy the reviewed sources before assigning a next-session visit.

`scripts/probe_kis_paper_minute_capability.py --execute --target QQQ/NAS
--max-pages 2 --explicit-older-key-once` already completed once at18:25:32Z:
two120-row pages/120 new older keys/zero overlap, no recognized M/F. This opt-in
probe discards rows; exact evidence belongs to Data. Do not repeatedly probe the
same question. The integrated retention path is:
`uv run --extra dev python scripts/backfill_kis_paper_private_intraday.py
--execute --mode session-capture --pages-per-target 4
--explicit-qqq-head-continuation --skip-legacy-preparation`.
It uses the existing named Paper-market loader, gate and cache lock, with at most
four QQQ pages and unchanged SPY/default behavior. Run only without an active
same-cache owner. A retained-cache conflict may quarantine its predecessor and
reject this exact capture; preserve original bytes and obtain a fresh bounded
capture when the token-start guard permits. Do not infer full-session coverage,
provider finality or scheduler origin from this direct invocation.

## Latest Bounded Research

`scripts/run_tiingo_monthly_frozen_policy_readback.py` already completed one
metadata freeze and one CPU inference attempt on August/September2026. Same
pinned Torch image/network none/2 CPU/2GiB/120s, source/data/parent artifacts RO,
only the exact new study directory writable; no env-file or GPU.126 cells and36
matched identities pass exact RO readback. Root/pins/limitations belong to
Research. Do not rerun, overwrite the contract or recalibrate parent TRAIN
constants. Default preview is metadata-only/no-write; a new question needs a
distinct contract rather than reopening this result.

`scripts/acquire_tiingo_adjusted_context_20261003.py` defaults to plan-only;
explicit `--acquire` already completed three approved standard-EOD requests
for SPY/QQQ/IWM, July1 2025-September30 2026. New timestamped sibling retains
945 rows/315 per ETF and raw adjusted fields;14 focused tests pass. Exact
path/hashes belong to Data. Do not rerun for the same scope or splice old
adjusted marks. Canonical rows remain unadjusted; separate new-vintage reader
`load_verified_adjusted_etf_vintage` requires exact expected dataset ID/hash,
manifest hash and three raw hashes. Actual315-row per-ETF readback and all six
252-return August/September windows pass, without reading a future October mark.
155 combined tests pass/3 native-symlink skips. It changes neither the frozen
August9 reader nor an existing campaign and provides no PIT/Paper qualification.

October3 isolated preparation: monthly input/utility modules have109 passing
synthetic tests, including CPU Torch optimizer, numeric reconstruction,
Decimal ledger and gradient/context invariance. The new portfolio-budget math
has234 synthetic and555 related passes; independent rereview confirms all
three reproduced defects were repaired. None reads private source/account
state or deploys a new Paper cap. Tests use isolated retained C: scratch.
`scripts/run_tiingo_monthly_net_utility_development.py` completed one actual
CPU-first/CUDA attempt: two128-epoch fits,126 cells,81.300s,49 focused tests
and immutable readback pass. Root/pins/results belong to Research/Steward.
Do not rerun or edit the frozen harness. Same pinned Torch2.7.0+cu128 image,
2 CPU/6GiB/900s/network none; read-only src/scripts/data/artifact root, only the
exact study directory, existing `_control/ledger` and canonical GPU-lock directory
writable. No env-file/credentials/broker or image change. Final NPZ arrays use
strict numeric schemas/allow_pickle=False; CPU reconstruction is checked.
Dynamic runtime pins require metadata freeze AND offline readback inside the
same Docker image, not host Torch2.13 CPU. The full calendar contract is188,626
pinned-image bytes; no generic reader limit changed. Worker/container exited,
GPU lock released. Both learned policies trail their own TRAIN-risk controls
in most/all folds; no selected model, retune, holdout or Paper promotion.

October3: `scripts/run_chronos2_return_development.py` completed its immutable
one-pass comparison under the same pinned Torch image below. Use network none,
read-only source/model/data, external artifacts writable,2 CPU/6GiB,900s and
HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE/HF_HUB_DISABLE_TELEMETRY/DO_NOT_TRACK=1.
Direct local constructors/safetensors, no Hub loader or dependency replacement.
Exactly one aligned origin per cross-series trio; isolated and duplicate-self
controls.1,305 scored forecasts/126 cells/72 exact parent controls,30.163s from
attempt reservation; code/asset/result readback passes. No training/selection.
Root/pins/results in Engine Research; do not rerun its closed attempt.

`scripts/run_tiingo_volatility_allocation_development.py` also completed once:
TRAIN2001-2012,22 prior-session inverse variance, fixed daily flatten with
TRAIN-risk-matched constant/long/cash controls.72 cells,3.949s reserved duration,
1 CPU/1GiB/600s, network none; existing base image/source/data read-only mounts.
All six20bps groups lose to risk-matched/cash. This daily adaptation does not
reject a separate monthly holding mechanism. Exact pins belong to Research.

`scripts/run_tiingo_monthly_holding_development.py` completed its distinct
72-cell adjusted-mark NAV study once. Metadata-only `--freeze` precedes rows;
`--run --contract-sha256 <exact pin>` reserves one immutable attempt. Closed
root/pins/results are in Engine Research; never rerun or change frozen code.
Use existing base image
`sha256:09144e4bfc5e76f0d7f905f57f7996d39cd576d014f0717ed18614a047cc75c1`,
1 CPU/2GiB/600s, network none, read-only src/scripts/data and artifact root.
Only this study directory and existing `_control/ledger` are writable nested
mounts. No credential env-file, broker path, GPU, image/dependency change or
extra dividend credit. Target is prior-close monthly allocation, not daily
flatten; fees include actual post-fee rebalance turnover and final liquidation.
100 new focused tests/2 native-symlink skips and immutable readback pass.
Weekly serial baseline completed6,341/19 skips,35 warnings,1,892.93s on
`C:\trpy\weekly-20261003-a6b6a9b`; it predates collection of these new tests.
Focused/weekly scratch is retained without unsafe recursive cleanup.

`scripts/run_tiingo_monthly_momentum_development.py` completed its distinct
72-cell fixed12-calendar-month study once, reusing the unchanged adjusted
reader and overnight ledger. Same metadata-only freeze/single-attempt CLI and
CPU/container/mount limits above; root/pins/results in Engine Research.
TRAIN2002-2012 after warmup; prior completed month-end versus exactly12-month-
earlier close, no nearest-date replacement. Unique required support includes
the13 historical month-end closes and every scored session. Zero-interest
cash is our own adaptation, not the paper's Treasury-bill excess-return rule.
150 current reader/holding/momentum focused tests pass,2 native-symlink skips;
independent review and immutable readback pass. No new prediction/model/weight,
GPU, broker, source dataset, runtime or schedule.

Shared-runtime authority passed6,341/19 skips, eight workers,307.80s and clean
helper exit;353 changed-path serial tests, Ruff/both sample-env Compose configs,
eight rebuilt consumers/16 changed-source hashes pass. First equal-count run
failed cleanup due a new synthetic hard-link fixture; fix only that fixture's
own teardown, never relax the helper or delete retained failed roots.
`C:\trpy\runs\r-07a471bd` is inactive/retained. GPU/CPU studies ran independently
of this verification. Claude actual weekly-limit response is review_unavailable.

Original-POST-date ID-less history now projects absent/unique/ambiguous/incomplete
only; no ID adoption, terminal inference or broker retry. One owned read-only
visit at15:24Z failed authentication before history; exact evidence in Execution.
Do not retry the control with a missing same-client token or infer credentials
are wrong from that category. Same unknown successor and existing schedules
remain intact. The later15:37Z visit succeeded with available known BUY/cancel
controls and stable private bytes, but zero unknown-tail candidates. No terminal
inference follows; do not repeatedly poll absence. Exact receipt/hash is in
Execution. The company objective stays open; independent ready work continues.

`scripts/run_timesfm_return_development.py` reuses the immutable bounded supervisor:
`--freeze` binds source metadata/code before rows are loaded;
`--run --contract-sha256 <exact hash>` owns one finite attempt, never an
automatic retune/retry. Root:
`D:\thericher-v2\model-artifacts\research\timesfm-2p5-tiingo-intraday-return-development-v1`.
Use the existing pinned Torch image
`sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039`,
GPU enabled,2 CPU/6GiB host RAM,600-second supervisor, network disabled,
source/data read-only, only the external artifact mount writable. No env-file,
credentials, KIS, new base dependency/image or scheduler. The supervisor parent owns
the canonical GPU lock until its child exits/is reaped, including timeout.

The existing `timesfm-2.0.2-py3-none-any.whl` SHA256 is
`c7bde94beb1651e1251cdf1e9d09cf6f015e0218d038a4a836a170dc70b08071`.
Verify before installing `--no-index --no-deps` into disposable `/tmp/timesfm`,
never the host or base/Paper image. Keep HF Hub offline/telemetry disabled.
The read-only container uses256MiB `/tmp` tmpfs and PYTHONPATH includes this
temporary package plus `/app/src`; weights remain under the external artifact
mount. The adapter loads local safetensors directly, not a Hub download helper.

Each input has128 prior raw daily intraday returns; the TimesFM median predicts
the next session open/close return. Jan-Mar and Apr-Jul2026 have61/84 targets
per SPY/QQQ/IWM. CPU controls precede CUDA; no training/weight update. Fixed
forecast >20bps acts long/flat under5/10/20bps all-in round-trip accounting.
Histories may predate the checkpoint; all target dates postdate the exact
official October2025 weights. Raw revised data and next-open availability
assumptions remain; this is not an independent holdout or a price-level test.
Per-context normalization/attention is independent even in a mixed-date batch;
do not transfer this fact to Chronos-2's related-series group attention.
Only aggregate development facts and hashes are retained, not predictions.

The local GPU allocator uses min(90 percent of total, free minus1GiB), rather
than the old per-study4GiB cap. No permission wait or artificial VRAM padding.
Actual run completed435 forecasts/90 cells in31.213s including offline package
installation/startup; peak allocation1,033,671,168 bytes. Offline contract,
source/asset and exact summary hashes validate. Small positive SPY proxy means
do not establish profitability; QQQ/IWM are not consistent.325 focused/related
tests pass in20.51s; Ruff/both sample-env Compose configs pass. No full-suite
run for this isolated package. This does not select a model or create a Paper input. The container
exited, lock released, registry non_promoting_completed; never rerun its closed
immutable path. Engine Research holds exact pins, results and next hypothesis.
Previous H180/feature-boosting/transition studies remain immutable references, not
a permission condition for independent Paper recovery.

## Modes

- `off`: no broker work; data/research and local simulation are available.
- `local_simulation`: broker-free replay; fills remain `source: local_paper`.
- `kis_paper`: KIS virtual account and virtual orders. This is standing
  authorized for the private project.
- `kis_live`: real-money behavior. It is unavailable: do not read
  `KIS_LIVE_*` or construct a live route.

Existing KIS clients must pin the virtual-paper host. A caller selecting a live
mode must fail before paper credentials are used.

### Ten-Percent Strategy Trial

Current September25: budget CLI exit0 means preview/not_due/no_intent or
order_complete, never an inferred fill. Recovery/unexpected status returns20;
pending/deadline exhaustion returns21. The host launcher reports worker_failed
for nonzero exits without relaunching. Verified Windows RestartCount=0;
existing23:50 cadence and visit bounds are unchanged. Legacy non-budget exit
behavior remains unchanged. Outcome failure_diagnostic is a closed stage/type/
optional local-code projection, not exception or raw response text.
The one15:40Z retry reached no_intent/existing_inventory_or_order_conflict.
No diagnostic inventory adoption/order followed; the earlier14:50Z generic
failure cannot be retrospectively explained. Exact receipts are in Execution.
The unknown linked successor remains owned; do not reset or repost it.

September24 offline follow-up: the September23 23:50 owner again returned
no_intent/daily_receipt_not_eligible with no budget binding/intents. This reason
currently combines input status, decision class and receipt validity; it cannot
prove a clock regression, stale input or neutral signal by itself. Preserve
these checks and isolate the exact categorical cause in the next repair.
The Windows owner remains due September24 23:50 KST. Only the obsolete dated
app follow-up thericher-paper was deleted; no Windows task/order was invoked.

2026-09-23 correction: the budget receipt loader now samples the real decision
clock after input loading/availability attestation. The old equality caused
the23:50 first-use receipt to abstain despite September21 coverage. Do not add
an epsilon or weaken future/stale predicates; a fixed equal clock still abstains.
The normal CLI supplies neither `now` nor a fixed clock. The new daily image
contains this correction; deployment does not itself prove a strategy trade.

The existing daily SPY session has an explicit `--budget-trial` mode. It uses
the existing daily baseline's enter/exit direction, not its old fixed-share
size or an assertion of predictive skill. It freezes 10 percent of the lesser
of two fresh USD orderable amounts as a provisional initial allocation, not
settled cash/equity or a loss bound. It holds no leverage/short position and
does not increase that allocation after profitable sales.

The private `.spy_strategy_budget.json` in the existing canary volume contains
only the funding/account binding and ordered intent references. Fills remain
in the existing private canary states. Never print either. Actual entry cost
plus residual buy reservations share one cap under the session/canary locks.
A missing binding alongside owned intents requires recovery, not a fresh
allocation. Initial inherited SPY is not adopted or sold. Shared SPY ownership
excludes a competing fresh legacy/diagnostic order; other symbols and exact
recovery/cancellation remain independent.

The scoped host entry is:

~~~powershell
uv run --no-sync python scripts/run_kis_paper_budget_strategy.py --visits 1
# Only the owned strategy invocation uses --execute; the command above is preview.
~~~

It uses `.env.example` for Compose and injects only the four scoped Paper
values when execution is requested. It never inherits `KIS_LIVE_*` values.
The existing daily task owns `--execute --visits 24`; only a pending exact
order repeats, at 15-second worker intervals with one client/token. The
worker starts no new visit after 1,200 seconds; container/host deadlines are
1,260/1,350 seconds and the task limit is 25 minutes. No foreground wait,
new recurring task or automatic retry of an unknown POST is introduced.

Source-safe results are under
`D:\thericher-v2\model-artifacts\execution\kis-paper-spy-budget`:
`dispatch.json` is process status only; per-session `outcome.json` is categorical
strategy status, and `decisions` holds safe hash-bound signal receipts. Neither
a process exit nor `order_complete` is settled cash or net PnL. Exact existing
intent/fill/account facts remain the authority. Legacy CLI defaults and the
separate 22:35 one-share fill cycle are unchanged.

Deployed 2026-09-22: the existing `thericher-kis-paper-daily-spy-session`
action now invokes this scoped launcher, with its weekday 23:50 KST trigger
and principal preserved. The task limit is 25 minutes; registration did not
advance last-run. Seven images have 42 matching source hashes. The daily
image is `sha256:df426086317da543968b1a3c39d0be1eeef7dffc20dcbd96cda00416ed4b9fe4`.
The real mounted private path and credential-free preview pass, but no
budget order/fill has yet been observed. The path validator accepts
`/app/private/canary` only with a real `/app/private` mount, not an arbitrary
directory beneath the repository. Required verification: 439 focused passed /
1 skipped; 3,903 full passed / 19 skipped, eight workers, 296.58s and clean
helper exit; Ruff and both sample-env Compose configurations passed.

## Long Codex Task

### Existing SPY Cycle Recovery

Latest September24 regular-session continuation attempted one linked successor.
It is now outcome_unknown/no broker identity, with a legacy provider_rejected
category that does not prove explicit rejection. The13:35Z read-only query
finds one owned SPY and no SPY open/history row. Preserve that exact tail and
all original identities; absence alone cannot authorize replay or a substitute
exit. The diagnostic-only classifier change does not rewrite this legacy
attempt or widen ID-less recovery. Execution retains the immutable evidence.
The second13:58Z read-only probe again has one SPY/no opens/no current-day
history; both inquiries use the attempted POST's exact New York date. Do not
reinterpret a missing row or old ambiguous category as a terminal result.
The correction is deployed to all eight consumers (40 matching source hashes).
399 focused/1 skip plus80 research tests and full5,348/19 skipped in323.48s
pass; eight workers/clean helper exit, Ruff/both Compose configs. No schedule
changed; existing budget owner remains due September24 23:50 KST. Its exit
signal does not adopt diagnostic inventory or imply any submitted/fill result.

Current September24 evening: exact read-only reconciliation restored the
original SELL to cancelled, with cancellation_confirmed, fresh zero-fill and
available account evidence. One owned SPY remains; original IDs and accepted
cancel are unchanged. Execution holds the12:59:24Z receipt/hash. Do not send
the accepted cancellation again or reset the cycle. Linked-successor code is
verified/deployed; the later unresolved successor attempt is described above.
The daily head has separately refreshed through September23 and yields exit;
the23:50 budget strategy cannot adopt the diagnostic inventory or force entry.
The earlier statuses below retain their timestamps, not the current phase.

Successor recovery is append-only in the existing private cycle binding:
persist one deterministic link and immutable intent plan before its ledger,
mark that exact prefix recorded before POST, and never repost a started or
unknown attempt. Each predecessor must have fresh typed zero-fill cancellation
proof; account ownership/open orders, pause controls and session are rechecked.
Only the committed exact tail shares the SPY owner. Original IDs/prices remain
unchanged. Partial or ambiguous ancestors cannot create a successor. An expired
never-sent successor remains scoped unresolved rather than being repriced.
The generic canary also rechecks time after a slow permission callback, before
recording submission_started. The sequence releases ownership only after exact
exit fills and fresh flat-account evidence. Gross flows are not settled cash
or net PnL. Tests:628 serial,5,226 parallel/19 skips,335.47s; all32 source hashes
match across eight rebuilt images. No scheduler expansion or new runtime.

Latest 2026-09-23 late-evening status supersedes the old no-sell facts below.
The existing buy is full; its same-cycle sell was acknowledged, unfilled, and
received one exact-ID cancel. Later complete observations bind original
remaining zero to a distinct same-date cancel lineage with matching full
quantity and no execution/rejection. One owned SPY remains. No replacement
order or schedule change has occurred. Exact receipts are in Execution.

The narrow repair is verified and deployed to seven consumers (28 matching
changed-source hashes):704 focused tests,5,097 full passed/19 skips, eight
workers,326.74s, clean helper exit; Ruff and both sample-env Compose configs.
Actual reattachment at14:40Z failed authentication; at14:44Z the SELL recovery
observation remained unavailable even though subsequent account/history reads
succeeded. Its persisted state is still outcome_unknown. The probe's overall
complete status means its steps ended, NOT that every leg recovered. Inspect
the exact leg's cancellation_confirmed/account/fill/phase fields; never combine
later independent history/account calls into its missing transition evidence.
The old14:10Z worker-outcome also predates this read-only probe; it is not a
current cancellation-state receipt. Do not repeat the already accepted cancel.

The additive `cancellation_confirmed` observation is true only for this narrow
zero-fill original-plus-cancel lineage, never for absence, a status label,
cancel ACK, remaining zero alone, partial fills, or incomplete/duplicate rows.
Existing pending recovery uses the current persisted fill and fresh complete
account (no same-instrument open order) before marking it cancelled. It reads
the completion clock after network work. Future fill observations do not
qualify; unknown-state transitions preserve monotonic stored timestamps.
The flag is transient; there is no private-state schema migration or new order
capability. The next exit must have a linked new intent after confirmed cancel,
not an edited/reused old intent or reset funding/cycle binding.
Official field references: [history fields](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_ccnl/chk_inquire_ccnl.py),
[cancel code 02 versus modify 01](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/order_rvsecncl/order_rvsecncl.py).

Current as of 2026-09-23 19:52 KST: the original buy's full fill is persisted
and its position agrees, with no SPY open order. No sell leg exists. Exact safe
receipt: `readonly-recovery-20260923T105253851682Z.json` in the cycle root below.
The existing fixed-cycle task runs once at 2026-09-23 22:35 KST, expires 23:10,
and retains its action, principal, cycle ID and 25-minute limit. It was not
manually started. The separate daily strategy remains at 23:50; shared SPY
ownership and the frozen aggregate budget are unchanged. Reobserve exact
fills/position before the exit; do not recreate or enlarge the original buy.

The cross-venue balance parser repair is deployed in all seven state consumers.
All three query groups must finish. Rows retain their reported US venue;
matching inventory duplicates across groups coalesce, while same-group/page
duplicates and quantity/cost-basis/currency conflicts fail. Market marks are
sequential indicative observations, not execution prices or atomic account NAV.
No change to quote freshness, sizing, persisted order identity or live isolation.

Resume only `spy-fill-20260922-v1` while its owned cycle is open. Its actual
artifact directory is `execution/kis-paper-spy-fill-cycle/e6ad99be327e7ece5fb77ca234f75d9c2fbf266277cabbf0221a7d44b5204866`
under the external root. The scoped launcher is
`scripts/run_kis_paper_spy_fill_cycle.py --cycle-id spy-fill-20260922-v1 --visits 20 --execute`.
Check the exact worker/ownership first; do not concurrently invoke it or run a
competing SPY entry. Old task exits and previews are not actual fill evidence.

The15:18Z read-only history probe found a numeric-padding mismatch between the
raw acknowledgement ID and one otherwise fully bound history row. The repair
only widens history candidate matching for positive ASCII decimal leading zeros.
Stored identifiers and cancellation calls stay unchanged; no state migration.
Keep duplicate rows ambiguous and all date/instrument/side/quantity/amount
checks. This empirical Paper compatibility fact is not an official universal
normalization guarantee. Safe probe metadata is retained beside the worker
receipt as `history-capability-20260923.json`; no raw ID or market row is there.
The generic pre-intent error now includes paired closed-enum stage/category
fields. No exception text, broker payload or secret can be put in these fields.

Earlier same-cycle result, 2026-09-22T15:32:38.784561Z, was
recovery_required/evidence_unavailable after one visit on the corrected image.
A separate single read-only attempt at 2026-09-23 00:36:48 KST returned
auth_rejected before account parsing. Neither supplies a fill or proves the
cause of earlier generic errors. No cycle worker remains; preserve the existing
acknowledged entry, binding and original order date. Recover that scope with
the existing serialized Paper loader/client; do not reset ownership, issue a
replacement buy, or start repeated authentication attempts without inspecting
the owned retry facts. No new standing cooldown or approval gate is introduced.
Independent offline research remains ready while provider recovery is pending.

### Fixed Position-Policy Comparison

`scripts/run_firstrate_position_policy.py` freezes metadata with `--freeze`
and supervises one `--run --contract-sha256` CPU replay. The completed
`persistent-position-h30-c36-v1` root and hashes are in Engine Research.
Keep the closed result; do not rerun or retune it. The worker reused eight
existing LSTMs, fixed rules and the pinned research image, with network off,
source/scripts/market data mounted read-only and external D: artifacts writable.
No wheel/dependency change or GPU allocation was needed. CPU limit was 600s,
outer container 660s; actual supervised time 317.730s. All 72 parent controls,
72 policy pairs and common-support checks passed. The container exited.
Generated summaries remain external; no new model weights exist for this study.

### Fixed Forecast Diagnostic

`scripts/run_firstrate_forecast_diagnostic.py` owns the completed
`fixed-forecast-diagnostic-h30-c36-v1` package, not a recurring job.
It reuses all28 frozen H30/context36 weights on CPU, checks84 parent replay
cells, and retains only aggregate dispersion, error, fixed-bin and descriptive
correlation/calibration facts. No forecast rows, new weights or fitted policy.
Contract/result hashes and interpretation are in Engine Research. Artifacts
are under the existing external FirstRate H30 family root. The actual run
completed in84.497s under a600s supervisor/660s container ceiling; do not rerun
or overwrite its started/summary records. It used the pinned research image,
network disabled, 2CPU/6GB, no GPU/credentials, read-only source/data and the
same hash-checked offline LightGBM wheel described below. `--freeze` is
metadata-only; `--run` requires its exact `--contract-sha256`.

Latest Paper runtime follow-up (September23 22:35 KST): task exit0 only records
worker completion. The exact worker outcome is recovery_required /
evidence_unavailable. Offline stable private-state parsing validates a fresh
full buy-fill observation at13:35:02.799196Z and no sell state. The immutable
observation is linked in Execution. No new API/order/task invocation was made
by that reader. Preserve same-cycle identity; localize the post-entry failure
before claiming exit/flat/accounting. The finite trigger is consumed, while
the separate23:50 strategy schedule remains unchanged.

### Fixed Opening-Range Comparison

`scripts/run_firstrate_opening_range.py` reuses the existing position-study
CLI/supervisor for one fixed source-local DEVELOPMENT rule. Its completed
contract and summary are in `agents/engine-research.md`; external directory:
`D:\thericher-v2\model-artifacts\research\firstrate-m5-opening-range-development-20260923-v1`.
It completed12 cells/159 one-share trades in259.329s of600, with no training,
GPU, new weights or Paper change. The descriptive criterion was not met;
neither a portfolio return nor statistical mechanism rejection follows.
Do not rerun or overwrite its started/summary records. Use `--freeze` only for
metadata and `--run --contract-sha256 <exact hash>` for a fresh owned contract.
The actual container used the pinned existing research image, network none,
2CPU/6GB, read-only `/app/src`, `/app/scripts`, `/app/market_data` mounts and
writable external `/app/model_artifacts`. Mount source subdirectories instead
of the whole read-only repo at `/app`, which prevents nested mount creation.

### Fixed Model-Family Comparison

`scripts/run_firstrate_family_comparison.py` owns the finite
`model-family-h30-c36-v1` study under the existing FirstRate H30 family.
It fixes context36/H30, costs1/3/5bps, four LightGBM fits and sixteen
TCN/Transformer fits; parent LSTMs are reloaded rather than retrained.
The contract and CPU summary pins are in Engine Research. Source and original
data are read-only; generated models/configs stay beneath
`D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\model-family-h30-c36-v1`.
Successful phases retain `cpu-models` or `cuda-models`; existing summaries and
started markers are not overwritten. This is not a recurring training worker.

Use the pinned research image recorded in the contract, network disabled,
2CPU/6GB RAM, source/scripts read-only, D: market data mounted read-only at
`/app/market_data`, and external artifacts at `/app/model_artifacts`.
The official LightGBM4.6.0 wheel is under external `public-runtime/lightgbm-4.6.0`;
verify its contract hash, then install with `--no-index --no-deps --target`
into `/tmp/family-runtime`. Mount `/tmp` as `rw,exec,size=512m`: the native
library cannot load from a noexec tmpfs. Torch loads before LightGBM to provide
OpenMP. Put the temporary runtime and `/app/src` on `PYTHONPATH` for spawned
children. No credentials, broker client, network or Paper service is supplied.
CPU uses `--phase cpu --contract-sha256`; CUDA additionally uses
`--cpu-summary-sha256` and the canonical GPU lock. Worker limits are600/900s;
outer container limits660/960s. CPU completion requires84 exact parent controls;
model restoration must reproduce predictions and every threshold decision.
All retained forecasts remain DEVELOPMENT-only aggregate cost cells, not NAV.

### TimesFM 2.5 Offline Research Runtime

The approved reusable version is `google/timesfm-2.5-200m-pytorch`, revision
`1d952420fba87f3c6dee4f240de0f1a0fbc790e3` (Apache-2.0), not TimesFM 3.0.
Personal use does not override the latter's separate revenue/production/output
restrictions. The rights decision and official sources are in DECISIONS.

Assets are under
`D:\thericher-v2\model-artifacts\foundation-models\timesfm-2.5-200m\1d952420fba87f3c6dee4f240de0f1a0fbc790e3`.
`scripts/run_timesfm_2p5_smoke.py --artifact-root D:\thericher-v2\model-artifacts --prepare`
acquires/verifies only pinned config, README, safe weights and the
`timesfm==2.0.2` wheel. Its acquisition is separate from inference. Existing
mismatched or partial bytes are not silently replaced. Preserve Apache notices.

The actual smoke uses the existing research image
`sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039`.
Run each phase in a disposable `--network none --read-only` container with
2 CPU cores, 6GB RAM, 512MB writable `/tmp`, source/scripts/model mounts
read-only and the external artifact root at `/app/model_artifacts`. Verify
the wheel hash, install it only into `/tmp/timesfm-runtime` using
`pip install --no-index --no-deps --target`, then place that directory on the
Python import path. No dependencies, base images or Paper images are upgraded.
Inside that container the entry is
`python scripts/run_timesfm_2p5_smoke.py --artifact-root /app/model_artifacts --phase cpu`
and then `--phase cuda` in the GPU-enabled container. Each invocation has
`timeout -s TERM -k 15 240`; only CUDA takes the existing exclusive GPU lock.
HF offline/no-implicit-token/no-telemetry flags are enabled, no secrets or
market-data volume are supplied, and raw predictions are not retained.

The closed synthetic run is not meant to be repeated as a scheduler. Results
are `contract.json`, `cpu.json`, and `cuda.json` beneath external
`research/timesfm-2p5-offline-runtime-20260922-v3`. This proves shape/device/
runtime compatibility only. A market comparison requires a separate applicable
source/temporal-scope contract; it does not block locally trained models or
the existing Paper baseline.

### Current Follow-Up

For this 2026-09-22 continuation, thread heartbeat `thericher-paper` owns one
follow-up at 2026-09-23 00:20 KST, after both installed Paper task limits. It
does not start another order worker or modify schedules. Inspect the exact
fill-cycle identity and every budget visit in the task-time window, not just
the last categorical status: a later no-intent can follow earlier recovery.
Mutable dispatch files lack timestamps and are process status only. Missing,
preview, exit zero and cancellation are not fills. Read private state through
pure parsers with categorical in-process projection; do not print identities,
amounts or parsed state objects. `StateStore.read()` acquires locks; avoid it
for a strictly read-only projection. Fees/settlement/net PnL stay unknown unless
independently evidenced. This follow-up requires the local host/app available.

```powershell
.\scripts\start_next_codex_task.ps1
```

Read the files it prints and then execute the single current objective in
`NEXT_CODEX_GOAL.md`. Codex assigns ready Data, Engine Research, Execution,
and temporary Validation work, integrates it, verifies, commits, pushes, and
refreshes the next objective. Do not stop for routine paper-work approval.

For integrated test feedback, pass `--maxfail=1 --durations=15` to the existing
parallel helper. A failed run is already non-authoritative; stop at its first
reported failure and inspect it instead of paying for the remaining long
replays. The measured 2026-09-21 failed full run took 40 minutes; the next
fail-fast run surfaced a test-isolation fault in 34.50 seconds. Successful
authority still requires the complete expected suite, workers and cleanup.

The 2026-09-21 partial reset superseded the incomplete D1-pair company goal.
The next implementation is the restart-safe SPY Paper lifecycle; D1 stays a
Data-owned measurement. Older one-run restrictions below describe their exact
historical attempts, not a global ban on new owned recovery or developmental
research. Use `AGENTS.md` for the development-versus-promotion distinction.
The bootstrap changed source/docs only. Subsequent work rebuilt the D1 image
and existing research runtime; current deployment facts are in the stateboards.

### Current Schedule Set (2026-09-22)

This section supersedes historical registration/next-due claims below. All
names in this table have the prefix `thericher-kis-paper-`; times are KST.

| Task | Current disposition |
| --- | --- |
| `intraday-head` | Retained: 00:29, 02:28, 04:24, 06:20 Tue-Sat. |
| `daily-spy-head`, `daily-spy-session` | Retained: 22:15 and 23:50 Mon-Fri; input collection and the scoped 10-percent aggregate-budget baseline trial. Daily session uses the host budget launcher, 24 visits, 25-minute task limit. |
| `snapshot-observer` | Retained: every four minutes for ten hours from 21:20 Mon-Fri; no cadence change without freshness/load evidence. |
| `daily-pair-forward` | Retained: 06:55 Tue-Sat; host runner now uses existing v2 profile/preflight/collector and v2 guard-receipt lineage. v1 remains untouched. |
| `daily-nas-forward` | Retained: 06:40 Tue-Sat; revision-retaining collection now has41 sessions per target, six saved whole-page revisions,234 added rows. Old overlap values remain. Code20 describes unresolved mixed-view values, not zero collection. |
| `d1-prospective-observation-pairing` | Final later opportunity 2026-09-22 23:20. Both triggers expire 2026-09-23 00:00. Fresh first observation is recorded, not a complete pair. |
| `daily-backfill`, `daily-broad-backfill` | Disabled: exact historical cursors terminal, respectively 3/3 and 2,119/2,119 targets. This is not a claim of unlimited historical coverage. |
| `daily-spy-stability-observer`, `spy-prefix-negative-control`, `spy-prefix-feasibility` | Disabled finite diagnostic studies; commands and immutable results retained. |
| `quote-session` | Recurring immediate-cancel smoke remains retired. Its existing registration is reused for one explicit fill cycle at 2026-09-22 22:35, expiring 23:10; no repetition/restart. Do not confuse this with retained `daily-spy-session`. |

Two completed Cboe one-shot registrations are also disabled. The two legacy
TheRicher tasks remain disabled. Nothing was unregistered or stopped mid-run.
Three old Codex follow-up IDs were confirmed `not_found` by the app; no new
automation replaces them.

The installer without `-ScheduleName` selects only the six operational tasks.
A named historical/diagnostic install remains possible, but updating a disabled
task preserves disabled state and an existing trigger expiry is retained.
Installing is not an implicit instruction to resume a retired experiment.
The pair task already calls the host runner, so the v2 edit needs no task start
or image rebuild. Its image exists; successful next collection is not claimed.

Rollback metadata is in
`D:\thericher-v2\model-artifacts\ops\schedule-cleanup-20260922\before.json`;
`after.json` records the independently read host settings. A review probe later
re-registered eight tasks; original start anchors were restored and last-run
timestamps were unchanged. `rechecked-after-review.json` and
`action-contract-recheck.json` retain the safe correction/route checks. No
full pre-probe XML was retained, so this is not a byte-identical task rollback
claim. Restore only named
enabled states/trigger expiry fields after checking ownership, using
`Enable-ScheduledTask`/`Disable-ScheduledTask` and `Set-ScheduledTask -Trigger`.
The prior runner is in Git revision `8dce708`; reverting to it also reverts the
pair to quarantined v1 and is not a data repair. Do not erase private state,
quarantine, raw data or immutable receipts to undo scheduling changes.

### Explicit SPY Fill Cycle

Installed finite opportunity: `thericher-kis-paper-quote-session`,
2026-09-22 22:35 KST, cycle ID `spy-fill-20260922-v1`. Its single trigger
expires at 23:10, execution limit is 25 minutes, restart count is zero, and
multiple instances are ignored. Principal, other task definitions and task
count are unchanged; last-run time did not advance during installation.
Do not reinstall this task with its legacy diagnostic definition before the
owned opportunity. Afterward disable the finite registration or keep its
expired trigger; do not resume the old recurring canary automatically.

The existing session CLI now has an explicit `--fill-cycle-id` mode. It buys
one SPY share using a fresh ask limit, then sells only its exact confirmed
inventory using a fresh bid limit. Marketable limits do not guarantee fills.
The old quote-session default and immediate cancellation remain unchanged.

The scoped host launcher uses the existing `kis-paper-session` service and
private volumes, with the sample Compose environment and only the approved
Paper credential fields injected in memory:

```powershell
uv run --no-sync --project C:\Users\Public\Documents\thericher-v2 python C:\Users\Public\Documents\thericher-v2\scripts\run_kis_paper_spy_fill_cycle.py --cycle-id spy-fill-20260922-v1 --execute --visits 20
```

Omit `--execute` for a credential-free, broker-free preview. Do not generate a
new cycle ID to evade an unknown outcome. Reusing the same ID reconciles its
persisted legs; at most one fresh submission occurs per visit. The worker uses
one cached client/token, up to 20 visits with 15-second observation intervals,
and a 20-minute soft budget. A container-local 1,260-second deadline with a
30-second termination margin remains effective if the host wrapper dies.
These are this worker's observation/compute bounds, not provider quota claims.

The source-safe `worker-outcome.json` and `dispatch.json` are under
`D:\thericher-v2\model-artifacts\execution\kis-paper-spy-fill-cycle\<cycle_ref>`.
They are mutable operational status, not cryptographic scheduler provenance or
standalone fill proof. Exact private leg state and current account evidence
remain authoritative. `worker_exited` does not mean the cycle filled.
Account/order IDs, raw prices and execution amounts never enter these files.
Fees, settled cash and net PnL stay `not_observed`.

While a cycle owns pending SPY inventory, only its own new SPY legs may use the
common canary submission path. Existing reconciliation/cancellation and other
symbols continue. Recover that same cycle after a timeout; never delete the
ownership file to force an unrelated SPY trade. An expired, never-submitted
exit with owned inventory needs a separately explicit repair, not an automatic
replacement of an unknown order. Old unrelated unknown receipts do not block
a fresh flat/no-open-order cycle or get relabeled resolved.

Deployment: all seven private-state consumer images rebuilt, with 35 matching
isolated/no-network/no-volume source checks. The host launcher's no-credential
preview returned `worker_exited` and the worker recorded `preview` under cycle
reference `38d6ab03e3a307fcd39e068614552c9e32ffc0d38e6160fc620d18ba574ebabb`.
The independent container deadline smoke returned the expected timeout code
124. Neither probe submitted an order or read an account. Current session
image: `sha256:b0ed763f79e9ed40372dd472e63f12e82b5b236d954a3c9b64e26ed6da7da2d3`.

### Restart-Safe Paper State

The private canary state has optional write-once `submission_started_at`,
persisted by atomic temporary write, file flush/fsync, and replace before the
submit transport. It records the original client attempt, not a broker fill or
acknowledgement timestamp. `submitted_at` retains that same attempt when an
order reference is acknowledged; new records require agreement between both.
History uses the durable attempt time, falling back to legacy `submitted_at`,
never the recovery clock. An unknown legacy date remains unknown and cannot
establish terminal cancellation from an absent date query. This does not add a
new submit retry path: unknown side effects still require exact reconciliation.
Pre-submit exposure conflicts remain `intent_recorded`; only unexpired intents
whose own conflict cleared may submit. They never bind/cancel an unrelated ID.

The strict receipt observer understands the optional timestamp, but its
explicit same-day observation semantics are unchanged. Before Execution image
promotion, update all active strict-reader images sharing the private-state
volume; do not assume a host edit changed baked source. D1 has a separate tag
and no source bind mount. A D1-only build uses no real credential file:

```powershell
docker compose --env-file .env.example --profile kis-paper-d1-prospective-observation-pairing build kis-paper-d1-prospective-observation-pairing
```

The actual 2026-09-21 D1 build/image hashes are in `agents/data.md`. It did not
invoke collection. All seven existing Execution private-state consumer images
were subsequently rebuilt, including the two strict read-only consumers;
21 baked-source checks matched. One explicit existing-path SPY Paper session
on the new image at 2026-09-22 00:54 KST reached acknowledged-submit/cancelled-
clean. A networkless read-only state parse confirmed the durable original
attempt timestamp. `agents/execution.md` links exact image/source/receipt facts.
This is not a date-crossing runtime test, terminal fill quantity, or PnL claim.
Do not repeatedly run immediate-cancel sessions to obtain fill/accounting proof.

### Cumulative Paper Fill Accounting

The existing canary/recovery history request now binds documented `inquire-ccnl`
quantity and amount fields to the persisted original ET order date and exact
intent. It does not add another GET, infer fills from acknowledgement, sum
amendment rows, or treat zero remaining quantity as a fill. Private state adds
optional `cumulative_fill`, `fill_observation_status`, and `fill_observed_at`.
Old states still parse. All seven private-state consumer images need the new
parser before a writer runs; never print these private numeric records.
Sanitized canary evidence exposes only categorical quantity/observation status.
Unavailable/conflicting reads retain prior totals but cannot expose a current
position/gross-flow contribution. Cancel and recovery retain earlier positive
observations before requery. Fees, settled cash and net PnL remain unobserved.
The next explicit fillable cycle must use fresh ask/bid limits and exit only
its confirmed inventory; this patch does not alter the immediate-cancel default.

NAS-forward now retains changed whole pages and appends previously absent dates
without replacing old values. Its September23 13:21Z run accepted six pages,
preserved six revision snapshots and grew every target from2 to41 sessions.
The first-retained mixed view remains deferred for its legacy predictive
consumer, not for continued acquisition. The exact hash/as-of whole-page reader
supports separately scoped developmental use with recording-time limits.
See the NAS cache section and Data for schema, receipts and deployed images.
No finality/correct-version inference or schedule change follows. The existing
NAS06:40/pair06:55 next runs remain September24 KST.

### Open/Open Development Comparison

`scripts/run_firstrate_m5_open_open_dev_20260921.py` reuses existing FirstRate
normalization, complete M5 resampling and LocalPaperBroker. `--freeze` writes
only metadata; `--run --contract-sha256 ...` consumes exactly that contract.
The completed `20260921-proposed-r1` namespace is immutable and must not be
rerun or re-frozen as an untouched evaluation. Its four Ridge fits and 48 cells
are already-seen development, not model selection or continuous-capital return.
Artifacts and hashes are in `agents/engine-research.md`; no weights are retained.
Past-known eligibility and future payoff censoring remain separate. Subsequent
experiments need a distinct scientific question, not relabeling these results.

### H30 LSTM Development And Retained Models

`scripts/run_firstrate_m5_h30_lstm_dev_20260921.py` has metadata-only `--freeze`
and separate `--phase cpu|cuda` invocations. Both phases used the same installed
research image, existing offline Compose profiles, and read-only source/data
mounts. Use `.env.example`, project name `thericher-v2`, `--no-deps` and
`--pull never`; this Compose version does not accept `run --no-build`.
The CPU phase must receive the frozen contract SHA; CUDA also requires the
exact completed CPU summary SHA. The parent owns the CPU/GPU timeout and reaps
its child; CUDA additionally holds the existing exclusive GPU lock. No positive
CPU PnL, D1 pairing, or operator approval was required for this development run.

The completed `20260921-h30-r1` contract/results must not be overwritten or
re-executed. Hashes and actual image/dependency versions are in the Engine and
Steward stateboards. `models` contains every final epoch-8 fit, not a selected
checkpoint: numeric NPZ arrays, train-only scalers, and hash-bound JSON config.
`restore_predictor` loads only the fixed in-repo LSTM with `allow_pickle=False`,
exact key/shape/dtype/identity checks and strict state loading. All 16 restored
models passed synthetic CPU inference; this is not a deployment/Paper adapter.

The old research image was missing an already-pinned calendar dependency.
Rebuilding the existing image resolved it. The Dockerfile now installs the
explicit CUDA Torch pin before editable research extras, avoiding a redundant
unconstrained Torch download followed by replacement. Research extras remain
range-resolved; actual versions and the image ID, not a fully locked runtime
claim, identify these completed experiments.

`scripts/run_firstrate_h30_train_diagnostic.py` is the completed train-only
appendix, not another performance evaluation. `--describe` prints its fixed
metadata digest; actual execution requires `--diagnostic-contract-sha256` and
uses the existing CPU profile with read-only data/source mounts and the same
research image. It restores all 16 numeric models, reconstructs only train
inputs/normalizers, compares seeded initialization/final fit, and masks the
old context. No optimizer, GPU, evaluation tensor, prediction export, or new
model is involved. A parent-owned 600-second CPU limit reaps its child.
The whole appendix succeeds or fails, and its immutable namespace is exclusive.
The completed `20260921-h30-r1/train-diagnostic-v1` took 13.201 seconds. Do not
overwrite or rerun it; hashes and findings are in `agents/engine-research.md`.
Training moved parameters but did not beat train-mean MSE, motivating the
bounded learnability follow-up below. This finding cannot choose a market
winner or predict generalization.

`scripts/run_firstrate_h30_train_learnability.py` completed that bounded
follow-up once. `--describe` is metadata-only; the actual single appointment
received the reviewed contract SHA through the existing `research` profile,
same image, `.env.example`, `--no-deps` and `--pull never`. Its parent holds
the existing GPU lock and supervises all source preparation, four fixed fits
and report serialization within 180 seconds; interruption reaps the child.
The sibling `train-learnability-v1/summary.json` is immutable and outside r1.
All four 256-update fits completed in 9.779 seconds; synthetic learnability
and small-batch memorization are demonstrated, with no new evaluation or
retained model. Hashes/results are in Engine Research. No repeated mechanics
check is required before a newly frozen substantive development comparison.

## Standing KIS Paper Authority

The operator has authorized all private `KIS_PAPER_*` development work:

- market, account, position, and open-order reads;
- virtual order submit, modify, cancel, sizing, and reconciliation;
- KIS-derived raw market-data retention in `D:\market_data`; and
- goal-owned schedules for collection, research, validation, and paper work.

Do not require a capital envelope, profitability result, dashboard, report,
trade count, or a per-call confirmation. Keep only technical properties that
preserve truthful paper evidence: paper-only routing, secret-safe output,
idempotent intent before a broker side effect, and reconciliation before an
unknown outcome is retried. There is no one-shot or per-objective quota for
distinct Paper intents or due Paper schedules.

The operator has additionally confirmed that ordinary private Paper trades are
included in this authority. `raw_market_data_retained: false` is a no-bytes
fact about its own historical attempt, not a fixed state to clear, a manual
approval request, or a reason to hold another due collection, Paper action, or
ready lane.

Do not add a future human-release mechanism for private non-live work by
renaming it as a status, safety score, report, model metric, or recovery step.
Those facts may reject only the exact computation with unavailable evidence or
the exact unknown Paper intent awaiting reconciliation.

Market data stays private, local, and unserved. Stop only the affected cache if
applicable source terms prohibit retention or if disk policy would be crossed.
Warn before projected free space falls below 20%; do not begin new large work
that would cross the 15% floor.

## KIS Daily Backfill

The active raw daily cache is at:

```text
D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json
```

Run the finite catch-up whenever the authoritative index has ready daily
cursors:

```powershell
uv run python scripts\backfill_kis_paper_market_data_catchup.py --execute `
  --receipt-root D:\thericher-v2\model-artifacts\data\kis-paper-daily-catchup-v1 `
  --max-chunks 48 --max-runtime-seconds 21600

docker compose --profile kis-paper-daily-backfill run --rm --no-deps --build `
  kis-paper-daily-backfill
```

The worker reattests committed snapshots, recovers a matching orphan before a
new network call, obtains one Paper token for the finite run, requests up to
two daily pages per chunk, writes each raw snapshot plus manifest to `D:`, then
atomically advances the cursor. It stops when no ready target remains, the
chunk/runtime budget is spent, storage protection applies, recovery needs work,
or the shared rate cooldown is active.

When `--receipt-root` is supplied, the worker also writes one immutable
source-safe outcome receipt beneath that external root. It contains only worker
bounds, safe counts/status, a `client_constructed` fact, and containment flags;
it contains no raw rows, response bodies, prices, credentials, account data,
order data, or repository path. A drained cache can therefore leave durable
proof without constructing a client or requesting a token.

All KIS Paper market-data workers use the same external request gate below
`D:\market_data\us_equities\kis_paper_private\collection-control-v1`. The
installed default serializes request starts at least 1.0 second apart. The
daily and intraday collector-local pacing constants alias this shared setting,
so there is no longer local delay that silently slows the owned request path.
HTTP `429` or KIS `EGW00201` records a 60-second categorical cooldown. The
control file stores only timing state, never response bodies, raw rows,
credentials, account facts, or authority state.

On 2026-07-26, a bounded source-safe QQQ terminal-head calibration accepted two
full minute pages through one in-memory client/token at a 1.0-second candidate
interval with zero categorical limits or errors. The resulting installed
end-to-end setting is 1.0 seconds: the shared gate and both owned
collector-local delay constants are aligned, while the 60-second cooldown and
five-minute token-start guard remain unchanged. This is not a general source
ceiling or historical-pagination claim. The probe accepts only a supported
interval and refuses to record a successful calibration when observed
page-request starts are faster than its claimed test interval. Retain a future
second delay only when it protects a path that cannot use the shared gate, and
record its owner, reason, and observed effect.

There is no verified daily quota or general route ceiling. Do not add an
unbounded daemon or parallel flood, and do not run a second worker against the
same cache while its owner is active. A finite, goal-owned capability probe may
measure the interval, cooldown, page budget, or capture cadence and recommend a
replacement from official-source or measured evidence. The probe itself cannot
loosen or remove the current evidence-backed request gate or cooldown. A later
bounded change may do so only after recording its calibration fact. A resulting
long-lived single-client capture worker may retain one in-memory token for its
own lifetime; it remains owned, observable, concurrency-bounded, and
recoverable.

These are the current finite recovery controls. Keep them active through an
isolated failure; any future lower/higher page pace, retry rule, or scheduler
throttle needs official-source or bounded-measurement evidence and a stated
recalibration fact. A quota or cooldown becomes the owning worker's next due
time, not a foreground Codex sleep. A failed capability probe remains scoped to
its target and never justifies an unbounded retry loop or a pause on another
ready lane.

Do not conflate the three timing mechanisms. The five-minute token-start guard
spaces only separate token POST attempts; it does not delay an existing
in-memory client or force a five-minute worker sleep. The actual catch-up
script passes a zero inter-chunk interval, so it proceeds page-by-page under
the shared request-start gate until its finite chunk/runtime budget, a real
cooldown, or another owned recovery fact stops it. A future faster pace must be
measured with one client and one changed pacing variable at a time, reporting
only safe counts for requests, accepted pages, categorical limits, elapsed
time, and the fact that would retain or replace the setting.

If the safe worker output is `auth_rejected` while the request gate has no
`last_rate_limit_at_utc`, first determine whether a separate worker issued a
token within the prior five minutes. The five-minute cross-process token-start
guard prevents short-lived workers from colliding; it is not the token lifetime.
KIS documents a 24-hour access token and a six-hour renewal behavior. Reuse one
in-memory client and its token for the finite/long-lived worker lifetime before
interpreting credentials. Only a spaced, single-client token failure is a
reason to verify the active KIS **Paper** App Key/App Secret in local `.env` or
the KIS Developer Portal. The data-only container does not mount `.env`; it
receives the pair through Compose. Never print or copy either value, and do not
reinterpret this scoped recovery fact as a pause on another Data, Research, or
Paper job.

The installed `thericher-kis-paper-daily-backfill` Windows task runs Tuesday
through Saturday at 07:00 KST. It invokes only the Docker profile above after
the final 06:20 intraday-head trigger and before the 08:10 operating review. Its
container mounts `D:\market_data` at `/app/market_data` plus the external
artifact root at `/app/model_artifacts` solely for source-safe catch-up
receipts. It receives only the two KIS Paper market-data variables; it has no
account, order, live, model, or GPU surface.

The data-only Docker image deliberately does not mount `.env`. Its shared
market-data loader may consume only a complete injected
`KIS_PAPER_APP_KEY`/`KIS_PAPER_APP_SECRET` pair with non-live
`THERICHER_MODE`; a partial pair or live mode fails closed. When neither Paper
app value is injected, host tools retain the strict local `.env` parser. Never
add account or `KIS_LIVE_*` variables to this service.

## KIS 1m Historical Capability

The current-head collector keeps its documented `PINC=0` first request. A
source-safe historical-reach probe may set `PINC=1` only to test the exact
prior-day route; it writes no raw minute rows, credentials, or account data.

```powershell
uv run python scripts\probe_kis_paper_minute_capability.py --execute `
  --include-previous-day --target QQQ/NAS --max-pages 3 `
  --artifact-root D:\thericher-v2\model-artifacts
```

On 2026-07-27, QQQ/NAS and SPY/AMS each returned accepted terminal
same-exchange-date pages with no continuation cursor under this scope. Do not
start a serial historical dispatcher or retry flood for either exact route. The
result is limited to those endpoint/request contracts; a future historical
attempt needs an explicitly named alternate endpoint, exchange route, or
compatible source and a fresh capability contract. Fresh scheduled head capture
continues independently.

Raw retention metadata is an actual outcome: `true` means a snapshot was
written, while a failed or empty response can truthfully remain `false`. It is
never a permission switch. A historical `false` is not a consent hold: once a
fresh correctly scoped collection is due after normal recovery or pacing, run
it rather than asking for approval or treating the old observation as a latch.
The current intraday collector and offline loader ignore an unretained legacy
marker without a cache snapshot before cache validation, deduplication, cursor
progress, or bar loading.

Historical one-shot artifacts are non-authoritative. Their completion or
retention value must never reserve, disable, or require approval for a later
correctly scoped KIS Paper collection, account, order, or scheduler run.

Do not add an `awaiting_operator_approval` state, a capital/profitability
threshold, a `safe_to_submit` approval proxy, or a global halt derived from a
historical marker. KIS Paper actions are standing-authorized by default. A
runner may stop only its own exact request for paper-host isolation, durable
identity conflict, or unknown-outcome reconciliation; that technical result
does not suppress another distinct Paper action or another lane.

Default to the next due, correctly scoped private Paper action. Do not add a
capital, profitability, trade-count, report, input-quality, or historical-run
checkpoint as an approval proxy. A factual unavailable input produces only its
own recovery or no-intent result; it does not stop independent work. Preserve
the record and retain the exact-intent reconciliation rule instead of deleting
or rewriting evidence.

If a page is repeatedly structurally invalid, diagnose only safe structure
(counts, field names, validation class, and session metadata), preserve the
failure evidence, and stop that target when the source-quality limit is clear.
Do not brute-force the same page or silently accept its remaining rows. This is
data correctness, not an approval condition for other KIS Paper or research
work.

For the private daily cache, two consecutive `daily_response_invalid` outcomes
with zero rows at the unchanged cursor mark only that target `source_limited`.
The worker then continues another ready target; this is neither a Paper-order
hold nor a global collection stop. A different endpoint, cursor, or
evidence-backed parser contract starts a new bounded source scope.

## KIS Fixed NAS Daily History

The current-listing six-symbol history cache is separate from the ETF catalog,
probe, and frozen panel:

```text
D:\market_data\us_equities\kis_paper_private\daily-nas-history\v1
D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-history-v1
```

Run only its dedicated Data-only Compose profile. Do not use host `--execute`
paths or override its four canonical container roots:

```powershell
docker compose --profile kis-paper-daily-history run --rm --no-deps `
  kis-paper-daily-history
```

The profile mounts only the dedicated cache, shared collection-control root, and
dedicated artifact root. It injects only `KIS_PAPER_APP_KEY` and
`KIS_PAPER_APP_SECRET` with `THERICHER_MODE=off`; it never receives account or
live values. The collector permits only the KIS Paper token POST and its fixed
NAS daily-price GET route.

Before relying on a run, reattach the source-safe index/receipt rather than
assuming a prior console output is current. Empty terminal pages produce no raw
snapshot; non-advancing cursors stop only that target before duplicate storage;
valid orphan snapshots are recovered before a new request. The worker's shared
retry/token due belongs to the worker or a goal-owned continuation, never to a
foreground Codex sleep or a different lane.

The profile's normal bounded continuation has a global cap of 288 chunks and
1,800 seconds. It retains one in-memory client/token only for its own process;
when an actual future `next_due` occurs, only that worker may wait and then
reuse the client. Each internal collection cycle keeps its immutable source-safe
receipt and the worker also writes one `continuation=*/summary.json` aggregate
under the external artifact root. The aggregate records counts, elapsed bucket,
cursor projection, retry-wait count, reuse outcome, stop reason, recovery, and
route/artifact isolation categories only. It never contains raw rows, request
headers, credentials, account data, or broker bodies.

Do not start a second worker against this cache. A summary whose reuse outcome
is `not_observed_no_future_retry_due_observed` means there was no eligible
future retry within that bounded run; it is not a token failure, a permission
hold, or a reason to delay another lane. `complete`, `source_limited`, and
`deferred` remain target-local facts. Recover a deferred target only through a
new bounded target-local objective; do not edit the durable index by hand or
blend another provider into its rows.

The recovery profile's `--recover-deferred-targets` mode is deliberately an
exact historical repair contract, not a general backfill switch. It admits only
the named deferred keys and their expected failure classes, fences orphan
recovery to those keys, and preserves every terminal peer byte-for-byte. Within
one core invocation, each admitted target receives at most one collection
chunk; a valid partial advancement becomes `ready` and is eligible only in a
later bounded invocation from its persisted cursor. A second unchanged-cursor
`daily_response_invalid` follows the target-local source-limit rule above;
transport failure remains deferred for only that target. Once all targets are
terminal, the profile exits without constructing a KIS client or making a
market-data request.

## KIS Broad Current-Listing D1 Cache

The broad daily cache is a source-separated current-listing acquisition path:

```text
D:\market_data\us_equities\kis_paper_private\daily-nas-broad\v1
D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-v1
```

It derives targets only from the pinned local NASDAQ directory snapshot mounted
read-only at `/app/symbol_directory`. Its registry is explicitly current-listing,
non-PIT, non-ranking, and not provider price data. It must never be treated as
historical membership, an adjustment/corporate-action guarantee, a source blend,
a ranking input, or a Paper-order input.

For the deterministic eight-target bootstrap, run the dedicated profile without
overriding its command:

```powershell
docker compose --profile kis-paper-daily-broad-backfill run --rm --no-deps `
  kis-paper-daily-broad-backfill
```

The profile is read-only except for dedicated D: cache/control/artifact mounts.
It receives only `KIS_PAPER_APP_KEY` and `KIS_PAPER_APP_SECRET` with
`THERICHER_MODE=off`, uses only KIS Paper `dailyprice`, and has no account,
position, quote, order, or live route. A preflight uses the same mounts but no
credentials:

```powershell
docker compose --profile kis-paper-daily-broad-backfill run --rm --no-deps `
  --entrypoint python kis-paper-daily-broad-backfill `
  scripts/backfill_kis_paper_daily_broad.py --preflight
```

The worker reattests registry/index identity before client construction and
validates every committed snapshot before consuming it. It keeps target-local
cursors and progression externally. Breadth-first continuation chooses targets
with fewer accepted pages before a deeper target. Two identical source-invalid
responses close only that target as `source_limited`; shared rate/auth/token
conditions remain deferred. A `rate_limited` response from an already active
client gets exactly one gate-due recovery within that worker's existing runtime;
the same client/token is retained, the next normal target selection resumes,
and a second rate limit yields to the owner scheduler. Known retry due times at
worker start, auth/token stops, runtime expiry, and storage-floor conditions
still yield without client construction. This recovery does not change the
one-second request-start gate or turn Codex into a foreground sleeper.

On 2026-08-19, the bounded continuation capability check reattached the
2,119-target registry and completed with zero chunks, accepted pages, failures,
or remaining targets. Its external source-safe receipt is
`D:\\thericher-v2\\model-artifacts\\data\\kis-paper-daily-nas-broad-v1\\run=20260819T140140890766Z-90568a0332da\\receipt.json`
(`sha256:065e6b4189e172f78047304b21d81361355eebe9f3c8db7d2b2935f3beb430a3`).
The unchanged index is generation 26,368 with 1,089 `complete` and 1,030
`source_limited` targets. This terminal outcome built no KIS client and made no
market-data request. Do not start a long worker merely to retry an exhausted
historical cursor; a separately bounded forward cache owns later daily sessions.

Install the continuation owner only after a successful bootstrap:

```powershell
.\scripts\install_kis_paper_schedules.ps1 `
  -ScheduleName thericher-kis-paper-daily-broad-backfill
```

It triggers Tuesday through Saturday every 30 minutes from 00:15 through 23:45 KST.
`IgnoreNew` retains one active 8-hour/24,000-chunk worker; a later trigger
recovers a failed worker without a duplicate collector. The Windows task limit
remains 870 minutes so Docker startup and final receipt writing fit outside the
worker bound. This is a reversible postrun-cadence calibration: compare the
first complete 8-hour cycle's source-safe `rate_limit_recovery_outcome`, terminal
postprocess result, and rolling 24-hour wall-clock accepted-page count with the
prior long-cycle evidence before retaining it. Do not hand-edit its index or
launch a second worker against the same cache. Inspect only source-safe aggregate
receipts/index facts before relying on its coverage.

Materialize a read-only source-local coverage snapshot without calling KIS:

```powershell
uv run python scripts\materialize_kis_paper_daily_broad_panel.py
```

The materializer takes a byte-stable index read, reattests the registry,
target cursors, source manifests, raw hashes, and row lineage, then writes an
immutable external manifest under
`D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1`
and a source-safe receipt under
`D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-panel-v1`.
It never opens the collector lock, calls a network/credential/broker route, or
copies raw rows. A changing index or source hash fails the one materialization;
it is not a collector hold. The resulting panel remains current-listing,
non-PIT, unadjusted, corporate-action-unqualified, and session-finality-
unattested, so it is not a model target, ranking, or training contract.

Compare two frozen panel manifests without reopening the mutable index or
calling KIS. The command writes only a source-safe external receipt with
dataset hashes and aggregate shared/mismatched fingerprint counts:

```powershell
uv run python scripts\compare_kis_paper_daily_broad_panel_continuity.py `
  --baseline-manifest D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1\<baseline>\manifest.json `
  --candidate-manifest D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1\<candidate>\manifest.json
```

An `equal` result establishes only canonical bar equality for shared
target/session rows in those two frozen snapshots. A `mismatch` result exits
nonzero and is not a harmless coverage warning. Neither outcome changes the
collector, source scope, schedule, or research eligibility.

The existing `thericher-kis-paper-daily-broad-backfill` task now runs one
host-side postprocess only after its Docker collector exits zero:

```powershell
uv.exe run --offline python scripts\postprocess_kis_paper_daily_broad_panel.py
```

The postprocess reuses the byte-stable materializer, compares the candidate
with the frozen generation-604 manifest, and writes one deterministic
source-safe outcome receipt under
`D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-panel-postrun-v1`.
It returns zero only when all current registry targets have non-quarantined
coverage, coverage has not regressed from generation 604, and all baseline
rows remain in the zero-mismatch overlap. A changing index, incomplete
breadth, missing continuity, or mismatch writes a scoped `retry` receipt and
returns `20`; it never stops or changes the collector. The host path reads no
`.env` or credentials and calls no KIS, broker, or network route.

After a `complete` postrun, the same task automatically invokes the offline
chronology observer with the exact digest-named postrun receipt. The observer
derives both immutable panel manifests from the receipt's dataset hashes, then
records only the frozen candidate's aggregate per-target bar-count and
calendar-span buckets. A manual invocation may still supply both manifest
paths explicitly:

```powershell
uv run --offline python scripts\observe_kis_paper_daily_broad_panel_chronology.py `
  --postrun-receipt D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-panel-postrun-v1\<receipt>.json `
  --repository-root C:\Users\Public\Documents\thericher-v2
```

It reattests the existing complete postrun and panel manifests, then writes one
external aggregate-only observation. It never emits a global common-history
threshold or a `feasible`/research-eligibility verdict: current-listing and
source-limited targets make such a boolean misleading. The observation is
perishable by candidate generation and is not a split, target, model, GPU,
ranking, Paper, or live input. An observer recovery exit is logged as its own
scoped follow-up and does not turn a successful collector/postprocess task into
a scheduler failure; it makes no KIS, credential, network, broker, or cache
call either way.

## KIS NAS D1 Forward Cache

The owned collector enables `retain_revisions=True`. A valid changed incoming
page is saved whole, with a conservative local `recorded_at` and the prior
snapshot binding in the same atomic index. The first-retained view appends new
dates but never overwrites old overlaps; both snapshots are verified on read.
Identical-page retries deduplicate. The legacy predictive projection stays
deferred for that contradictory view even after a later clean page. This does
not prevent acquisition or independent Paper work. For separately scoped
development, `load_kis_paper_daily_nas_revision_as_of` selects one exact symbol/
snapshot hash at or after recording; it never builds a mixed latest-row view.
It proves neither historical availability nor provider finality/correctness.

Runtime evidence: September23 13:21:08Z accepted6 pages, retained6 revisions,
and advanced each target2->41 sessions. Exact receipt is in `agents/data.md`.
Collector/preflight use normal Compose builds. The observation image received
a networkless source-only overlay on its pinned prior image, with unchanged
Torch2.7.0+cu128; all nine changed-source hashes match. No schedule, Paper image,
credential policy or shared control root changed. Normal source builds remain
valid; the overlay merely avoids reinstalling an unchanged CUDA runtime.

The prospective six-symbol NAS D1 cache is separate from the frozen historical
panel and exists only under external roots:

```text
D:\market_data\us_equities\kis_paper_private\daily-nas-forward\v1
D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-forward-v1
```

The direct collector is credentialed and should be used only for a bounded
Data-owned recovery or probe:

```powershell
docker compose --profile kis-paper-daily-nas-forward run --rm --no-deps `
  kis-paper-daily-nas-forward
```

It injects only the two KIS Paper market-data variables with `THERICHER_MODE=off`.
The route permits only the virtual-paper token and fixed `AAPL`, `AMZN`, `GOOGL`,
`META`, `MSFT`, and `NVDA` NAS daily-price requests. It has no account, order,
live, model, or GPU surface. The collector retains only prior completed D1 rows
strictly after the frozen boundary and never merges them into the historical
panel.

The installed `thericher-kis-paper-daily-nas-forward` task invokes
`scripts\run_kis_paper_daily_nas_forward_schedule.ps1` at 06:40 KST on
Tuesday through Saturday. It first runs the credential-free preflight. A
current verified cache runs the network-disabled observer; exit `10` runs the
collector once, and only a complete collector result runs the observer. A
`partial` or `deferred` collection returns recovery exit `20`, so stale or
incomplete cache data cannot be observed as a new result. An invalid observer
cache also returns `20` after writing its source-safe recovery receipt.

The observer has no KIS credentials or network route, mounts market data
read-only, and runs the frozen consumer only when exactly three all-six common
post-boundary sessions exist. Below that threshold it writes a completed
external `input_unavailable` receipt. It does not select, tune, rank, ensemble,
promote, submit, or modify anything.

Install or refresh the task normally with:

```powershell
.\scripts\install_kis_paper_schedules.ps1 `
  -ScheduleName thericher-kis-paper-daily-nas-forward
```

That rebuilds its three images before updating the task. During a bounded
installer recovery after those exact images have already been verified,
`-SkipImageBuild` reattests each Compose image before registering the task; it
does not bypass image existence checks.

Every successful page advances the target's source-safe accepted-page count. An
exact duplicate leaves the raw snapshot bytes unchanged. Transient transport,
authentication, rate, or reconciliation failures are target-local `deferred`
recovery, not `source_limited`; a global cache-integrity failure emits a
source-safe `reconcile` receipt. The cache's all-six common-session count and
the three-session prospective consumer status are distinct facts. Do not wait in
the foreground for a future session; let the owned task collect it while other
ready work continues.

## KIS QQQ/SPY D1 Forward Cache

The QQQ/NAS plus SPY/AMS forward stream is a separate Data cache, not an
extension of the frozen QQQ/SPY history or the six-symbol NAS forward stream:

```text
D:\market_data\us_equities\kis_paper_private\daily-qqq-spy-forward\v1
D:\thericher-v2\model-artifacts\data\kis-paper-daily-pair-forward-v1
```

It retains only completed KIS Paper daily rows after 2026-07-24. The
credential-free preflight is network-disabled and mounts the cache read-only:

```powershell
docker compose --profile kis-paper-daily-pair-forward run --rm --no-deps `
  --pull never kis-paper-daily-pair-forward-preflight
```

Exit `10` means collection is required. The credentialed collector injects only
the two KIS Paper market-data variables and has no account, position, quote,
order, model, GPU, or live route:

```powershell
docker compose --profile kis-paper-daily-pair-forward run --rm --no-deps `
  --pull never kis-paper-daily-pair-forward
```

The companion readiness mode is network-disabled, mounts no market-data cache,
and validates only the shared control state plus aggregate Paper environment
availability. It writes a source-safe receipt but does not construct a client,
request KIS, or commit cache state:

```powershell
docker compose --profile kis-paper-daily-pair-forward run --rm --no-deps `
  --pull never kis-paper-daily-pair-forward-readiness
```

Install or refresh the guarded task with:

```powershell
.\scripts\install_kis_paper_schedules.ps1 `
  -ScheduleName thericher-kis-paper-daily-pair-forward
```

It runs at 06:55 KST Tuesday through Saturday. Before collection it checks the
host KST identity and whether the NAS forward, broad, or legacy daily worker is
running. A failed guard runs only the credential-free preflight with a
source-safe recovery reason, returns `20`, and leaves retry to the next due
time. It does not sleep the foreground, create a parallel request flood, or
block independent work.

### QQQ/SPY D1 Prospective Observation Pairing

This is an independent Data measurement, not the company objective. The
2026-09-21 source repair budgets one daily page for each of the two fixed
targets through one shared client/token. It changes neither request pacing
nor schedules. `daily_page_limit_exceeded` is a safe diagnostic category, not
an external quota claim. Synthetic integration tests do not establish that
the installed image contains the patch or that either observation succeeded.
Data must check owned runtime source before deployment/measurement claims;
preserve existing receipts, cache quarantine, and the worker's `next_due`.

The separate revision-leakage measurement never writes this cache. Its task is
`thericher-kis-paper-d1-prospective-observation-pairing`, with first and later
triggers at 08:15 and 23:20 KST Tuesday through Saturday. It mounts the v2
cache read-only, uses only the existing virtual-Paper `dailyprice` route for
QQQ/NAS and SPY/AMS, and stores state plus immutable source-safe receipts at:

```text
D:\thericher-v2\model-artifacts\data\kis-paper-d1-prospective-observation-pairing\v1
```

The first stage records a fixed source-contract hash, completed-session key,
UTC observation time, and one canonical row hash per target. The later stage
must bind exactly to that first receipt and same session. A missing target,
invalid receipt/state, cache conflict, absent session row, or identity mismatch
is `input_unavailable` or `disqualified` for that session. A match is
`measurement_only_match`; it does not establish point-in-time availability,
provider finality, corporate-action status, model input, GPU eligibility,
Execution input, Paper order, or live behavior.

The worker owns `next_due` in its external state and does not poll or foreground
wait. Do not invoke the task manually. The initial container smoke was outside
the scheduled minute and returned `not_due` without constructing a KIS client.
The approved offline reader historically reattached completed-session 2026-09-04
first stage as `input_unavailable/first_observation_target_failure` (receipt
`sha256:a7d54a2220bb5f7ca78a9e34a48c827fbe6c03d4c5f575c5c23a0d12519af401`).
Its hash-bound receipt has no first-observation binding and no later observation,
so it is not a two-observation outcome. Source-safe Task Scheduler status is
`Ready`; task exit alone is not stage or outcome evidence. The reader-owned
`next_due` is `2026-09-07T23:15:00Z`.

The rebuilt observer image adds `observation_failure_codes` only to a future
target-level first-stage failure. The list is sorted and limited to the existing
sanitized recovery taxonomy; an invalid code makes the immutable receipt fail
offline validation. A direct first-stage exception receives one fixed family
reason instead. Neither path stores error text, raw rows, credentials, account
data, or stack traces, and neither changes task timing, KIS route, cache writes,
or pair-result semantics.

After the task writes a result, use only
`read_current_kis_paper_d1_prospective_observation_pairing_outcome` from the
pairing module to inspect it. The reader is host-only and offline: it validates
the hash-bound `current.json` pointer, its immutable receipt, and, for a later
result, the exact first receipt ID/hash, session, and first-observation hashes.
`current_pointer_unavailable` means no result is available yet; it is not a
match, a failure, a retry instruction, or a reason to invoke the task.
`first_recorded` is likewise incomplete: only a validated `later` receipt is a
two-observation outcome. A hash-bound `input_unavailable` first-stage receipt
is likewise scoped to its session and does not supply that pair outcome. The hash linkage is provenance under an assumed-honest
artifact host, not cryptographic proof of Task Scheduler origin, provider
finality, or decision-time availability.

For a repeatable source-safe host read, use the narrow CLI below. It invokes no
task, Docker service, KIS client, credential loader, or cache writer and emits
only the validated receipt identity/binding and categorical outcome fields.

```powershell
uv run --extra dev python scripts/read_current_kis_paper_d1_prospective_observation_pairing_outcome.py `
  --artifact-root D:/thericher-v2/model-artifacts `
  --repository-root .
```

The CLI also accepts the exact pairing receipt root shown above when a task
handoff already supplies that narrower path.

On 2026-08-19, the bounded direct refresh first wrote a `collection_required`
preflight receipt for the 2026-08-18 eligible session
(`sha256:7987f5a89f3ec8631646ece7718f0433ae7308aad9b27060cf0efffa4ad7028f`).
Its one permitted collector then wrote a hash-bound `deferred` receipt with
`token_request_not_due`, zero new accepted pages, and zero changed targets
(`sha256:f3305c86da4ce345beed1e734f30e614356827ed54f678e3dcf87596c32f5914`).
Both receipts are external under the pair-forward artifact root and contain no
raw rows, credentials, or account data. Do not retry that bounded direct run;
the existing task owns the next due attempt while independent work continues.

### Causal Qualification

The completed offline predicate reads the existing pair-forward cache plus one
explicit source-safe parent receipt. It writes only a canonical aggregate
receipt under:

```text
D:\thericher-v2\model-artifacts\data\kis-daily-forward-causal-qualification-v1\run=20260820-kis-daily-forward-causal-qualification-r1\receipt.json
```

The current receipt hash is
`sha256:9b361addc7e76dd5cd8ff6bf9800077c8a8866f3b5a21eeedbeb6d2a2dcdc3cf`.
It is `input_unavailable`: source/pair identity, complete-calendar continuity,
and chronological boundary are satisfied, while named clock/session,
decision-time availability, and provider finality are `not_observed`. It is not
a KIS call, credential read, Docker or scheduler invocation, GPU use, research
promotion, or Execution input.

Do not overwrite this receipt. A later causal-qualification run requires a new
explicit label and a current cache/parent-receipt contract; it must capture the
missing runtime facts rather than infer them from a file timestamp, task exit,
or hash.

### One-Shot Collection Outcome

The completed one-shot preflight returned `collection_required` with external
receipt `run=20260819T155737898831Z-4b91351878114c11/receipt.json`
(`sha256:77de03be7d6f4f1ce0fb567244e239966869c39cc50f75f2be361369d7dc9ef9`).
Its exactly one existing collector call then returned
`unavailable/collector_unavailable` with external receipt
`run=20260819T155753946326Z-d0ec4d21d99446fa/receipt.json`
(`sha256:7bba8e74781c803bcdcaaef44aaabdc6b4021b0f039919296618430c996a59b3`).
That receipt contains no cache payload, so do not use it as a causal parent or
retry it. The existing cache remains readable with seven common sessions.

### Stage Discrimination And Runtime Image Limitation

The source and synthetic tests now distinguish only four source-safe collector
failure stages: `control_gate`, `environment`, `collection`, and `commit`.
They do not expose secret/config names, exception text, response detail, target
identity, or raw data.

The one networkless readiness run wrote
`run=20260819T161924502292Z-333ce65960854fcd/receipt.json`
(`sha256:e64e4888b2f5e4937df1712c2bb72f3bf6f6d1410a55bef1d9ba9d09254ee4e5`)
as `ready/aggregate_ready`, token-due, rate-open, no-network, and no-cache
write. Its exactly one allowed collector invocation then wrote
`run=20260819T161956811379Z-4948e7f7e87b4fe0/receipt.json`
(`sha256:b00e687001ff988bf1e2b32e53ee9c5eebf7585bdacc33b057259c64f50870e0`)
as `unavailable/collector_unavailable` with no cache payload and no
`failure_stage`. That exact receipt therefore does not attest that the
stage-aware source was the collector's runtime image. It is not a stage,
provider, finality, or availability conclusion, and it was not retried.

The collector image was rebuilt from the workspace without another KIS call.
A later bounded source/image-provenance package must make that runtime identity
observable before a fresh independent collection is considered; this is a
technical evidence boundary, not an operator approval or a standing hold on
other work. A ready/due result still cannot prove decision-time availability or
provider finality.

### Shared Runtime Contract

Claude's follow-up verdict was `supported-with-limits`: a receipt fingerprint
must live inside `payload`, because the causal reader validates the receipt's
top-level schema exactly. It therefore cannot claim a full image digest. The
three existing pair-forward services now share this local image tag:

```text
localhost/thericher-v2/kis-paper-daily-pair-forward:local
```

Every new pair-forward receipt includes `payload.runtime_contract_sha256`. It
is a deterministic hash of the frozen stage contract only: receipt kind,
unavailable reasons, and the four fixed collector stages. It reads no file,
environment, path, timestamp, credential, cache, or market-data value. A
matching hash establishes that the runtime implements this fixed diagnostic
contract; it does not prove general image freshness or source-build provenance.

Build the shared local contract, then use the credential-free preflight to
reattach it without a KIS request or cache write:

```powershell
docker compose --profile kis-paper-daily-pair-forward build `
  kis-paper-daily-pair-forward
docker compose --profile kis-paper-daily-pair-forward run --rm --no-deps `
  --pull never kis-paper-daily-pair-forward-preflight
```

The 2026-08-19 preflight wrote
`run=20260819T164013025667Z-6219bc10fc8c4dd4/receipt.json`
(`sha256:e5c2cf9be1bace915d8c3deb19a57ab5a5f0cc1d7bff634afbeb8f2a38090a7a`)
as `collection_required`. Its `runtime_contract_sha256` matched the host's
static contract hash. The service remained `network_mode: none`, mounted the
cache read-only, had no credentials, and did not invoke readiness or collector.
This reattaches the runtime contract only; it neither supplies a data input nor
changes provider finality, decision-time availability, causal qualification,
Research, Execution, or Paper eligibility.

The subsequent one-shot collector was invoked exactly once with `--pull never`
and no build request. Claude's recheck was `supported-with-limits`: the common
local tag proves only the selected tag name, while the payload contract hash
proves only the fixed stage contract. Neither proves immutable image identity,
freshness, configuration, or source-build provenance. The collector wrote
`run=20260819T165517911332Z-b52ac5d46a704e12/receipt.json`
(`sha256:804786626d4fe10dbac971d21f563a54298e9afae92d7beb69c0c4caef8b74cf`)
as `unavailable/collector_unavailable/failure_stage=commit`; its payload
contract hash matched the preflight and host static contract hash. It retained
no cache payload, raw row, credential, or account datum and all non-market-data
route flags are false. A credential-free offline cache reattest remains valid at
seven common sessions, with zero cache-file and index modifications observed in
the invocation time window. This records only an unknown commit-stage failure,
not its cause, a data availability fact, or a consumer qualification. Do not
retry it; a later source/fixture-only fixed failure-kind change must precede any
new collection objective.

### Commit Failure Kind V2

The source/fixture-only recovery changed the static pair-forward contract to v2
(`sha256:82a72fb357f6d7ad8d3d8bb447cc4310461bdb9226afbca26e0e1ad9b42a8c1c`).
Only a receipt already classified as `failure_stage=commit` may carry optional
`payload.commit_failure_kind`. The only values are selected in fixed order from
the caught exception family: `cache_contract`, `storage`, or `validation`. The
value is a source constant; exception text, type name, path, raw data,
credential, account data, and dynamic fields are never retained. A nonmatching
exception omits the field, so this is partial diagnostics rather than an
exhaustive runtime cause claim.

The v2 hash intentionally differs from the v1 preflight and collector receipts.
Do not compare them as matching runtime contracts. Before a future collection,
build the same existing shared local tag and create one fresh credential-free,
networkless v2 preflight. Only a matching `collection_required` preflight can
precede one collector invocation; `cache_current` or `unavailable` closes that
attempt without a collector call or retry.

### V2 One-Shot Outcome

The one credential-free v2 preflight wrote
`run=20260819T172512279495Z-e9baed100e2548a8/receipt.json`
(`sha256:cf95c93741330d60d95dc040e12446d3a34e899d8a3565b82cb0f8b2743e6ec2`)
as matching `collection_required`. The existing shared image tag was built
once; its locally observed image identity did not change before or after the
following collector, which is not a full provenance claim. The exactly one
collector call wrote
`run=20260819T172546233523Z-2f2f777f8c454d19/receipt.json`
(`sha256:0c28203f24a098685f8068433e2250f14c1774bde99e5e87e64de1862ae53d42`)
as `unavailable/collector_unavailable/failure_stage=commit` with
`commit_failure_kind=cache_contract`. It retained no cache payload, raw row,
credential, or account data, and every non-market-data route flag is false.

The cache and index reattach to their prior source-safe identities with seven
common sessions, and no cache-file or index mutation was observed in the
collector window. The fixed kind does not identify an exact subcause, so this
outcome is closed without retry or consumer change. The next local-only package
may expose a fixed phase for a future `cache_contract` failure; it must never
serialize exception text, exception class, path, raw data, credential, or
account data.

### Commit Failure Phase V3

The source/fixture-only v3 contract is
`sha256:219a3a13d1419f9b65dc34f1d6fa3a3ffcb534b045b1d1729308cb8d944e5893`.
Only `failure_stage=commit` with `commit_failure_kind=cache_contract` may carry
optional `commit_failure_phase`. The only values are fixed operation-boundary
constants: `cache_prepare`, `snapshot_persist`, `index_persist`, and
`cache_reverify`. The cache writer preserves the caught cache exception class
and message for local callers, then exposes only its allowlisted phase through
the collector payload. Storage and validation failures, every non-commit stage,
and successes omit the field.

The phase changes no prior receipt and cannot prove an exact data cause without
a later independent outcome. Focused fixture tests cover all four boundaries,
allowlist rejection, field omission, and a private-detail canary. This package
made no credential, KIS, Docker, cache-write, scheduler, Research, Execution,
Paper, or live call.

### V3 One-Shot Outcome

Claude's collection recheck was `supported-with-limits`: exact-one and
matching-hash enforcement belongs to the host orchestration, and a deferred
execute can alter the cache observation without a page collection. The v3
networkless preflight wrote
`run=20260819T175759151923Z-5abf449a6416418f/receipt.json`
(`sha256:6fa27ec40b8009b76c0c31fe6210a4ad8814676566bc5f6cc442fa71a011fd5a`)
as matching `collection_required`. It retained no cache payload and all
non-market-data route flags are false. Exactly one collector then wrote
`run=20260819T175852692208Z-6dd72fc496fc48d5/receipt.json`
(`sha256:cd1b1222c61da98aa12091b8a61bd153cd91e2943d0c79c98dafe4340eb33dc3`)
as `unavailable/collector_unavailable/failure_stage=commit` with
`commit_failure_kind=cache_contract` and
`commit_failure_phase=cache_prepare`.

The selected local tag was unchanged across the call, which does not prove
immutable image provenance. The receipt contains no cache payload or forbidden
market/private fields. The offline cache/index reattach to their prior
identities with seven common sessions and two seven-row streams; zero files were
observed changed in the bounded invocation window. This is a fixed prepare-phase
category, not an exact cause or a data/finality/consumer conclusion. Do not
retry. A later local-only diagnostic may distinguish only `cache_access`,
`cache_state_load`, or `incoming_merge` for a future matching result.

### Prepare Subphase V4

The source/fixture-only v4 contract is
`sha256:95e0ec0fd7408e237cbb79e4010e152291dd4322f58133bd4c46207c258dc893`.
Only the exact triple `failure_stage=commit`,
`commit_failure_kind=cache_contract`, and
`commit_failure_phase=cache_prepare` may carry optional
`commit_failure_prepare_subphase`. Its fixed values are `cache_access`,
`cache_state_load`, and `incoming_merge`. They identify only the static source
region where a cache exception surfaced, never an exact cause. An unclassified
boundary omits the field. The cache exception type, message, and args remain
unchanged, and no dynamic error, path, raw row, cache value, credential, or
account datum enters the receipt.

Claude's falsification-first review was `supported-with-limits`: preserve the
region-versus-cause distinction and add no incident-shaped value. Fixture tests
cover every fixed region, triple mismatch, unclassified omission, exception
preservation, and a private-detail canary. This package made no credential,
KIS, Docker, cache-write, scheduler, Research, Execution, Paper, or live call;
the completed v3 receipt remains subphase-unknown.

### V4 One-Shot Outcome

The v4 recovery check returned no Claude output, so it is
`review_unavailable`, not a verdict or hold. The matching credential-free
preflight receipt is
`run=20260819T183535741410Z-6454fe31110444e3/receipt.json`
(`sha256:e24e124b7e2ab6ec50496b5fc9a70ce21198f1483606527b442e9c749cf9029f`)
with no cache payload, no network requests, no cache writes, and every
non-market route false. It permitted exactly one collector. That collector's
receipt is `run=20260819T183649887588Z-b72198c4d5344bba/receipt.json`
(`sha256:8100bf8cccc02afa88124c05a731ae53113f99075761c5fbe8bb657a3416e832`),
which is hash-bound as `deferred` with QQQ/NAS `auth_rejected` and SPY/AMS
`token_request_not_due` target states. It exposes only the daily market-data
route; all non-market routes are false and collector network use is
`not_recorded` rather than inferred.

The external cache/index reattach to the receipt's changed identities, while
the aggregate remains seven common sessions and two seven-row streams. The v4
prepare subphase is absent because this is not a matching commit failure. Do
not retry the daily collector from this outcome. It changes no causal timing,
provider-finality, model, Research, Execution, Paper, PnL, or live fact. The
next bounded package isolates the KIS Paper authentication path without a
market-data, account, order, or live call.

### Authentication Capability Outcome

Claude returned `supported-with-limits`: the non-reserving due check avoids
ordinary configuration reads, while a later atomic transport claim can still
lose a cross-worker race after the Paper app values are held only in process
memory. The source/fixture contract verifies that a loss makes no token request
and emits no credential, token, raw body, or dynamic exception text. The one
allowed token-only result is
`data/kis-paper-daily-pair-forward-v1/kis-paper-auth-capability-probe-v1/auth-capability-20260819T190601865051Z/receipt.json`
(`sha256:d07e12f8ca521ca32cc00a4a0f81625ad5b503fa0505bad026969aca95db8261`).
Its recomputed hash matches and its source-safe outcome is `authenticated`,
with no reason and only the 2026-08-19T19:00Z bucket retained. The receipt
records `paper_only` and `token_only`; market-data, account, position,
open-order, quote, order, live, credential-write, token-retention, and raw-body
retention are false.

This is one virtual-host token endpoint capability fact, not a daily-price
result or an eligibility promotion. Preserve the v4 daily receipt unchanged.
The next package runs the existing networkless Paper configuration/gate
readiness path and, only on its matching ready result, one existing D1
collector. It must not wait in the foreground or retry either call.

### V5 Readiness And One-Shot Outcome

The networkless readiness receipt
`run=20260819T191313847774Z-fefb0b409c2c4366/receipt.json`
(`sha256:f1d833bdf8aa775919f1793d2025ab2b530d251c13e3da22eb81a70a2c6ba7ab`)
recomputed as matching `ready/aggregate_ready`. It validated only the named
Paper configuration and recorded `token_request_due: true`,
`rate_gate_deferred: false`, no network request, no cache write, and no account,
order, or live route. Claude's `supported-with-limits` review requires the
individual gate fields and current host ownership to be checked before dispatch;
the collector's atomic gate is still decisive.

One collector then wrote
`run=20260819T191401404530Z-df12344aeec246ec/receipt.json`
(`sha256:a10e42f5a44753c67bf483414005d98b5171341998926b10a2a5f9dc85100910`)
as `unavailable/collector_unavailable` at
`commit/cache_contract/cache_prepare/incoming_merge`. The receipt has no cache
payload and retains only the daily-market route with every non-market route
false. The verified current cache/index identities, seven common sessions, and
per-target aggregate states match the preceding v4 deferred cache exactly. Do
not retry this collector. `incoming_merge` is a source region, not a direct
cause; duplicate conflicting overlap is only the source-inspection candidate.
The next source/fixture-only package must establish a revision-preserving merge
policy before another collector invocation.

### Forward-Cache Overlap Reconciliation

The source/fixture-only reconciliation policy is now fixed. Canonically equal
replayed rows are idempotent. A different row for a retained session never
overwrites that retained row: it records only the fixed
`daily_retained_revision_conflict` category and aggregate count, leaves that
target `input_unavailable`, and keeps the quarantine on later ordinary
collections. An unseen session may append only when it is strictly later than
the target's retained coverage end; an unseen interior/older session or a
conflict within one incoming payload remains a structural cache-contract error.
The causal D1 reader rejects every cache whose target is not `ready`, so a
quarantined target cannot reach Research or Execution. No raw row values or
value-derived diagnostic hash enter source-safe payloads. A future external
recovery must be a separately declared target-scoped re-fetch, not an automatic
quarantine clear.

### Post-Reconciliation Observation

The completed post-policy preflight was `collection_required`, followed by one
and only one fixed-pair collector. Its source-safe receipt is `partial/resume`
with two accepted pages, two retained-revision conflicts, two quarantined
targets, and eighteen common sessions. Both targets remain
`input_unavailable/daily_retained_revision_conflict`. The offline causal reader
then returned `input_unavailable` for source-pair identity and the existing
clock, availability, and finality gaps. This is a cache-mechanics observation,
not an independent reference, automatic clearance, causal input, model result,
or Paper/Execution permission. The direct runner now resolves an omitted
`ProjectRoot` after parameter binding; installed task actions already pass it
explicitly.

The completed package passed its focused 48-test group and the full authority
suite as `3218 passed, 19 skipped` in 42m13s, plus Ruff, both credential-free
Compose parses, and `git diff --check`. Verification made no external, KIS,
broker, credential, or scheduler call.

### Isolated V2 Fresh Cache

The v1 cache remains immutable/quarantined. The v2 cache is a separate
`QQQ/NAS` + `SPY/AMS` lineage at:

```text
D:\market_data\us_equities\kis_paper_private\daily-qqq-spy-forward\v2
```

Use its dedicated profile only. Its preflight is network-disabled and has no
KIS credentials; the collector has only the virtual-Paper daily-market-data
credentials and no account, position, quote, order, or live route:

```powershell
docker compose --env-file .env.example --profile kis-paper-daily-pair-forward-v2 run --rm --no-deps --pull never kis-paper-daily-pair-forward-v2-preflight
docker compose --profile kis-paper-daily-pair-forward-v2 run --rm --no-deps --pull never kis-paper-daily-pair-forward-v2
```

The 2026-08-20 bootstrap preflight was `collection_required`
(`sha256:9aaee83455c9a93906ff534a46d28457bd6aeb125b3f0bf251dc6a6bf4a1d976`),
the one collector was `ready`
(`sha256:0db2b9fa0dd1b475f971fee33009ed576e03c877fb0e63d19a004db4a3a95d49`),
and a separate network-disabled preflight reattached `cache_current`
(`sha256:d91a68988a3ef248c4ea2c752b27e4ec3c7f53746dd47a06592dcb4e15e6835a`).
The cache has 18 common sessions, but raw rows remain only under the external
cache root. This is not point-in-time availability, provider finality,
corporate-action, model, GPU, Execution, Paper-consumer, or live evidence.
Never copy, relabel, clear, or use v2 to clear the v1 quarantine.

## KIS Daily Event Sidecar

The qualified QQQ/SPY event-only snapshot is external and immutable:

```text
D:\market_data\us_equities\kis_paper_private\daily-corporate-actions\snapshot=2026-07-24-qqq-spy-tiingo-events-v1
```

It contains normalized event date/kind/value records plus source and coverage
hashes, not Tiingo quote rows or response bytes. Its paired price-free
research receipt is at:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json
```

To inspect only the pinned local KIS QQQ/SPY range, with no credential or
network access:

```powershell
uv run python scripts\collect_kis_daily_corporate_action_sidecar.py
```

`--execute` is the narrow Tiingo collection path. It reads only the approved
`TIINGO_API_TOKEN` through the strict local loader, makes one standard-EOD
request each for QQQ and SPY, and refuses incomplete session coverage. Use it
only for a new explicit immutable `snapshot=` destination; do not overwrite or
re-fetch the pinned snapshot merely to re-run Research. The event sidecar is
retrospective price-return plumbing only. Before a daily baseline, the next
offline audit must bind the source hashes, audit every event boundary, and use
a conservative `+-1` KIS-session mask. It never enables a model, GPU run,
total-return claim, KIS Paper action, or live behavior.

### Qualified Event-Boundary Audit

The resulting offline audit is immutable and external:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json
```

Its content hash is
`sha256:3d97b26b5e8e422cb2b4bcf262fbd1be887e44d7e43afdd9e2b5d689f805a46c`.
It binds the `+-1` KIS-session mask
`sha256:921c61b8abf822b0aee71b66b43c37875cb581e95bf7a1563b053880c087d429`
and the fixed chronological partitions
`sha256:b82ed4022237929febde187651cb31e74740b311faa85c850967c617ac8dcfdb`.
The audit qualified QQQ (78 events, 316 masked pairs) and SPY (76 events, 307
masked pairs) with zero unmasked residuals at the fixed 20% screen. It contains
no raw prices or per-pair returns.

Verify the immutable artifact without a credential, network, KIS, or Tiingo
call:

```powershell
Get-FileHash -Algorithm SHA256 `
  D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json
```

Do not rerun the default audit destination: immutable output intentionally
refuses overwrites. A later changed source scope requires a fresh explicit
destination and remains a new research contract. This audit is retrospective
price-return integrity evidence only; it does not make a model, total-return
claim, point-in-time input, KIS Paper action, or live behavior eligible.

### Joint QQQ/SPY Event Window

The active schema-v2 joint event-window contract is external and immutable:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json
```

It binds the price-free event sidecar to the exact QQQ/SPY catalog, excludes
either-symbol events over each real `t-20..t+2` dependency span, and freezes
three expanding `3783 / 22 / 252` folds with a 151-session untouched tail. The
active artifact hash is
`sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814`.
It is `candidate` only: `model_execution_eligible` is false and its review
status is `review_unavailable` because the required Claude CLI OAuth session
was expired.

To create a new immutable candidate only after its pinned input scope changes,
run the offline local reattestation command. It reads no `.env`, credentials,
KIS, Tiingo, or broker route:

```powershell
uv run python scripts\prepare_kis_daily_joint_event_window_contract.py `
  --model-execution-review review_unavailable
```

Do not overwrite the v2 artifact. The next consumer must rebuild and compare
its contract identity, then handle one fold and its exact eligibility identity
at a time; it must not treat the three expanding folds as one generic
`CampaignContract`, train, replay, select a model, or produce a Paper decision.

#### Reattested Expanding-1 Input

The first and only active fold-local input is external and immutable:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-fold-input-expanding-1-v1.json
```

Its artifact hash is
`sha256:a15c26b6ce8f9c8c1e204cd8300b46241e2e7d894548666c73d32d030f790f0b`
and its fold-input identity is
`sha256:b019c7e9a10eb2add48bbaa815c046a9b216ca9069c4ca8e4f836bc91085a1db`.
It binds the active parent hash and contract identity plus exact sparse
`expanding-1` eligibility counts of 2,345 development and 146 validation
decisions. It retains no price or return values and remains
`model_execution_eligible: false` with `review_unavailable`.

To rebuild the parent locally and write this one index-only fold input when its
destination does not already exist, run:

```powershell
uv run python scripts\prepare_kis_daily_joint_event_window_fold_input.py `
  --fold-id expanding-1
```

The command reads only the pinned local catalog, sidecar, audit, and parent
artifact. It does not read `.env`, call KIS or Tiingo, invoke a broker, train,
replay, or create a Paper decision. A later D1 materializer must consume these
exact sparse indices, not infer a continuous eligible range.

### Reattested D1 Materializer

The first source-safe `expanding-1` validation receipt is external at:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-materializer-expanding-1-validation-first-v1.json
```

Its content hash is
`sha256:247142b6f84f7e0ce88e538ea6832c083be2d1b29b66b079c99a2ad6d6b2f748`.
It records only verified lineage, sparse-count/identity, timestamp and index
geometry, and non-executable scope. It never stores bars, prices, returns,
labels, predictions, checkpoints, credentials, or orders.

To materialize another already verified sparse window, give the offline command
a new external destination; immutable receipts are never overwritten:

```powershell
uv run python scripts\prepare_kis_daily_joint_event_d1_materializer.py `
  --phase validation `
  --destination D:\thericher-v2\model-artifacts\research-contracts\<new-receipt>.json
```

The command reads only pinned local market data and immutable contract inputs.
It does not read `.env`, call KIS or Tiingo, invoke a broker, train, replay, or
create a model/Paper decision.

### Reattested D1 Target/Cost Semantics

The active source-safe target/cost receipt is external at:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-target-cost-expanding-1-validation-first-v2.json
```

Its content hash is
`sha256:90beea4c501a946dd5502a2b0eb4a06b10a0ef36ed5f70f29c595a17dd6d7486`.
It binds the verified materializer to QQQ `t+1/t+2` long-versus-flat semantics,
one basis point fee and two basis points slippage per fill, `0.0001`
`ROUND_HALF_EVEN` quantization, and Decimal precision 34. It persists only
identities, formula parameters, timestamps, and index geometry, never opens,
returns, labels, predictions, checkpoints, credentials, orders, or PnL.

The earlier v1 receipt remains immutable evidence but is not active: independent
Validation found its intermediate Decimal arithmetic could vary with the ambient
precision. Use only v2 for any later candidate-only consumer.

To write another source-safe semantic receipt, use a new external destination:

```powershell
uv run python scripts\prepare_kis_daily_joint_event_d1_target_cost.py `
  --phase validation `
  --destination D:\thericher-v2\model-artifacts\research-contracts\<new-target-cost-receipt>.json
```

The command reattests only local pinned inputs. It does not read `.env`, call
KIS or Tiingo, invoke a broker, train, replay, or create a Paper decision.

### Independent Expanding-2 Contract

The completed second-fold artifacts remain external and immutable:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-fold-input-expanding-2-v1.json
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-materializer-expanding-2-validation-first-v1.json
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-target-cost-expanding-2-validation-first-v2.json
```

Their hashes are `sha256:79723a...c9305`, `sha256:e489f...9709f`, and
`sha256:4de77...941da`. The fold input is `2511 / 128` sparse
development/validation decisions and the validation receipt proves only
`4079 -> 4080..4099 -> 4100/4101` (`t-20..t+2`) geometry. The fixed target
semantics remain v2 with Decimal precision 34.

For a first immutable write to a different verified single-fold destination,
explicitly pass `--fold-id expanding-2` to each preceding materializer and
target/cost command. The default artifact names above intentionally refuse a
second write with `FileExistsError`; preserve that file and reattest its hash
and lineage instead of overwriting it. In Docker, use the same
`/app/model_artifacts` and `/app/market_data` arguments shown below.

### Independent Expanding-3 Contract

The completed third-fold artifacts remain external and immutable:

```text
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-fold-input-expanding-3-v1.json
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-materializer-expanding-3-validation-first-v1.json
D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-target-cost-expanding-3-validation-first-v2.json
```

Their hashes are `sha256:40d6c992...7128fc`, `sha256:e0b90a50...c147c8`, and
`sha256:4c389d43...961560`. The fold input binds `2671 / 145` sparse
development/validation decisions. Its validation receipt proves only
`4366 -> 4367..4386 -> 4387/4388` (`t-20..t+2`) geometry, before the final
151-session tail beginning at index `4605`. The target semantics remain v2
with Decimal precision 34.

Use `--fold-id expanding-3` explicitly for any local or Docker reattestation.
The existing receipt names are immutable: an attempted second write must fail
with `FileExistsError`, which confirms the external mount and must not be
worked around by overwrite or deletion.

### Candidate-Only D1 Sequence Screen

The completed first-fold CPU and CUDA evidence is external only:

```text
D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cpu-smoke-20260727-r1
D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cuda-screen-20260727-r1
```

Their source-safe result identities are `sha256:81e486...247f5` and
`sha256:8c4e49...32068`. Each uses the reattested `expanding-1` materializer,
the v2 target/cost identity, exactly 2,345 development and 146 validation
decisions, a development-only normalizer, one fixed linear classifier, and one
fixed compact GRU. It stores only lineage hashes, counts, fixed specifications,
and aggregate classification metrics. It stores no rows, targets, predictions,
model weights, replay events, PnL, credentials, accounts, orders, or fills.

The completed independent `expanding-2` CPU and CUDA evidence is at:

```text
D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cpu-smoke-expanding-2-20260727-r1
D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cuda-screen-expanding-2-20260727-r1
```

Its result identities are `sha256:96a29b18...a7106e` and
`sha256:233629de...2826e`. Each is an aggregate-only candidate screen over the
explicit `2511 / 128` E2 split with development-only normalization. Neither
result selects a model or permits replay, PnL, Paper, or live behavior.

The completed independent `expanding-3` CPU and CUDA evidence is at:

```text
D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cpu-smoke-expanding-3-20260727-r1
D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cuda-screen-expanding-3-20260727-r1
```

Its result identities are `sha256:438b720b...c20e87` and
`sha256:f3ad3199...03922a`. Each is an aggregate-only candidate screen over
the explicit `2671 / 145` E3 split with development-only normalization. Neither
result selects a model, changes a threshold, forms an ensemble, or permits
replay, PnL, Paper, or live behavior.

Use Docker's network-disabled research profile for any new immutable attempt:

```powershell
docker compose --env-file .env.example --profile research run --rm --no-deps `
  research python scripts/run_kis_daily_joint_event_d1_sequence_screen.py `
  --mode cpu-smoke --fold-id <explicit-fold-id> --run-label <new-label> `
  --artifact-root /app/model_artifacts --market-data-root /app/market_data
```

Only after a completed CPU smoke, a bounded CUDA attempt may replace
`--mode cpu-smoke` with `--mode cuda-screen` and use a distinct label. This is
classification evidence only. Do not use either summary to tune, select,
ensemble, replay, promote, or derive a Paper decision. In Docker, only the
explicit `/app/market_data` and `/app/model_artifacts` bind mounts count as
external storage; the host paths remain `D:\market_data` and
`D:\thericher-v2\model-artifacts`. The runner recognizes only the explicit
`expanding-1`, `expanding-2`, and `expanding-3` pin profiles; pass the fold
explicitly even though the historical E1 default remains available.

### Fixed D1 Cross-Fold Falsification

The fixed cross-fold verifier is an offline, aggregate-only consumer of the
six exact E1/E2/E3 CPU/CUDA summary/precommit pairs. It checks each input's
canonical bytes, external containment, hash, fold lineage, split geometry,
development-only normalizer, candidate specification, and source-safe scope
before comparing anything. E1's legacy summary shape is accepted only through
its exact pinned pair. It never infers a fold from counts or missing fields.

Run it with an unused external artifact label:

```powershell
uv run --extra dev python scripts\run_kis_daily_joint_event_d1_crossfold_falsification.py `
  --run-label <unique-label> `
  --artifact-root D:\thericher-v2\model-artifacts
```

It writes exactly `precommit.json` and `summary.json` beneath
`D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-crossfold-falsification-v1\<unique-label>`.
It keeps every mode and expanding fold separate and compares a frozen candidate
only with the named fold's class-majority count. The only conclusions are
`falsified` and `inconclusive`; it never pools overlapping folds, emits a
winner/ranking/score, or writes rows, labels, predictions, weights, replay,
PnL, credential, KIS, broker, account, order, or Paper data.

The completed `crossfold-falsification-20260727-r1` run has precommit identity
`sha256:991a344522cdd9a51af370e8a8ec9e9b1335cf8f301b8bb9af4f490c325b2330`
and result identity
`sha256:1bbbc7ea47ceb6ce4d2b75409d020a1486bb4a6a6ea071ce4246852cca18bc5d`.
All twelve fixed candidate/mode/fold observations are falsified under this one
strict fold-local rule. That fact rejects only the fixed pair; it is not a
general architecture conclusion, selection, profitability result, or Paper
trading input.

### Masked D1 Naive Validation

Run the completed fixed control package only against the pinned audit and KIS
cache; it has no credential, Tiingo, KIS, broker, GPU, or model path:

```powershell
uv run python scripts\run_kis_daily_masked_naive_validation.py
```

The immutable aggregate output is:

```text
D:\thericher-v2\model-artifacts\kis-daily-masked-naive-validation\kis-daily-masked-naive-validation-v1.json
```

Its current content hash is
`sha256:e2ad842d852fe647f7de6367955f7a48f27f08508e32816f98f3c473ffcffbf6`.
The command fully attests source bytes before it materializes only the prefix
through embargo, runs `flat`, `always_long`, and
`previous_session_direction` through `source: local_paper`, replay-checks the
temporary fills, then deletes raw event logs. The untouched tail remains
unmaterialized. This is an unadjusted retrospective plumbing result, never a
model, alpha, profitability, total-return, point-in-time, KIS Paper, or live
claim. A changed input must use a new explicit artifact identity rather than
overwriting this receipt.

## KIS Intraday Backfill

The active private 1m cache is at:

```text
D:\market_data\us_equities\kis_paper_private\intraday\v1\index.json
```

Run a bounded cursor-resuming cycle whenever fresh intraday coverage is useful:

```powershell
uv run python scripts\backfill_kis_paper_private_intraday.py --execute --pages-per-target 2
```

The Docker-equivalent path injects only the two Paper app values and mounts the
external market-data root outside `/app`:

```powershell
docker compose --profile kis-paper-intraday-cache run --rm --no-deps kis-paper-intraday-cache
```

It uses only the Paper-only market-data client for `QQQ/NAS` and `SPY/AMS`,
writes immutable raw provider-field rows and manifests under `D:`, then moves a
cursor atomically. It never reads account or live values, places an order, or
writes market data into Git. A failed or empty call records no data-bearing
chunk and does not reserve or disable its next correctly scoped collection.

For this KIS minute endpoint, response header `tr_cont` is the pagination
authority: `M` or `F` continues with `NEXT=1` and a `KEYB` derived from the
oldest validated bar. Treat `output1.next` and `more` as provider metadata, not
as cursor control. This keeps a terminal page from becoming a repeated
`minute_cursor_invalid` recovery loop.

### Historical Capability Probe

Use this only to remeasure the documented normal-start behavior, not to seed an
undocumented historical cursor:

```powershell
uv run python scripts\backfill_kis_paper_private_intraday.py --execute --mode historical-probe --pages-per-target 2
```

The probe starts with a blank `KEYB`, derives a continuation only from a valid
response, and writes to the sibling
`D:\market_data\us_equities\kis_paper_private\intraday-historical-probe\v1`
root. It never advances the ordinary historical or prospective-head cursor and
never calls an account, order, or live endpoint. A terminal first page is a
bounded capability observation, not authority to invent a timestamp seed or a
claim about other KIS endpoints.

This existing probe qualifies normal-start/continuation behavior, not the
general request ceiling. A throughput probe must also bound its request count
and elapsed time, preserve the same source-safe output rules, and report the
specific fact that retains or recalibrates a future capture worker.

### Bounded QQQ Minute Capability Probe

Use the dedicated source-safe probe when the question is the current terminal
head behavior and in-memory Paper-token reuse, rather than cache backfill:

```powershell
uv run python scripts\probe_kis_paper_minute_capability.py --execute --max-pages 3
```

It uses only the KIS Paper market-data token and `QQQ/NAS` minute route. It
does not call account, position, order, or live endpoints. It retains no raw
rows; instead it atomically writes an allowlisted result below
`D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe`.
The current probe can repeat a terminal head with the same in-memory client to
measure token reuse, but it cannot establish historical reach, a faster request
ceiling, or a complete 390-minute session. Preserve the existing request gate
and cooldown while interpreting its result.

`data.kis_paper_intraday` is the offline consumer: it verifies every index,
manifest, and raw hash; maps KIS Korea timestamp fields to UTC; and delegates
5m, 10m, 1h, and 3h aggregation to an explicit `SessionWindow`. The first
observed pages include extended-session data, so do not treat the cache as a
regular-session strategy dataset until Data records that source semantics.

### Prospective Head Collection

Use the separate head cache when the goal is fresh in-session observations
rather than historical cursor continuation:

```powershell
uv run python scripts\backfill_kis_paper_private_intraday.py --execute --mode session-capture --pages-per-target 4
docker compose --profile kis-paper-intraday-head run --rm --no-deps kis-paper-intraday-head
```

Head snapshots live below the sibling `intraday-head` cache root and never
advance the historical backfill cursor. It is a Data-local source sampler, not
a company-wide wait. The Windows Scheduled Task
`thericher-kis-paper-intraday-head` currently runs Tuesday through Saturday at
00:29, 02:28, 04:24, and 06:20 KST according to its source-safe static Task
facts. Do not infer a retained-cache chunk from any one trigger. Each data
collector invocation keeps the four-page-per-target normal cap. The existing
regular-weekday post-close invocation (16:20--20:00 Eastern) is the one bounded
exception: it uses eight pages per target to test whether the retained head can
cover a full session. It adds no Task, route, rate change, retry loop, or
automatic escalation; a still-short receipt closes that cap test. The capture
coverage selector, not the schedule, still requires an exact 390-minute
declared QQQ session before it can call a whole-session observation complete.
That rule does not apply to the bounded runtime selector: it accepts one
verified, same-session, contiguous 90 completed-minute QQQ/NAS window ending
on a 10-minute boundary and emits a precise stale/missing/gapped fact
otherwise. Historical Research uses separately qualified inputs and does not
wait for this task.

If a complete fresh head page disagrees with an active retained head snapshot,
the installed `head` and `session-capture` modes may write an index-only
quarantine marker for the exact old `chunk_key`, manifest hash, and raw hash.
The marker leaves the immutable D: snapshot bytes untouched, excludes that
entry from active loader/coverage input, and prevents only that exact orphan
from being reactivated. The conflicting fresh response remains rejected in
that run; a later independently fetched head page must be clean before it is
admitted. This is deliberately unavailable to cursor-backed historical
backfill: a retained snapshot must carry persisted `collection_scope: head`.
New historical snapshots carry `historical`; legacy snapshots without a scope
remain strict-reject-only. A quarantine marker with a missing or invalid exact
chunk, manifest, or raw hash makes the index invalid before orphan recovery.
No manual index edit or latest-wins rule is permitted.

The intraday-head task retains `StartWhenAvailable` from its Data recovery
ownership, so a missed collection can resume after the interactive user becomes
available without creating another task. Its chained prospective consumers still
require their own current 90-minute window, regular-session time, receipt, and
fresh account/quote facts; a late resume therefore becomes a source-safe
no-intent unless those exact call-time conditions remain true. The head task
allows battery start/continuation, keeps `IgnoreNew`, and has a 90-minute task
limit, below its shortest 109-minute trigger gap. Do not manually start a
duplicate run to compensate for a missed window; inspect the task result and
use the existing owned recovery path.

After a terminal dispatch receipt is written, reattach only the task-owned
current pointer and its exact immutable receipt with this host-only command:

```powershell
uv run python scripts/project_kis_paper_intraday_head_schedule_receipt.py
```

It reads no credentials and makes no KIS, Docker, network, or market-data call.
It never scans for a latest receipt: a malformed/link/reparse-point pointer,
reserved run ID, Git-local artifact root, missing receipt, hash mismatch, or
terminal-category mismatch returns only `unavailable`.

### Intraday Capture Topology And Invocation Markers

To inspect the retained QQQ capture topology without opening raw minute rows,
credentials, Docker, or KIS, run:

```powershell
.\scripts\inspect_kis_paper_intraday_capture_topology.ps1
```

The audit reads only the external index/manifest metadata plus source-safe
static facts for the one existing Task. A reported
`unretained_or_unstarted_slots` value means exactly that: it does not prove a
missed Scheduler trigger, a provider limitation, or a collector failure.

To compare the installed intraday-head Task's source-safe static shape with the
checked-in first `session-capture` runner and credential-free Compose route,
run:

```powershell
.\scripts\inspect_kis_paper_intraday_head_static_contract.ps1
```

It reads only Task Scheduler metadata plus checked-in source and writes one
external source-safe categorical receipt. It does not read credentials, use a
current/latest marker, invoke a Task, Docker, KIS, collector, broker, or
Scheduler, or retain action command text, roots, task output, market rows, or
private runtime state. `matches` covers only enabled/action/triggers/settings
and the first `session-capture` route; it is not evidence that a task ran or
that Docker/container entry, provider behavior, session completeness, finality,
or a model input is valid. `Running` is observational rather than a mismatch.

The existing dispatcher writes a diagnostic-only immutable `started` marker
before collection and a hash-bound `terminal` marker after its existing
schedule receipt. The terminal preserves both the schedule-observed timestamp
and the later dispatcher-completion timestamp, so the reader can distinguish
the exact boundary without inventing a Scheduler or collector outcome. To
inspect only the validated current marker pointer, run:

```powershell
uv run python scripts\project_kis_paper_intraday_head_invocation_receipt.py
```

`unavailable` means no valid current marker can be reattached; it is not a
success, busy, or failure inference. The marker contains only opaque run and
timestamp/outcome categories under
`D:\thericher-v2\model-artifacts\execution\kis-paper-intraday-head-invocation-v1`.
It is assumed-honest-host provenance, not cryptographic proof that Task
Scheduler started the process. Do not manually invoke the task, collector,
Docker service, KIS, or Scheduler to manufacture this evidence.

To bind the current marker to the exact source-safe schedule terminal and
metadata-only topology, while reading only static Task facts, run:

```powershell
.\scripts\project_kis_paper_intraday_invocation_reattachment.ps1
```

The result is only `marker_unavailable`, `start_only`, `terminal_unavailable`,
`marker_not_later`, `collector_nonzero`, `retained_partial`, or
`complete_session`. It recomputes
the marker and schedule bindings, never searches for a newest artifact, and
does not treat topology metadata as an exact run binding. Its evidence pointers
are exact but relative to the external artifact root, never local absolute
paths. A marker remains assumed-honest-host provenance, not cryptographic
Scheduler-origin proof.

When a bounded objective needs a marker later than a known terminal, pass both
opaque baseline facts to the same offline reader:

```powershell
.\scripts\project_kis_paper_intraday_invocation_reattachment.ps1 `
  -BaselineRunId <opaque-run-id> `
  -BaselineCompletedAt <UTC-ISO-8601-timestamp>
```

`marker_not_later` means the current, otherwise bound pointer repeats that run
or does not complete strictly after its baseline. It is not a second binding,
a failure, or a reason to alter Task, collection, KIS, Docker, consumer, or
Paper behavior.

`collector_nonzero` means only that the dispatcher-recorded collection service
stage returned nonzero for that exact bound task path. It does not identify a
collector-process, Docker, provider, persistence, rate, or timing cause. Do not
read or retain command output or exception text as a shortcut: any future
localization receipt must use a closed allowlist of categorical codes and keep
the original stage exit separately intact.

For an already bound terminal, `collection_outcome` is written only after the
runner's `Invoke-HeadProfileService` call has returned a host
`docker.exe compose run` exit code. This proves neither Docker/container entry
nor collector, KIS, or provider behavior. Do not add a duplicate pre/post
marker merely to restate that returned boundary; a direct data-only collector
probe is the narrower way to separate collector/provider behavior from the
task-owned host path.

Future terminal markers may carry only `reason_unavailable`,
`dispatcher_config`, or `collector_provider`. The dispatcher derives that field
in memory from exactly one existing structured collector error payload; malformed,
multiple, unknown, or free-text-looking output remains `reason_unavailable` and
is never retained. A zero collection exit must retain `reason_unavailable`. Old
immutable markers are read as `reason_unavailable` without byte changes. This
category is diagnostic evidence only: it does not authorize a Task, paging,
pace, Docker, KIS, consumer, Paper, or recovery behavior change.

The reattachment projection also reports `collection_outcome` and
`failure_category_is_comparable`. The latter is true only when the exact later
terminal is both `collector_nonzero` and `collection_outcome: nonzero`.
`retained_partial` or `complete_session` may preserve the compatibility-default
`reason_unavailable` after a successful collection stage; that field is
noncomparable and is not a failure-category binding, match, or divergence.

One comparable post-writer category binding is not a recovery premise. Before
proposing a category-based recovery, reattach two later independently
hash-validated task-owned *nonzero* bindings with the same comparable category
and obtain a fresh Claude falsification-first verdict. A different comparable
later category records divergence only and still authorizes no behavior change.

The reader also accepts a terminal-embedded SHA-256 binding for one fixed,
external, source-safe causal-condition attestation. That optional receipt must
match the terminal's run, capture, availability, and pair identities and name
the clock authority, `America/New_York` DST/session rule, completed M1
geometry, chronological boundary, decision-time availability, and provider
finality. The currently installed task does not write or bind this receipt, so
the current projection remains `not_recorded`/`input_unavailable`; do not create
or attach one manually. This is an internal default-deny reconstruction rule,
not cryptographic proof of provider origin.

To rebuild and update only an already installed named task after a local code
change, use the scoped installer selector:

```powershell
.\scripts\install_kis_paper_schedules.ps1 `
  -ScheduleName thericher-kis-paper-intraday-head `
  -RequireExisting
```

It validates the name before invoking Docker, rebuilds only the selected task's
local services, and updates only that task definition; it does not run the
service. `-RequireExisting` fails before the build when a selected task is not
already registered. Use `-WhatIf` when reviewing the scope. Leaving out
`-ScheduleName` retains the installer's all-task behavior.

For `thericher-kis-paper-intraday-head`, the installer's image list is tested
to match the dispatcher's literal service set exactly. Keep that inventory in
sync with the existing dispatcher so a scheduled task cannot fall back to a
stale local image while still using `--pull never`.

The same named task dispatches the credential-bearing data collector, one
virtual-only `kis-paper-prospective-qqq-session`, the offline
`kis-paper-prospective-qqq-validation`, an optional older pair-bound
`kis-paper-intraday-observation`, and a network-disabled terminal receipt
writer. The QQQ session owns the only local prospective recomputation and
`local_paper` replay; the terminal receipt records that stage as `embedded`.
It reads KIS Paper credentials, account facts, or a QQQ quote only after a
current `enter` or `exit` receipt; otherwise it exits as no-intent. The older
observer is independently offline and starts only after Data writes both
required pair-evidence files. The Validation service receives the exact QQQ
execution-session ID, re-loads the local cache at the recorded timestamp, and
writes an external source-safe validation artifact. It has no network or KIS
environment values and cannot modify replay or broker state. The terminal
writer receives only allowlisted stage exit/status values and safe session IDs;
it persists one external source-safe dispatch receipt. The dispatcher preserves
a nonzero collector code. Once collection succeeds, an unavailable or nonzero
required embedded/session/validator stage exits `20`, and an unavailable
receipt writer exits `21`; a fully validated `no_intent` still exits `0`. The
older observer remains optional for this QQQ cycle. These are technical
recovery signals, never a Paper authority, data-quality, or manual approval
gate.

The current QQQ runtime/Paper route uses one Data-owned two-minute completed-bar
deadline with an inclusive exact-boundary rule. It records the completed-window
end, route observation time, lag category, and selected budget in a source-safe
runtime projection. Before creating the KIS Paper account client it rechecks
that deadline; immediately before `submit_limit`, the existing canary lock
evaluates the same deadline together with the regular-session predicate. This
deadline does not constrain offline Research campaigns that deliberately pass a
separate campaign-local age. The offline validator writes new results under the
immutable `runtime-freshness-v5` validation namespace, so it can reattach an
older receipt without overwriting it. A current QQQ runtime receipt carries an
exact `observed_provisional` input grade with provider availability/finality
`not_observed`, terminal-state support `unqualified`, and PnL `not_observed`.
The offline validator recomputes that grade from the retained window and
rejects a missing or altered current-v5 grade; older receipts remain replayable
only under their original scope.

### Bounded Session Capture

Use the measured capture path when one current head invocation needs an
immutable, source-safe 390-minute coverage receipt:

```powershell
uv run python scripts\backfill_kis_paper_private_intraday.py --execute --mode session-capture --pages-per-target 4
```

It uses the existing `intraday-head` cache, one in-memory KIS Paper
market-data client/token, the same worker lock, request-start gate, cooldown,
strict conflict rule, and `tr_cont` continuation behavior. It writes raw
provider rows and cache state only under `D:\market_data`, then writes an
allowlisted capture receipt under that external head cache. Its console result
contains no receipt path, provider row, price, credential, account, or order
data.

The receipt's QQQ capture status says whether its bounded transport attempt
completed; it is not a regular-session qualification. Only coverage of exactly
390 regular-session minutes qualifies a session. A terminal or extended-session
page can therefore report a completed capture attempt and zero qualified
minutes, which must remain Data evidence rather than a Research input. SPY is
recorded as a companion target, but an independent SPY failure cannot erase the
scoped QQQ capture result.

On 2026-08-19, one Data-owned **direct host** invocation of this exact bounded
path completed `QQQ/NAS` and `SPY/AMS` with the four-page cap. Its unbound,
source-safe capture receipt is
`D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T130238145868Z-50e04e46fdb2e4e0.json`
(`sha256:50e04e46fdb2e4e0ceb65673066751fdb37bfaa5b53b8007f4ddb8f20316354a`).
That proves only the direct host collector path completed this scope; it is not
Windows Task/Scheduler or Docker/container provenance, a complete session,
provider finality, a model input, or an execution consumer.

The first later direct Compose-service attempt did **not** exercise the token
transport: its exact safe receipt
`D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T131812782029Z-0caa1e559078804d.json`
(`sha256:0caa1e559078804dc2d269a9aa2abf708e9f169783f775378fdf0d17250e2bcc`)
is `incomplete` with both targets `rejected/token_request_not_due`. The shared
token-start gate had a separate recent reservation and rejected the attempt
before a token POST; it identifies no owner and proves neither a Docker nor a
KIS/provider failure. Treat its due time as the owning control's `next_due`,
not a foreground sleep. A distinct goal may make one fresh atomic attempt only
after a non-mutating due precheck; never retry this exact attempt.

The next due-gate Compose attempt reached the existing cache-conflict branch.
Its safe receipt
`D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T133017088958Z-ed596cfe5f8dc959.json`
(`sha256:ed596cfe5f8dc95977c961d48927e9266ba6353e82578f2a2f76b26acc1b80e4`)
records `minute_duplicate_conflict` from `retained_cache` with `quarantined`
disposition for both fixed targets. That means the installed path preserved the
immutable raw snapshot and excluded only conflicting active head entries; do
not inspect, edit, clear, or restore those bytes. It is neither provider
finality nor a complete-session claim. One later independently fetched clean
capture may test the existing recovery rule after the shared gate is due. If
the same retained-cache conflict recurs, close this exact recovery path rather
than adding a retry loop or a cache-rewrite rule.

That one later clean-capture attempt completed through the same direct Compose
service. The exact unbound receipt is
`D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T134229353199Z-c87d4ebfde0e7545.json`
(`sha256:c87d4ebfde0e7545e7907936c8eb506c1e3aa7514ef6d9ea86e9a36d7b4a522e`).
Its two fixed targets are `collected`, with no retained-cache conflict category.
The offline reattachment binds the filename timestamp and hash and confirms an
unbound `paper_only` market-data capture. It closes only this direct cache
recovery path, not Scheduler provenance, session completeness, finality, model
eligibility, or a downstream consumer.

The one existing `thericher-kis-paper-intraday-head` task invokes this same
capture mode before its bounded local and QQQ Paper consumers. It adds no new
Windows task, and its concurrency and collector exit authority stay unchanged.
The normal cap remains four pages per target; only the bounded post-close
window uses eight pages to measure full-session reach. An eligible 90-minute
runtime window may now produce a provisional
five-action receipt and a `local_paper` replay without waiting for a
whole-session observer. Only a separately current `enter` or `exit` receipt
can reach the existing virtual QQQ/NASD canary lifecycle; this is execution
learning, never a model or PnL claim. The older metadata-only preparation child
and pair-bound observer retain their original first-five scope.

A duplicate minute inside one candidate batch rejects that whole candidate,
including any earlier page from the same invocation: no snapshot is retained
and no cursor advances. An explicitly marked legacy candidate-batch partial is
kept only as audit evidence and is excluded from cache/session consumption. In
the generic `head` mode, the outer worker is `complete` only when it returns
one eligible result for both expected QQQ and SPY targets. In `session-capture`
mode, the source-safe QQQ capture status is deliberately separate from the
process exit, which still reflects whether the full collector cycle succeeded.
The existing QQQ-only preparation child may still run after its exact QQQ
result while the generic outer worker remains `incomplete`.

To compare head coverage without opening raw minute CSV files, prices, or
credentials, run:

```powershell
uv run python scripts\inspect_kis_intraday_head_coverage.py
```

It emits only QQQ regular-session minute counts, offset-based missing ranges,
continuation and overlap categories, index identity, and the scoped
preparation-input status. It does not write an artifact, call KIS, or create a
cache.

After a durable head collection whose exact `QQQ/NAS/1m` result is `collected`
or `recovered`, the same service makes one sequential metadata-only preparation
attempt. An independent SPY target failure keeps the overall worker
`incomplete`, but cannot delay the QQQ-only preparation input. It uses the fixed
`scheduled-head-v1` identity and the external model artifact mount only. The
child has no KIS/account/order/live environment and a ten-second containment
timeout. Its parent output exposes only `pending`, `prepared`, or a scoped
`preparation_unavailable` reason; it never exposes a path, raw row, price, or
credential. A pending or unavailable preparation does not change the completed
collection, cursor, or freshness projection. Once the first five complete QQQ
sessions exist, the preparation pair is external and reused only after
validation of the immutable first-five session/date and fingerprint identity.
This creates no model, GPU job, or Paper order.

For an offline KIS-cache replay after a complete session has been retained:

```powershell
uv run python scripts\run_kis_paper_intraday_local_paper_baseline.py --session-date 2026-07-21 --symbol QQQ
```

The command makes no network or credential access. It writes only a sanitized
local-paper summary under the external model-artifact root.

### Baseline Decision Receipt

Write or reattest the immutable receipt for the frozen KIS-native QQQ input:

```powershell
uv run python scripts\write_kis_paper_baseline_receipt.py
```

It reads the external cache offline, writes only safe receipt/no-intent evidence
under `D:\thericher-v2\model-artifacts\kis-paper-baseline-receipt`, and never
reads a credential, calls KIS, or emits raw bars/prices. An `unqualified` or
otherwise unavailable result is scoped to that receipt; retain the artifact and
continue independent KIS Paper, Data, and Research work.

### Frozen Historical KIS Daily CPU Baseline

Use the private daily cache for a bounded offline KIS-native replay:

```powershell
uv run python scripts\run_historical_kis_cpu_baseline.py `
  --symbol QQQ `
  --run-label qqq-daily-YYYYMMDD-r1
```

The runner loads only the qualified QQQ/SPY KIS-private-daily catalog, freezes
an 80/20 chronological development/descriptive-holdout split with one purge
session, and evaluates `always_long` and `previous_bar_direction`. A decision
uses a completed daily close, enters at the next daily open, exits at the
following daily open, and charges 1 bps fees plus 2 bps slippage. All replay
fills must remain `local_paper`. It writes its contract, work evidence, and
sanitized summary under
`D:\thericher-v2\model-artifacts\historical-kis-daily-cpu-baseline`.

Choose a new label after an interrupted run. The chronological holdout is
descriptive and unsealed: this command cannot select a model, claim
profitability, submit a Paper order, or read credentials/network data.

The 2026-08-19 QQQ and SPY reproductions used separate external labels and the
same 4,756-bar common-panel hash. Each completed the four fixed
development/chronological-holdout by baseline cells with `local_paper` fills.
No cell had positive after-cost PnL; this anchors a negative control rather
than a model-selection or profitability result. The contracts, replay work, and
sanitized summaries remain only under the external baseline artifact root.

### Frozen KIS Daily L2 Logistic Control

The fixed L2 logistic control reuses the same hash-pinned QQQ/SPY D1 catalog,
but fits pooled development labels only for 160 deterministic CPU steps and
replays its frozen validation against the three fixed local-paper comparators.
It does not read credentials, call KIS, use Docker or GPU, serialize raw rows,
or write model parameters into the repository.

The 2026-08-19 run label `20260819-kis-daily-l2-logistic-r1` completed beneath
`D:\thericher-v2\model-artifacts\kis-daily-l2-logistic-control-v1`. Its
precommit preceded fit and validation replay, validation labels were excluded
from fitting, and its two model plus six comparator cells retained only
`local_paper` fills. The after-cost QQQ/SPY model replays were `-109.2703` and
`-139.3587`, below the fixed previous-bar-direction controls. The external
precommit, parameter identity, and sanitized-summary hashes are
`sha256:60ac9f662014bc76067945befed7877a345099088f5e3defd4747eacf9dd3b9a`,
`sha256:7db2456aa6f0368008becd59d7d70b3580b2f0f5aeb0db4aafda5f858f3a8545`,
and `sha256:143f7ce60cc74fcac61cf004245730b78c0a34acf5e8003d326bd267c1492213`.
This is negative descriptive control evidence only: it selects no model,
creates no ensemble or GPU appointment, and cannot support a Paper or live
action.

### Frozen Chronological CPU Campaign

When Data has reattested exactly 20 complete regular 1m sessions for one KIS
symbol, run the first chronological naive comparison from the retained cache:

```powershell
uv run python scripts\run_kis_intraday_cpu_campaign.py `
  --symbol QQQ `
  --run-label qqq-YYYYMMDD-YYYYMMDD-r1 `
  --session-date YYYY-MM-DD `
  # repeat --session-date until exactly 20 ordered full regular sessions are supplied
```

The command remains offline after the cache load: it does not read credentials
or call KIS. It freezes a 10-development / 1-unused-session purge / 9-validation
split and runs `flat`, `always_long`, and `previous_bar_direction` through
`local_paper`. The external summary records only dataset/contract identities,
session dates, costed aggregate results, and replay hashes; raw bars, quotes,
account data, order identifiers, and secrets remain absent.

Use a new safe `--run-label` after an interrupted attempt. Existing external
evidence is immutable and never overwritten. This is recovery separation, not a
one-shot quota or an approval step.

### Intraday Feature Breadth And CUDA Smoke

The first QQQ feature breadth run used the same 20-session source with 90
completed 1m bars plus completed 5m and 10m resamples. It trained only on the
first 10 sessions, left the purge session unused, compared fixed candidates on
the next 5 sessions, and did not materialize the last 4 sessions. This is a
small anti-overfit evidence boundary, not a KIS Paper approval or a reason to
pause collection, scheduling, or virtual orders.

Run the offline CPU comparison with a new external label:

```powershell
uv run python scripts\run_kis_intraday_feature_breadth.py `
  --run-label qqq-YYYYMMDD-YYYYMMDD-feature-breadth-r1 `
  --session-date YYYY-MM-DD
  # repeat --session-date until exactly 20 ordered full regular sessions are supplied
```

Run the fixed development-only CUDA GRU smoke in the network-disabled research
container. It consumes the external D: cache through `/app/market_data` and
writes only the sanitized summary under `/app/model_artifacts`:

```powershell
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_intraday_cuda_sequence_smoke.py `
  --run-label qqq-YYYYMMDD-YYYYMMDD-gru-smoke-r1 `
  --artifact-root /app/model_artifacts `
  --cache-root /app/market_data/us_equities/kis_paper_private/intraday `
  --session-date YYYY-MM-DD
  # repeat --session-date until exactly 20 ordered full regular sessions are supplied
```

The smoke writes no checkpoint and does not choose, promote, or submit a model.
The completed first artifacts are under
`D:\thericher-v2\model-artifacts\kis-intraday-feature-breadth\qqq-20260623-20260721-feature-breadth-r1`
and
`D:\thericher-v2\model-artifacts\kis-intraday-cuda-sequence-smoke\qqq-20260623-20260721-gru-smoke-r1`.

## KIS Account Snapshot

The credential-bearing account bridge is intentionally separate from the web
process. Invoke it when current paper account facts are useful:

```powershell
docker compose --profile kis-readonly run --rm --no-deps kis-readonly
```

After changing its source or Compose definition, first rebuild the local image:

```powershell
docker compose build kis-readonly
```

`docker compose run` reuses an existing image and does not prove that it contains
the current working tree. This is runtime reproducibility, not a new KIS Paper
approval or a reason to delay unrelated work.

It writes a sanitized local runtime snapshot. Schema v3 retains only the
account fields the local console needs: currencies, orderable amounts, symbols,
quantities, sides, and freshness. It intentionally excludes reference prices,
position prices, open-order limit prices, order identifiers, credentials,
account numbers, raw response bodies, and tokens. Do not pass `.env` values on
a command line or emit those values in logs/artifacts.

The bridge reports its fixed `read_only` scope and whether the account snapshot
is complete. It is not a `safe_to_submit` approval proxy: a later paper executor
uses a fresh account view together with its own virtual-route, intent, and
unknown-outcome checks. An unavailable bridge artifact may retain only its
allowlisted endpoint, transaction ID, HTTP status, and a narrow KIS `msg_cd`
code; never a broker message body, `msg1`, account identifier, or free-form
response text.

### Bounded Account Snapshot Observer

The task-owned observer uses the same one-shot bridge rather than a new KIS
client or dashboard route. Install or reattest only this named task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_kis_paper_schedules.ps1 `
  -ScheduleName thericher-kis-paper-snapshot-observer -SkipImageBuild
```

It starts at 21:20 KST on weekdays and repeats every four minutes for a bounded
10-hour window. Before it invokes Docker, the credential-free host inspector
uses the source-backed 2026 US session calendar and returns the eligible
session close. The runner rechecks that close immediately before Docker. Outside
a known session, or with four minutes or less remaining, it exits with a
categorical result and makes no Compose or KIS call. During an eligible session
it invokes only:

```powershell
docker compose --profile kis-readonly run --rm --no-deps --pull never `
  -e THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID=<new-uuidv4> `
  kis-readonly
```

Task Scheduler uses `IgnoreNew`, the runner also holds a named host mutex, and
the bridge holds an advisory refresh lock on the shared runtime volume for every
snapshot writer. A busy bridge leaves the prior snapshot and external artifact
root untouched; a bridge failure writes the existing canonical unavailable
snapshot. There is no missed-run catch-up, foreground sleep, or retry loop.

For a tagged `complete` or `unavailable` bridge result, the bridge writes one
immutable source-safe observer receipt under
`D:\thericher-v2\model-artifacts\execution\kis-paper-snapshot-observer`. It
retains only the UUIDv4 marker, categorical status/reason, timestamp,
read-only/no-submit contract, and a relative bridge-receipt pointer plus the
SHA-256 of that final bridge receipt. The reader recomputes that hash and
requires the bridge status, timestamp, reason, and marker to match. It never
copies account facts or diagnostics into the observer receipt. The bridge CLI
emits the marker only after that reader succeeds, and the runner requires it to
equal its own fresh UUIDv4. A busy, crashed, or otherwise missing observer
receipt is `unknown`; do not infer success or busy from a Task Scheduler exit
result alone. The marker demonstrates a marker-present observer invocation only
under the assumed-honest local host; it is not cryptographic proof that Windows
Task Scheduler launched the process.
Inspect task facts without account values:

```powershell
Get-ScheduledTaskInfo -TaskName thericher-kis-paper-snapshot-observer
```

Reattach one exact tagged observer receipt without calling KIS, Docker, the
dashboard, or a credential path:

```powershell
uv run --extra dev python scripts\reattest_kis_paper_snapshot_observer.py `
  --evidence-path D:\thericher-v2\model-artifacts\execution\kis-paper-snapshot-observer\<exact-receipt>.json `
  --artifact-root D:\thericher-v2\model-artifacts `
  --repository-root .
```

The path is required: the reattacher never scans for a newest receipt. It
recomputes the bridge hash and validates the bound marker/status/time/reason,
then prints only the categorical read-only fact. A missing, malformed, or
tampered receipt is `observer_evidence_unavailable`; it is not a reason to
rerun the task or infer a fresh account snapshot.

On 2026-08-07, the caller-selected `20260807T141607347092Z` observer sidecar
reattached as `complete` at `14:16:07Z`, with `read_only` scope and no submit
capability, after the host reader recomputed its referenced bridge SHA-256.
The credential-free loopback dashboard `/health` returned only `ok` and
`broker_calls: false`; no account value, identifier, or raw snapshot was read.
This is marker-present observer provenance under the assumed-honest host, not
cryptographic proof of Task Scheduler origin: Task Scheduler Operational
logging is disabled on this host.

The current-image bridge reached `balance` (`VTTS3012R`) and received HTTP 500
with `EGW00201` on 2026-07-21 UTC after a successful image rebuild. It sent no
order. KIS's official sample repository identifies that code as exceeding the
per-second request limit. The real read-only transport now spaces valid external
requests by at least one second using an injectable monotonic policy. A rebuilt
bridge then completed at `20260721T223701135634Z-complete.json` with only
sanitized position/open-order counts and USD currency labels. It made no order.

On 2026-08-04 KST, one rebuilt current-image bridge invocation completed and
the existing loopback dashboard rendered its fresh schema-v3 projection. The
Docker web process had no KIS environment values or broker/artifact mount. The
source-safe bridge receipt is external only under
`D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge`.
This is read-health evidence, not a submit permission or a substitute for a
future executor's fresh call-time account and quote checks.

The separate canary transport now uses that same source pacing for valid real
virtual requests. Its first current-image virtual run,
`canary-20260721T225034Z`, reached initial reconciliation then ended as
`outcome_unknown` with `submit_transport_unknown`. Its safe evidence has no
broker order reference, which is not proof that KIS received no submit side
effect. Its one allowed same-run recovery is complete: it made no order-route
request and found an available account, zero open orders, zero completion rows,
and no matching entry. Because the run has no durable broker reference, its
state remains `outcome_unknown` / `reconciliation_unresolved`. Do not retry,
replace, modify, or cancel that run. A later independently identified canary
may proceed after its failure diagnostics are improved. This is a technical
recovery rule, not a manual approval or live route.

The first independently identified paced canary,
`canary-20260721T232137Z`, reached clean initial reconciliation and received
the closed result `submit_kis_rejected`; safe evidence still has zero open
orders, zero completion rows, no matching entry, and no broker order reference.
Preserve it as `outcome_unknown` rather than retrying it. The next diagnostic
may retain only a strictly validated short KIS-style code when present; it must
not retain response text or any other response field.

The next independent run, `canary-20260721T233837Z`, verified that projection:
KIS again returned `submit_kis_rejected` after clean reconciliation but supplied
no valid code, so the safe field is `null`. Official KIS sample code confirms
the current US-paper buy route/fields and documents `last` plus `zdiv` on its
quote endpoint. The next execution task should derive a private limit from that
quote and run inside a known US regular-session window, rather than changing the
documented order mapping or repeatedly submitting a fixed `$1` order.

## KIS Paper Order Work

Paper order submission is authorized as soon as the Execution adapter exists.
Before sending a paper order, the implementation must prove through tests that
it cannot build a live host/route, persist an idempotent intent, and reconcile
an unknown outcome. These are code correctness requirements, not an operator
approval sequence. The dashboard remains credential-free and cannot submit an
order by itself.

## Local KIS Paper Operations Console

Start or rebuild the local-only console with:

```powershell
docker compose up -d --build web
```

Open `http://127.0.0.1:8787`. The console reads only sanitized runtime
projections and writes local directional state. `Pause buys` prevents a new
buy canary/session from loading Paper configuration or calling KIS; `Resume
buys` clears that local instruction immediately. `Pause sells` is preserved for
the daily sell executor and does not suppress a hard-risk exit. None of these
buttons submits, modifies, cancels, or reconciles a broker order by itself, and
none is a Paper approval, capital, profitability, trade-count, or report gate.

The web service has no KIS credentials, private canary state, or `D:` market
data mount. It can show a metadata-only cache-freshness projection. To refresh
that projection without reading credentials or calling KIS:

```powershell
docker compose --profile kis-paper-intraday-head run --rm --no-deps --build `
  kis-paper-intraday-head python scripts/backfill_kis_paper_private_intraday.py `
  --project-only --runtime-projection /app/runtime/state/kis_paper_intraday_freshness.json
```

To make one separate, virtual-only account-read observation, use the named
bridge rather than a session or canary command:

```powershell
docker compose --profile kis-readonly run --rm --no-deps kis-readonly
```

It publishes only a sanitized external availability record and a short-lived
local runtime snapshot. It cannot submit, modify, cancel, or reconcile an
order. A successful bridge is current read-health evidence only; it never
replays a prior receipt or substitutes for the fresh account and quote reads
required by a later scheduled Paper session.

The `kis-readonly` service has a read-only container root with `/tmp` as tmpfs.
Its existing runtime and external artifact mounts are the only intended writable
locations; do not add an unrestricted writable repository or data mount to this
read-only account observation path.

`raw_market_data_retained: false` is never a control condition for the console,
a later collection, a KIS Paper call, an order, or a schedule. It records only
the absence of bytes for its own historical result.

When a due session ends before a canary intent exists, such as a directional
buy pause or quote failure, it refreshes the sanitized canary runtime to
`unavailable` with no account, order, quote, or broker-body data. The detailed
safe reason remains in the external session evidence; the console never keeps a
stale prior canary result as if it were current.

Schedule installation or an explicit task update builds each named service image
before registering its Windows task. Due tasks then run with `--pull never` and
never build in the market-time decision path. A missing image is a truthful,
recoverable task failure; run `scripts\install_kis_paper_schedules.ps1` after a
code or dependency update to rebuild images and refresh task commands. This is
runtime reproducibility, not a new scheduling or Paper approval condition.

All named tasks allow battery start/continuation and have explicit execution
limits. The current finite Paper quote cycle and daily budget session retain
`IgnoreNew`, now with a 25-minute limit, and deliberately omit
`StartWhenAvailable`: a late wake or login must not create an off-cadence
Paper session. The retired daily-backfill task is
data-only and has a 390-minute task limit around its declared six-hour inner
budget.

The Codex app daily operating review runs at 08:10 KST. It is the concise
operator-summary and integration pass for the prior daily-SPY head/session,
quote-session, and intraday-head sanitized outcomes. It performs no KIS call
itself; the named Windows tasks remain the only recurring KIS-facing
execution/data jobs.

### Intraday Causal-Input Reattachment

For one caller-selected `thericher-kis-paper-intraday-head` terminal, use only
the offline projection below. It follows the task-owned current pointer and
verifies its immutable terminal hash and same-run capture binding. When a
later task writes them, it also reattests the exact source-local availability
contract/receipt/precommit/summary hashes, recomputes the named summary-file
hash, and reattests the pair-attempt contract that uses them; any mismatch is
rejected. It never loads credentials, starts
Docker, reads a broker route, or opens raw minute rows.

```powershell
$env:THERICHER_HOST_MODEL_ARTIFACT_ROOT = 'D:\thericher-v2\model-artifacts'
$env:THERICHER_HOST_MARKET_DATA_ROOT = 'D:\market_data'
uv run python scripts\project_kis_paper_intraday_head_schedule_receipt.py
```

A terminal is not a causal-input qualification. Classify the exact input as
`input_unavailable` when the bound cumulative coverage is incomplete or when
completed-bar/session geometry, target/hash identity, chronological split,
decision-time availability, or provider finality is absent. Never replace a
missing fact with a scheduler exit code, cache timestamp, terminal page, or
latest-artifact lookup. Matching availability and pair hashes do not attest
decision-time availability or provider finality by themselves. The existing
Windows task alone owns the next attempt; continue independent Execution
observation and CPU preparation without a foreground wait.

The fresh 2026-08-11 06:20 KST terminal reattached through this reader at
2026-08-10T21:20:07Z. Its terminal, same-run capture, and availability bindings
verified, but the cumulative current-session coverage category was `incomplete`;
the optional pair binding remained `legacy_unbound`. Therefore this exact input
is `input_unavailable/session_coverage_incomplete`, with decision-time
availability and provider finality still `not_observed`. This is a source-safe
coverage fact only, not a raw-data, model, execution, or provider-finality
claim.

The metadata-only coverage inspector now treats a later retained row with the
same fingerprint and a completed bar end as cumulative confirmation of that
row. It still reports a conflicting fingerprint and excludes candidate-batch
conflicted chunks. This rule applies to future inspections and capture receipts;
it does not rewrite prior immutable receipts. Re-evaluating the current cache
under the repaired rule remained short, so the terminal above remains
`input_unavailable` and no consumer is upgraded.

### Future-Only Causal Attestation Writer

The networkless writer below is not a collector, task installer, broker route,
or terminal rewriter. It reads the task-owned current source-safe projection
and a separate external-observer input under the external artifact root. It
writes an immutable future attestation only when capture coverage is complete,
availability and pair bindings are exact, every independent-observer category
is present, the input run/timestamp exactly matches the current terminal, and
the availability/decision/finality timestamps are ordered correctly.

```powershell
uv run python scripts\write_kis_paper_intraday_causal_attestation.py --execute
```

No `.env`, credential, KIS, Docker, account, order, quote, raw M1, or task path
is opened by this command. Missing, task-derived, stale, malformed, or
mismatched observer input yields a source-safe `not_written` result and creates
no artifact. The 2026-08-17 current-terminal smoke correctly returned
`not_written/session_coverage_incomplete`.

The independent-observer origin is marker-present, assumed-honest provenance;
the writer does not claim cryptographic proof that an input was independently
observed. Exact run/timestamp binding rejects an explicit replay or a
task-derived input, but a source that falsely labels itself independent remains
an external provenance limitation. A future dispatcher integration is separate
and must never attach an artifact to an existing immutable terminal.

## Bounded Daily SPY Stability Observer

`thericher-kis-paper-daily-spy-stability-observer` is a Data-only Windows task
at 23:15 KST on weekdays. It runs the
`kis-paper-daily-spy-stability-observer` Docker profile between the existing
22:15 daily-SPY head and the 23:35 virtual-Paper canary. It receives only the
Paper application key/secret, pins the existing virtual host through the
market-data client, and sends at most one `dailyprice` request for `SPY/AMS`
after all of these local checks pass:

- the current time is within 23:15--23:20 KST on a weekday;
- the verified daily-head snapshot is 15--90 minutes old and ends strictly
  before the current Eastern market date;
- the shared KIS request and token-start gates permit the token/request path;
- the separate source-safe receipt ledger has fewer than ten prior GET
  attempts and is not already held by another observer process.

The observer compares only the prior-session row hash from the cached head
with the separately timed response. Its external receipt contains categorical
status, UTC timestamps, scope bindings, and hashes, never raw OHLCV, prices,
credentials, account data, order data, or a live route. A missing/stale
snapshot, client/config failure, token failure, or lock contention records a
categorical `unavailable` result without consuming a `dailyprice` attempt.
`stable` means only that the two virtual-Paper reads matched;
`provider_finality` remains `not_observed`, and the receipt is neither a
consumer qualification nor an Engine/Paper input.

The Docker service mounts all market data read-only except the existing narrow
`collection-control-v1` gate directory, and mounts the external artifact root
for immutable receipts. It has no account, order, KIS live, model, GPU, or
dashboard surface. Validate a completed receipt offline only:

```powershell
uv run python scripts\validate_kis_paper_daily_spy_stability_receipt.py `
  --receipt-path <external-receipt-path> `
  --repository-root C:\Users\Public\Documents\thericher-v2
```

Do not manually invoke it to manufacture additional observations. Its bounded
worker owns the next due run; a source-safe receipt is reattached after the
task completes while unrelated lanes continue.

## Daily SPY Point-In-Time Paper Session

The daily SPY path first refreshes its small forward `SPY/AMS` head and then
evaluates one whole hash-attested source. The collector drops the current US
exchange date before storing bytes, so a same-session daily close never reaches
the receipt. The runner uses the first local availability of that source, a
transparent two-close baseline, one fresh complete KIS Paper account/open-order
snapshot, and a separate fresh `AMS` price proof before the Paper boundary. A
ready entry is eligible only from a flat account and a ready exit only from one
`SPY` / `AMEX` share. Any SPY open order, stale account fact, or out-of-scope
position produces a scoped no-intent result rather than an inferred position or
replacement order. The service uses the virtual buy/sell routes only and leaves
a valid daily lifecycle limit order open for normal virtual reconciliation; the
standalone canary remains the immediate-cancel diagnostic.

Run the two stages manually only when needed; both are authorized KIS Paper
work and emit safe metadata rather than secrets, raw market rows, prices, or
broker bodies:

```powershell
docker compose --profile kis-paper-daily-spy-head run --rm --no-deps --build `
  kis-paper-daily-spy-head

docker compose --profile kis-paper-daily-spy-session run --rm --no-deps --build `
  kis-paper-daily-spy-session
```

The installed Windows tasks run the head at 22:15 KST, the stability observer
at 23:15 KST, and the receipt session at 23:50 KST, Monday through Friday. The
session may honestly record a
no-intent when a receipt is stale or abstains, the market is closed, its
directional pause is active, its account fact is stale or out of scope, an SPY
order is already open, or its transient price proof is unavailable. That result
applies only to that invocation and does not block the next due collection, a
separate Paper intent, or another lane. Sanitized evidence can state
`pnl_status: not_observed`; it never turns an acknowledgement or local intent
into a fill, cash, cost-basis, or realized-PnL claim.

After a daily session reaches a durable receipt-derived canary result, the same
scheduled service automatically invokes the read-only observer for that exact
`receipt-<sha256>` run. No latest-run scan, extra Windows task, or manual
permission is involved. The safe session outcome embeds the categorical
observation; an observer failure is recorded as `observer_unavailable` without
changing, retrying, cancelling, or replacing the original order outcome.

## KIS Virtual-Paper Canary

The price-input execution-learning command is a virtual-paper US buy-limit
canary with one whole share, a transient explicit nonmarket limit,
reconciliation, and cancellation after an accepted submission:

```powershell
docker compose --profile kis-paper-session run --rm --no-deps kis-paper-session
```

It receives only `KIS_PAPER_*`, pins every route to the virtual host, stores
private recovery state in its dedicated Docker volume, writes sanitized runtime
state to the shared local dashboard, and writes external evidence under
`/app/model_artifacts`. It checks the America/New_York weekday regular-session
time window before loading Paper configuration; outside that window it produces
a safe no-submit result. Its price input combines the exact `AMS/SPY`
asking-price route (`HHDFS76200100`) with `AMS/SPY` price detail
(`HHDFS76200200`), then sends an `AMEX` order only when the Korea timestamp is
fresh, decimal scales agree, and `e_hogau` supplies a valid limit tick. The
source last may be sub-tick; the helper rounds the derived limit down and
validates that final submitted value against the tick. The input never reaches
an artifact, dashboard, or log. The helper uses the explicit
supported 2026 holiday and early-close calendar. The Windows Scheduled Task
`thericher-kis-paper-quote-session` invokes this command once per weekday at
KST 23:35. Its cancel-after-submit choice is durable, matching accepted open
orders resume cancellation after a restart, and sibling run IDs are serialized
at the private state root. A non-success submit response or completion evidence
after a cancel is `outcome_unknown`, not a clean result or retry cue. Do not
pass secrets or account values on the command line.

Before a new submit, the session records its own durable intent and, under the
shared private-root lock, obtains a fresh virtual account/open-order snapshot.
A replayed session ID recovers only its exact durable state and cannot create a
replacement order. A distinct current session does not enumerate, mutate, or
relabel historical state files: it records `matching_open_order` and sends no
new order only when its fresh snapshot contains a matching current order. This
is intentionally not a claim that a historical unknown which is absent from the
current broker view is clean or impossible. That visibility limit remains
unqualified, not a global Paper hold or an approval step.

The original `NAS/SPY` quote and price-detail diagnostics returned
success-shaped mappings with blank required price fields. They are historical
rejected candidates, not the current input. The current `AMS/SPY` structural
probes proved the route shape, fresh timestamp category, scale, and tick input
without retaining a value. The diagnostic command below emits only HTTP,
mapping, result, and field-state categories; it never writes a price, raw
response, account value, intent, or order:

```powershell
docker compose --profile kis-paper-session run --rm --no-deps --build `
  kis-paper-session python scripts/probe_kis_paper_spy_price_detail.py
```

Use it only to classify the documented candidate. A blank or invalid result
rejects that conversion and does not create an approval hold, one-shot quota,
or a pause on later correctly scoped Paper work.

The canary may be invoked by a scoped recurring Paper schedule during eligible
sessions. There is no one-shot or per-goal execution quota: a distinct new
intent can proceed after the scheduler's technical session, pacing, concurrency,
and durable-state checks. An ambiguous intent remains unrepeated until its own
reconciliation; it may defer only the next exact conflicting quote-session
canary, never a later distinct Paper intent or another lane.

For a persisted ambiguous run, use the read-only recovery command. It rebuilds
the decision only from private durable state and rejects every phase that could
create a new order or cancel an acknowledged order:

```powershell
docker compose --profile kis-paper-session run --rm --no-deps --build `
  kis-paper-session python scripts/reconcile_kis_paper_canary_unknown_run.py `
  --run-id <existing-run-id> --state-root /app/private/canary `
  --runtime-projection /app/runtime/state/kis_paper_canary.json `
  --paper-account-snapshot /app/runtime/state/paper_account_snapshot.json `
  --emergency-state /app/emergency/emergency_state.json `
  --execution-control /app/emergency/paper_execution_control.json `
  --artifact-root /app/model_artifacts --repository-root /app
```

It may obtain a virtual token and read reconciliation endpoints, but never uses
the buy-limit or cancellation route. A missing or malformed private state ends
with a safe failure; it is not recreated from command-line values.

The 2026-08-11 historical session/direct reader pair is bound as
`canary_completed -> outcome_unknown / unresolved`, `paper_only`, with no
attribution eligibility. Its later closure assessment did not rerun this command:
the source-safe evidence did not include an exact private durable-state binding
or a predeclared immutable pointer proving that no same-run reconciliation had
already occurred. It therefore preserved the scoped unknown without a KIS,
submit, cancel, modify, or replacement request. This is not broker-state proof.

Read-only reconciliation may repeat through the existing owned, serialized
path with exact persisted intent identity and submission-date binding.
Record its outcome without altering old receipts. A prior reconciliation is
not a one-attempt quota, and predeclared proof of no prior attempt is not a
permission prerequisite. Missing/ambiguous identity remains unresolved for that
intent; never fabricate a replacement submission or cancel an unrelated order.
The 2026-09-21 bootstrap changes this operating instruction only. The
submission-date and never-submitted-intent state-machine fixes remain work for
the Execution owner, not demonstrated runtime recovery.

To inspect one completed canary without a KIS call or credential read, project
only its sanitized lifecycle fact from the host artifact root:

```powershell
uv run python scripts/project_kis_paper_canary_lifecycle.py `
  --run-id <existing-run-id>
```

The host command uses `THERICHER_HOST_MODEL_ARTIFACT_ROOT` rather than the
Docker-only `/app/model_artifacts` path. It emits only opaque references,
lifecycle/reconciliation categories, and attribution eligibility.

### Receipt-Linked Observation

Observe one existing receipt-derived SPY Paper intent through the read-only
observer profile:

```powershell
docker compose --profile kis-paper-receipt-observer run --rm `
  -e KIS_PAPER_RECEIPT_RUN_ID=<receipt-run-id> `
  kis-paper-receipt-observer
```

The observer reads the matching private durable state, then may call only the
virtual Paper token, account/open-order, and same-day history endpoints. It
cannot submit, modify, or cancel an order. `same_day_id_seen` is only an order
ID sighting; it is never a fill, cancellation, receipt-attributed position, or
realized PnL result. Artifacts remain external under
`D:\thericher-v2\model-artifacts\execution\kis-paper-receipt-observation`.
If the exact state is absent, corrupt, stale, or ambiguous, retain the scoped
categorical result and continue distinct authorized Paper work normally.
The standalone profile remains useful for an exact manual replay or diagnosis;
the normal daily schedule already performs the same exact-run handoff.

### Terminal Field Contract Probe

Use this only to inspect the documented field shape for one existing SPY/AMEX
Paper canary state. It reads the state volume read-only, derives the KIS query
day from the persisted acknowledged-submission timestamp, and calls only the virtual token plus
`VTTS3035R` history GET path:

```powershell
docker compose --profile kis-paper-terminal-field-probe run --rm --no-deps `
  -e KIS_PAPER_TERMINAL_PROBE_RUN_ID=<existing-run-id> `
  kis-paper-terminal-field-probe
```

Its artifact is under
`D:\thericher-v2\model-artifacts\execution\kis-paper-terminal-field-probe`
and contains only opaque references, identity/pagination categories, and field
presence. It never writes a broker identifier, value, account fact, status
code, payload, terminal lifecycle, or PnL. A missing or ambiguous exact row is
a scoped source-contract result, not a reason to stop Paper sessions,
collection, or research. Before any history request, the probe requires the
persisted run, client-order, and decision identifiers to agree with the
requested receipt identity. The one original legacy decision form may use a
derived `created_at` ET day only when its run timestamp, one-minute skew,
five-minute-or-less validity interval, and full ET date agree; its safe result
is separately labeled `history_observed_derived_date` and
`derived_created_at_et_day`. It never treats an absent or ambiguous derived-date
row as an order, cancellation, fill, or PnL conclusion. A missing state,
identity mismatch, or unqualified timestamp-free legacy state is categorical
evidence with no credential or network access, never proof that an order was
not submitted.

For a daily SPY session, the existing session process invokes the same probe
only after it has checked the receipt-derived run identity and completed the
receipt observer. Its safe session evidence contains only the probe payload and
an opaque content-hash artifact reference; a probe failure records
`terminal_field_probe_unavailable` while preserving the prior canary and
observer outcomes. This is not another schedule, order route, quota, or
terminal/PnL promotion. The standalone profile remains useful for an exact
manual replay or diagnosis.

The first token attempt on 2026-07-21 returned `auth_rejected` before a
submission. An earlier read-only bridge attempt reached the account boundary
and returned `balance_rejected`; no order was sent. The current-image
read-only bridge completed on 2026-07-22 and refreshed the sanitized local
console projection without submitting an order. These are integration facts,
not approval gates. Diagnose the virtual-paper route through the sanitized
reason plus allowlisted endpoint/transaction/HTTP metadata, then rerun a
bounded bridge job. The first current-image canary result is an ambiguous
submit transport outcome, and its exact persisted run has already received its
one read-only recovery. Preserve that run as unresolved; improve closed safe
submit diagnostics before a separately identified new canary. The first such
new canary is now preserved as a KIS rejection, so expose only a validated
short KIS code on a later independent run. Do not substitute live credentials
or inspect/print secret values. The sanitized runtime and evidence never retain
an API body, account identifier, or secret.

## Research And Artifacts

Keep generated checkpoints, campaign summaries, and control evidence under:

```text
D:\thericher-v2\model-artifacts
/app/model_artifacts
```

### FirstRate Free M1 Source-Local Normalization

Normalize only the staged, acquisition-receipt-bound SPY/QQQ ZIPs with:

```powershell
uv run --extra dev python scripts/normalize_firstrate_free_intraday.py
```

The runner has no network, credential, KIS, broker, Docker-service, or Task
Scheduler path. It rechecks each source ZIP hash, expects exactly one named CSV
entry, rejects invalid ordering/DST/archive shape, writes canonical `CSV_FIELDS`
files under `D:\market_data\us_equities\firstrate_free_intraday\canonical`, and
writes only aggregate evidence to
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday`.

The output timestamp set must equal the decoded source timestamp set. Do not
fill, reindex, aggregate, or infer omitted minutes; zero-volume omissions stay
`not_present_in_source`. The normalized files are source-isolated retrospective
mechanics only, not session coverage, KIS parity, decision-time availability,
provider finality, a model input, a Paper input, or a live route.

### FirstRate Source-Local Timeframe Mechanics

Build the aggregate-only mechanics manifest with:

```powershell
uv run --extra dev python scripts/build_firstrate_free_intraday_timeframe_mechanics.py
```

The runner reattests the canonical input hashes from the normalization receipt,
loads the files through `LocalCsvBarProvider`, and holds resampled Bars only in
memory. It records source-safe 1m/5m/10m/1h/3h counts, timestamp-set hashes,
and OHLCV content hashes under `D:\thericher-v2\model-artifacts`; it never
writes resampled market rows. A target bucket is retained only when every
expected observed source minute is unique, complete, and contiguous.

Buckets use a UTC-epoch anchor, not a U.S. regular-session anchor. A bucket not
emitted from the observed source set is not a claim about a market gap,
zero-volume bar, session coverage, provider finality, or decision-time
availability. This manifest remains source-isolated and non-promoting.

### FirstRate Source-Local Window Preflight

Build the target-free window-geometry manifest with:

```powershell
uv run --extra dev python scripts/build_firstrate_free_intraday_window_preflight.py
```

The runner reattests the normalization and timeframe-mechanics receipts before
re-reading canonical CSVs. It recomputes the fixed 1m/5m/10m/1h/3h matrix and
records only eligible-window counts and end-timestamp-set hashes. A window is
eligible only when all in-memory Bars are complete and every adjacent start is
exactly one declared timeframe apart. It never bridges, fills, reindexes, or
writes a feature, label, price, prediction, weight, or resampled Bar.

The result is source-local geometry only. It is not a time-grid, session,
availability, finality, KIS-parity, model, backtest, Paper, or live claim.

### FirstRate Source Semantics

Retrieve the two official FirstRate pages and then attach the review-limited
interpretation with:

```powershell
uv run --extra dev python scripts/retrieve_firstrate_source_semantics.py
uv run --extra dev python scripts/resolve_firstrate_source_semantics.py
```

The retrieval fetches each official no-auth page twice and records only URL,
hash, exact source statements, and source-safe fact status under
`D:\thericher-v2\model-artifacts`. The resolver reattests that immutable source
receipt and records the bounded interpretation without a network call or source
rewrite. It must preserve fixed-offset versus DST conversion and source bar
start/end stamping as `not_disclosed` unless a separate primary source resolves
them. Neither receipt authorizes cross-feed alignment, session completeness,
KIS parity, a model, Paper, or live behavior.

### FirstRate 5m CPU After-Cost Control

Run the fixed source-local SPY/QQQ L2 control once with a new label:

```powershell
uv run python scripts/run_firstrate_5m_after_cost_control.py --run-label <unique-label>
```

The runner reads only the existing canonical FirstRate CSVs and normalization
receipt, creates complete contiguous UTC-anchored 5m Bars in memory, and
freezes a 60-bar observation, one-bar direction target, 61-bar embargo,
L2-logistic fit, `always_flat`/previous-bar comparators, and 1/3/5-bps
per-side synthetic costs. It writes only external precommit, model, aggregate
summary, and independent validation JSON; raw bars, labels, predictions, paths,
and local-paper event logs are not retained. It has no credential, network,
KIS, broker, order, GPU, or Paper-consumer path.

The completed `20260820-r2` run was `rejected`: its L2 candidate beat flat in
zero of six SPY/QQQ nonzero-cost cells. All 18 replay cells were local-paper,
replayable, and terminal-flat. Do not rerun or tune that lineage; do not infer a
GPU, KIS, or execution consequence from it. The next disjoint technical-rule
control needs its own frozen precommit and independent validation.

### FirstRate 5m Technical Trend-Rule Control

Run the frozen source-local `SMA(20) > SMA(60)` rule once with a new label:

```powershell
uv run python scripts/run_firstrate_m5_trend_rule_after_cost_control.py --run-label <unique-label>
```

The runner reuses only the existing source reattestation and complete,
contiguous UTC-anchored 5m geometry. It performs no training or calibration,
then replays the fixed trend rule, `always_flat`, and previous-bar-direction
comparators through terminal-flat `local_paper` at the same 1/3/5-bps
per-side synthetic band. It writes only external precommit, aggregate summary,
and independent validation JSON; it retains no raw bars, labels, predictions,
or event stream and has no credential, network, KIS, broker, order, GPU, or
Paper-consumer path.

The completed `20260820-r1` run was `rejected`: the trend rule beat flat in
zero of six nonzero-cost SPY/QQQ cells, while all 18 replay cells were
`local_paper`, replayable, and terminal-flat. Do not rerun or tune this
20/60 rule or treat it as a GPU, KIS, execution, or profitability signal.

### FirstRate 5m Mean-Reversion Control

Run the frozen source-local Wilder-RSI(14) <=30 / >=50 rule once with a new
label:

```powershell
uv run python scripts/run_firstrate_m5_mean_reversion_after_cost_control.py --run-label <unique-label>
```

The runner reattaches the existing canonical FirstRate source and complete,
contiguous UTC-anchored 5m geometry. It freezes a 60-bar observation,
61-bar embargo, completed-bar Wilder RSI with long-only <=30 entry and >=50
exit, a predeclared next-bar terminal flatten, `always_flat`, and the fixed
1/3/5-bps-per-side synthetic band. It writes only external precommit, aggregate
summary, and independent validation JSON; no raw bars, features, predictions,
or local-paper event stream are retained. It has no credential, network, KIS,
broker, order, GPU, or Paper-consumer route.

The completed `20260820-r1` run was `rejected`: the RSI rule beat flat in
zero of six nonzero-cost SPY/QQQ cells. All 12 replay cells were
`local_paper`, replayable, and terminal-flat. Do not rerun or tune this
fixed 14/30/50 lineage or treat it as a GPU, KIS, execution, or profitability
signal.

### Tiingo D1 Trend-Pullback Rotation Falsification

Run the frozen source-separated SPY/QQQ/IWM D1 rotation once with a unique
external label, then reattach its exact receipt in a fresh process:

```powershell
uv run python scripts/run_tiingo_d1_trend_mean_reversion_rotation.py --run-label <unique-label>
uv run python scripts/run_tiingo_d1_trend_mean_reversion_rotation.py --run-label <same-label> --verify-only
```

The runner reads only its pinned local Tiingo snapshot and writes a precommit,
aggregate summary, and independent validation receipt beneath the external
artifact root. It does not read `.env` or credentials, call a network, KIS,
Docker, or broker, train or load a model, use GPU, retain rows/prices/scores,
or create an Execution or Paper input.

The completed `20260820-r1` run stopped at the frozen preflight as
`input_unavailable/insufficient_validation_active_decisions`: only 3 of the
required 100 validation decisions were active, while 1,892 of 1,896 scheduled
validation decisions were excluded by the fixed event/discontinuity conditions.
This is not a performance or PnL result. Do not retune the rotation, cost
band, masks, or threshold from this outcome. A separate aggregate-only Data
audit must establish whether the fixed mask contract is structurally sparse
before any later policy change is considered.

### Tiingo D1 Event-Mask Coverage Audit

Run the bounded aggregate audit only after the completed rotation has all three
immutable receipts, then independently reattach it:

```powershell
uv run python scripts/run_tiingo_d1_event_mask_coverage_audit.py --run-label <unique-label>
uv run python scripts/run_tiingo_d1_event_mask_coverage_audit.py --run-label <same-label> --verify-only
```

It reattaches the same pinned local snapshot and completed rotation receipts,
then emits only aggregate event/discontinuity counts, deterministic index-set
hashes, bounded exclusion-run buckets, and binding status. It does not read
`.env` or credentials, call a network, KIS, Docker, or a broker, use GPU,
train/load a model, retain rows/dates/prices/values/per-decision masks, or
create an Execution or Paper input.

The completed `20260820-r1` audit is `consistent`: event masks account for
all 1,892 validation exclusions, discontinuity-only exclusions are zero, four
contexts are unmasked, and three are active. No semantic contradiction was
found, so the frozen Tiingo rotation lineage is closed without retuning its
rule, mask, threshold, source, or cost contract.

### Source-Scoped Liquid Universe

Reattest the current local source metadata without reading bars, credentials,
or a provider:

```powershell
uv run python scripts/materialize_source_scoped_liquid_universe.py
```

The immutable manifest stays under
`D:\market_data\us_equities\source-scoped-liquid-universe\v1`. It binds the
private QQQ/SPY/IWM D1 cache index and the current six-symbol NAS D1 panel as
separate partitions. It is not a point-in-time historical universe, liquidity
qualification, stock rank, cross-sectional alignment, model input, or Paper
authorization. The only current consumer is an offline unranked metadata
handoff; a later rule must declare its own source/feature/cost contract.

Run a CPU baseline before an eligible GPU campaign. GPU work needs a frozen
dataset and falsifiable hypothesis; do not launch models solely to keep the GPU
busy. One GPU job runs at a time while other lanes continue.

### KIS Daily Sequence Breadth Screen

The daily sequence screen is a fixed QQQ/SPY-only, development-only comparison
of compact LSTM, causal TCN, and compact attention. It reattests the pinned
private daily catalog offline, uses 20 completed-bar windows, keeps a 22-session
purge between development and validation, fits standardization only on pooled
development rows, and replays only `local_paper` next-open/following-open
targets. It does not select a winner, form an ensemble, promote a checkpoint,
or call KIS.

Run the CPU wiring smoke first with a unique label:

```powershell
docker compose --env-file .env.example --profile research run --rm --no-deps `
  research python scripts/run_kis_daily_sequence_architecture_screen.py `
  --mode cpu-smoke --run-label <unique-label> `
  --cache-root /app/market_data/us_equities/kis_paper_private/daily `
  --artifact-root /app/model_artifacts
```

Only after that contract succeeds, run the fixed CUDA attempt with another
unique label:

```powershell
docker compose --env-file .env.example --profile research run --rm --no-deps `
  research python scripts/run_kis_daily_sequence_architecture_screen.py `
  --mode cuda-screen --run-label <unique-label> `
  --cache-root /app/market_data/us_equities/kis_paper_private/daily `
  --artifact-root /app/model_artifacts
```

The research profile has no network and mounts market data read-only. It writes
precommit, summary, checkpoint, and replay evidence only under the external
artifact root. A code-only rerun may reuse the existing research image because
the source and scripts are mounted read-only; rebuild only after a Dockerfile or
runtime dependency change.

### NAS D1 Per-Symbol Sequence Breadth

The source-local NAS breadth runner reattests the fixed six-stream campaign
before every run. It first writes six deterministic CPU L2-logistic smoke
receipts, then writes external-only CUDA `state_dict` checkpoints for LSTM,
causal TCN, and compact attention. Validation forwards remain target-free; this
runner neither selects a candidate nor creates replay or PnL evidence.

Run the CPU smoke on the host with a fresh label:

```powershell
uv run --extra dev python scripts/run_kis_nas_d1_sequence_breadth.py `
  --mode cpu-smoke --run-label <unique-cpu-label> `
  --market-data-root D:/market_data `
  --artifact-root D:/thericher-v2/model-artifacts
```

Then run CUDA without loading the local `.env`; use the corresponding external
CPU summary path inside the container:

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = "1"
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_nas_d1_sequence_breadth.py `
  --mode cuda-breadth --run-label <unique-cuda-label> `
  --market-data-root /app/market_data `
  --artifact-root /app/model_artifacts `
  --cpu-smoke-summary /app/model_artifacts/research/kis-nas-d1-sequence-breadth-v1/cpu-smoke/<unique-cpu-label>/summary.json
```

Only the actual non-symlink `/app/market_data` and `/app/model_artifacts` bind
mounts count as external storage; repository `/app/data` and `/app/reports` are
read-only in this service. CUDA requires the complete sibling `precommit.json`
and source-safe CPU summary from the exact fixed campaign. Never reuse a breadth
run label or move a checkpoint into Git. A completed breadth receipt is not
validation evidence, model selection, an ensemble input, a replay, or a KIS
Paper decision.

### NAS D1 Candle-State Breadth v3

The distinct candle-state package uses only the frozen six-symbol NAS D1 panel.
Its five per-symbol features are built from 40 completed OHLCV bars under one
fixed Decimal context. The per-symbol normalizer uses ordered `fsum` and fixed-
precision canonicalization, while CPU writes a source-safe summary-attestation
sidecar before CUDA can consume the summary. The host CPU smoke and Docker CUDA
breadth therefore share one immutable contract identity. It is candidate-only:
validation forwards contain no labels, and it cannot select, ensemble, replay,
materialize PnL, call KIS, or create a Paper action.

Run the CPU smoke without loading local credentials:

```powershell
uv run --extra dev python scripts/run_kis_nas_d1_candle_state_breadth.py `
  --mode cpu-smoke --run-label <unique-cpu-label> `
  --market-data-root D:/market_data `
  --artifact-root D:/thericher-v2/model-artifacts `
  --review-status review_unavailable
```

Then run the matching CUDA breadth with the credential-free example Compose
environment and the exact external CPU receipt:

```powershell
docker compose --env-file .env.example --profile research run --rm --no-deps research python `
  scripts/run_kis_nas_d1_candle_state_breadth.py `
  --mode cuda-breadth --run-label <unique-cuda-label> `
  --market-data-root /app/market_data `
  --artifact-root /app/model_artifacts `
  --cpu-smoke-summary /app/model_artifacts/research/kis-nas-d1-candle-state-breadth-v3/cpu-smoke/<unique-cpu-label>/summary.json `
  --review-status review_unavailable
```

Do not reuse a label or write artifacts under Git. A precommit mismatch is a
scoped recovery fact for that exact contract; preserve it and issue a new
versioned contract only when feature semantics genuinely change.

### NAS D1 Sealed Local-Paper Evaluation

After the exact same-runtime CPU and CUDA breadth receipts exist, run the fixed
sealed evaluator only in the offline research container with a new immutable
label:

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = "1"
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_nas_d1_sealed_evaluation.py `
  --run-label <unique-sealed-label> `
  --market-data-root /app/market_data `
  --artifact-root /app/model_artifacts `
  --review-status review_unavailable
```

The command neither reads `.env` nor has network, KIS, credential, account, or
broker access. It reattests the frozen panel and campaign, reloads each external
checkpoint with `weights_only=True`, reconstructs validation targets only in
memory, and simulates the fixed two-session slots through `local_paper`. Its
external directory contains only immutable source-safe `precommit.json` and
`summary.json`; no raw bars, prices, labels, probabilities, event rows, or
checkpoint copies are retained. The receipts record only a marker-detected
`execution_environment` class (`docker` or `host`) and its marker observation,
not a path, device, hardware identifier, secret, or Compose-security attestation.
The versioned Compose profile and its tests establish the network/mount contract.
A completed sealed receipt is still candidate-only: it cannot rank, select,
ensemble, promote, or create a KIS Paper order.

The artifact root and every existing output-path component must be ordinary
directories. The runner rejects a symlink or Windows junction before directory
creation and again before receipt writing; do not place the sealed evaluator
under a redirected artifact path.

### NAS D1 Volatility-Conditioned Trend Breadth

The distinct source-local NAS campaign uses only causal completed-bar `20 x 5`
volatility-conditioned trend windows. It trains on development labels only and
executes validation as target-free forwards. Run the CPU smoke with a fresh
external label:

```powershell
uv run --extra dev python scripts/run_kis_nas_d1_volatility_trend_breadth.py `
  --mode cpu-smoke --run-label <unique-cpu-label> `
  --market-data-root D:/market_data `
  --artifact-root D:/thericher-v2/model-artifacts `
  --review-status review_unavailable
```

Then run its bounded CUDA breadth in the network-disabled research service,
without loading the local `.env`:

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = "1"
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_nas_d1_volatility_trend_breadth.py `
  --mode cuda-breadth --run-label <unique-cuda-label> `
  --market-data-root /app/market_data `
  --artifact-root /app/model_artifacts `
  --review-status review_unavailable `
  --cpu-smoke-summary /app/model_artifacts/research/kis-nas-d1-volatility-trend-breadth-v1/cpu-smoke/<unique-cpu-label>/summary.json
```

CUDA accepts only the exact external CPU summary and sibling immutable
precommit, writes checkpoints only below `/app/model_artifacts`, and reloads
them with `weights_only=True`. A completed receipt proves candidate plumbing
and target-free forward shape only. It is not a validation result, selection,
ensemble input, local-paper replay, KIS Paper decision, or live behavior.

### NAS D1 Volatility-Conditioned Sealed Evaluation

After the exact r2 CPU and CUDA receipts exist, run the one fixed sealed
evaluation in the network-disabled research container with a fresh label:

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = "1"
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_nas_d1_volatility_trend_sealed_evaluation.py `
  --run-label <unique-sealed-label> `
  --market-data-root /app/market_data `
  --artifact-root /app/model_artifacts `
  --review-status review_unavailable
```

The runner reattests the panel and exact r2 receipts before it writes its
precommit. A candidate-evidence fault writes a source-safe failure receipt
without opening validation targets; a completed summary retains aggregate
candidate/comparator evidence only. CPU refits must match their frozen receipt;
CUDA reload is strict and `weights_only=True`; all simulated fills are
`local_paper` and replay terminal-flat. The result is candidate-only and cannot
rank, select, tune, ensemble, promote, or create a KIS Paper order. Never reuse
a label, place artifacts in Git, or use the interrupted r3/r4 directories as a
completed result.

### NAS D1 Prospective Shadow Observation

Run one new local-cache observation in the network-disabled research service:

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = "1"
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_nas_d1_volatility_trend_prospective_observation.py `
  --run-label <unique-observation-label> `
  --market-data-root /app/market_data `
  --artifact-root /app/model_artifacts `
  --review-status review_unavailable
```

The runner reads no `.env`, credentials, KIS route, provider, account, or
broker. It reattests the frozen r2/r5 receipt identities before writing a
source-safe precommit, derives the boundary from the frozen source session, and
requires all six symbols to have a post-boundary decision plus complete `t+1`
and `t+2` D1 bars. No eligible window writes an immutable `input_unavailable`
receipt; it is complete for that invocation and does not hold collection. An
eligible window runs the fixed 24 candidates through in-memory `local_paper`
only, requires replayed terminal-flat accounts, and retains no raw bars,
targets, predictions, event rows, or checkpoint copies. Use the Docker command
for an eligible observation because it is the frozen candidate runtime.

### KIS Daily Regime-Tree Breadth

The fixed nonlinear breadth candidate uses the same 20 completed-bar QQQ/SPY
daily input and local-paper target as the established daily screen, but trains
one shallow histogram-gradient tree on development labels only. It writes no
pickle, joblib file, raw row, or model checkpoint; only source-safe precommit,
summary, and local-paper replay evidence live under the external artifact root.

```powershell
docker compose --profile research run --rm --no-deps research python `
  scripts/run_kis_daily_regime_tree_breadth.py `
  --run-label <unique-label> `
  --cache-root /app/market_data/us_equities/kis_paper_private/daily `
  --artifact-root /app/model_artifacts
```

The first fixed `20260728-cpu-smoke` is falsified for both QQQ and SPY after
costs. Do not reuse it for parameter tuning, an ensemble, a GPU rerun, model
promotion, or a Paper decision. A later campaign must make a distinct causal
hypothesis and write a separate immutable contract.

The independent `20260819-kis-daily-regime-tree-r1` reproduction also
completed beneath
`D:\thericher-v2\model-artifacts\kis-daily-regime-tree-breadth-v1`. Its
development-only fit excluded validation labels, retained no serialized
estimator, and completed two model plus six fixed comparator replays with only
`local_paper` fills. QQQ/SPY after-cost model replays were `-45.8296` and
`-73.7783`, below their fixed previous-bar-direction comparators, so the tree
lineage is closed. Do not rerun, tune, select, ensemble, allocate GPU to, or
route this result to Paper or live behavior.

### Prospective Intraday Offline Observation

To consume an already verified first-five QQQ preparation pair, run:

```powershell
uv run python scripts/run_kis_intraday_prospective_observation.py
```

The command is local-only. It does not read `.env`, credentials, or KIS state,
and it does not call a network or submit a broker order. Before the pair exists,
the expected safe result is `preparation_pair_missing`. After the pair exists,
it verifies the pair and frozen first-five QQQ dates plus row-fingerprint
digest around local cache reads. The full head-index SHA-256 remains
preparation-time provenance, so append-only or independent-SPY metadata updates
do not invalidate the pair; a selected-row change is rejected. It then writes
the frozen receipt and sanitized local-paper evidence only under
`D:\thericher-v2\model-artifacts`.

To exercise the same boundary in the isolated research container:

```powershell
docker compose --env-file .env.example --profile research run --rm --no-deps `
  research python scripts/run_kis_intraday_prospective_observation.py
```

The container has network disabled. Its external receipts omit raw prices,
order identifiers, source paths, PnL, and candidate-selection conclusions.
On recovery, the receipt accepts only current-schema canonical event envelopes
and the frozen chronological decision/fill plan. A buy must have exactly its
planned local-paper entry and exit fills; malformed, extra, or unplanned events
invalidate the receipt rather than being repaired.

### Prospective SPY Fresh-Session Capture

After the existing Data-owned KIS head collector has retained a complete SPY
session, materialize its safe 15:30 ET observation receipt with:

```powershell
uv run python scripts/capture_kis_paper_prospective_spy_observation.py `
  --session-date 2026-08-03
```

The command is cache-only: it reads no `.env`, credential, KIS client, account,
order, or network state. It requires the supplied date to be the current
America/New_York date and the current time to be at or after 15:30 ET. A normal
pre-cutoff, weekend, missing, or incomplete source returns source-safe
`not_yet_observed` with no artifact. A capture writes only canonical receipt
facts under `D:\thericher-v2\model-artifacts`; raw cache rows remain under
`D:\market_data`. Do not add a second scheduler for this command: the existing
head collector remains the schedule owner.

### Prospective SPY Virtual-Paper Session Cycle

The existing `thericher-kis-paper-intraday-head` task now invokes
`kis-paper-prospective-spy-cycle` only after its collector exits successfully.
The service reuses the `intraday-head` SPY cache and creates a source-safe
no-intent receipt when the completed-bar capture is unavailable. It reaches
the existing one-share virtual-Paper canary only for a current frozen `enter`;
the receipt content supplies the canary identity and the existing canary lock
serializes retries. It adds no Windows task and does not embed execution in the
collector process.

The first integration smoke receipts were pre-cutoff no-intent results. Do not
change the documented `00:31`, `02:31`, `04:31`, or `06:20` KST schedule or the
baseline's exclusive one-minute validity from this wiring alone. The next
Data-owned timing probe must measure 15:30 ET completed-bar availability and
end-to-end collection timing first. A no-intent probe does not need an
Execution, account, quote, or order call.

### Prospective SPY Completed-Bar Timing Probe

After a successful existing intraday-head collection, the same scheduler runs
the separate `kis-paper-prospective-spy-timing-probe` container before its
existing SPY cycle. The probe is network-disabled, receives no `KIS_*` or mode
environment values, and has only the read-only market-data and external
artifact mounts. It receives the scheduler's raw host dispatch/return
timestamps plus the collector's existing source-safe SPY aggregate result.
It then records whether the frozen prefix was present *after collection*.

The probe does not add a Windows task, start another collector, alter the
terminal schedule receipt, or affect the scheduled task exit code. Its receipt
records UTC and America/New_York endpoints with offset/DST state, a
Docker-inclusive host duration, schedule relation, aggregate collection facts,
and `decision_time_availability: not_observed`. It never establishes that data
was available at 15:30 ET or that a Paper decision could have executed before
expiry. Do not change the trigger or validity contract from one receipt;
interpret a real measurement through the next bounded Data/Engine review.

### Static Norgate Development Receipt

To re-attest the already retained static Norgate trial panel and write or verify
its sole sanitized development-only receipt, run:

```powershell
uv run --extra dev python scripts/qualify_norgate_development_input.py
```

It is offline and credential-free. It reads only the local panel under
`D:\market_data` and writes the one deterministic JSON receipt under
`D:\thericher-v2\model-artifacts\norgate-development-qualification`. The
output contains aggregate identities/counts/scope and a declarative interface,
never source rows, symbols, dates, OHLCV, feature values, labels, prices, PnL,
or broker data. A qualified result is development-only, not model, GPU,
campaign, Paper, or live authority.

### Norgate Host Readiness Bridge

Run this only for a new, explicitly bounded readiness package and only through
the isolated host runtime:

```powershell
D:\thericher-v2\host-runtimes\norgate-python\Scripts\python.exe `
  scripts\run_norgate_host_readiness_bridge.py --run-label <unique-label>
```

The bridge may call only local `status`, configured-database membership, and
US Equities update metadata, then compare it in memory against the two
predeclared local metadata-root candidates. It prints and retains only host
runtime, local API, catalog, update-metadata, and active-root categories; it
never reads price, membership, listings, corporate actions, credentials, KIS,
broker, scheduler, Docker, or raw rows.

The completed 2026-08-18 UTC bridge receipt is
`D:\thericher-v2\model-artifacts\data-receipts\norgate-host-readiness-bridge\bridge-norgate-host-readiness-20260818T230439Z.json`
(`sha256:20cf9e2954bb567fa31a54d58cde6d61b50be0d86b4b345261e14136c1aa521c`).
It is `input_unavailable/local_api_not_ready`: the host runtime is available,
but catalog/update/root categories are `not_checked`. This does not diagnose an
updater, subscription, vendor-access, or rights condition and does not permit a
daily capability retry or D1 pilot. Reattach the receipt with
`read_norgate_host_readiness_receipt`; do not rerun this completed objective.

### Norgate Trial Host Readiness Reconciliation

The completed reconciliation is a distinct local-host diagnosis. It reattaches
the exact bridge before one isolated-client status call, then examines only a
fixed updater installation marker and an in-memory process marker when that API
is not ready:

~~~powershell
D:/thericher-v2/host-runtimes/norgate-python/Scripts/python.exe `
  scripts/run_norgate_trial_host_readiness_reconciliation.py `
  --run-label <unique-label>

D:/thericher-v2/host-runtimes/norgate-python/Scripts/python.exe `
  scripts/run_norgate_trial_host_readiness_reconciliation.py `
  --run-label <unique-label> --verify-only
~~~

It prints and retains only categorical status, reason, recovery, and hashes.
It does not read source rows, configuration values, credentials, or database
paths; it does not invoke a network route, updater, KIS, Docker, broker, or
model/GPU path.

The completed norgate-host-reconcile-20260820-r1 output is
input_unavailable/local_api_not_ready_updater_not_observed
(sha256:5c79a0430b789709df50136f6a1ea999836072c7483f6f1598fc80d43bb924ac).
Its validation reattached the prior bridge
(sha256:20cf9e2954bb567fa31a54d58cde6d61b50be0d86b4b345261e14136c1aa521c)
without reinvoking the host. The only next local prerequisite is to install and
run Norgate Data Updater; this is not a trial-rights, data-capability, or
research-input conclusion. Do not poll it or run the date-indexed probe until a
fresh bounded readiness result says ready_for_date_indexed_probe.

### Fixed Market-Data Contract Inventory

For the six predeclared source classes, run the source-safe inventory once with
an immutable label:

```powershell
uv run --extra dev python scripts\build_market_data_contract_inventory.py `
  --inventory-label <unique-label>
```

It checks only allowlisted directory/file metadata and hashes existing
source-safe receipts. It never reads or hashes market rows, loads credentials,
uses the network, calls KIS/a broker/Task Scheduler, or creates a model, GPU,
Paper, or promotion path. Reattach only with
`read_market_data_contract_inventory`.

The completed receipt is
`D:\thericher-v2\model-artifacts\data-receipts\market-data-contract-inventory\market-data-contract-inventory-20260819-r1.json`
(`sha256:17f2b0f7cf7e16a61b2c2006e806d6e9c8e6135d41e63bf073fe4cdd2fb55632`).
Its six categorical entries produce no predictive, Paper, or GPU consumer;
missing evidence remains scoped `input_unavailable`, never a global hold.

### Norgate Date-Indexed Capability Probe

Run this only after a distinct host-readiness result is `ready/one`, with the
isolated Windows host runtime that contains the locally installed Norgate
package; it is intentionally not a project or Docker dependency:

```powershell
D:\thericher-v2\host-runtimes\norgate-python\Scripts\python.exe `
  scripts\run_norgate_trial_daily_capability_probe.py --run-label <unique-label>
```

The command writes a precommit, aggregate receipt, and trial-retention marker
under `D:\market_data\us_equities\norgate_trial\daily_capability_probe`. It reads
no `.env`, credential, KIS, account, broker, or Docker path and prints no raw
OHLCV. A `qualified_for_offline_research` result verifies only the frozen
three-case field response. It does not establish vendor availability time,
adjustment or corporate-action semantics, model eligibility, GPU work, ranking,
Paper behavior, or a full-union panel.

### Norgate Date-Indexed D1 Pilot

After reattesting a qualified capability receipt, materialize the three frozen
cases with the same isolated Windows host runtime:

```powershell
D:\thericher-v2\host-runtimes\norgate-python\Scripts\python.exe `
  scripts\run_norgate_trial_daily_pilot.py `
  --run-label <unique-label> `
  --capability-receipt D:\market_data\us_equities\norgate_trial\daily_capability_probe\probe=20260801T152000Z-norgate-trial-daily-capability-r1
```

The runner fingerprints the local Norgate database build, requires it to match
the receipt, writes a new precommit before source reads, and stores raw D1,
membership, and listing CSVs only under
`D:\market_data\us_equities\norgate_trial\daily_pilot`. Its JSON output is
source-safe: status, hashes, package, limitations, and scope only. Reattach the
result using `load_attested_norgate_trial_daily_pilot_bars` for completed D1
`Bar`s and exact source-date state lookup. Do not treat that lookup as PIT
availability, a static-universe replacement, model/ranking/GPU/PnL evidence, or
a Paper/KIS route.

### Source-Partitioned D1 Eligibility

To recompute and reattest the current source-partitioned D1 eligibility receipt,
run:

```powershell
uv run python scripts\materialize_source_partitioned_d1_liquidity_eligibility.py
```

It first reattests the source-scoped universe, then reads each ETF stream
independently and the frozen NAS panel separately. It writes or reuses the
canonical external receipt under
`D:\thericher-v2\model-artifacts\data\d1-liquidity-eligibility\v1`. The
receipt stores only source hashes, fixed thresholds, categorical eligibility,
and limitations. It performs no KIS call, credential read, network access,
broker action, model fit, or GPU work. The narrow D1 proxy is not a claim about
intraday liquidity, ranking, model quality, fillability, or Paper eligibility.

### ETF D1 Trend-Regime Control

To run the fixed source-local ETF D1 falsification control from existing local
caches, use a unique external label:

```powershell
uv run python scripts\run_etf_d1_trend_regime_control.py --run-label <unique-label>
```

The command reattests the source-partitioned D1 eligibility receipt, then opens
QQQ, SPY, and IWM independently. It applies only the completed-D1
`close > SMA50 and SMA20 > SMA50` rule, enters at the next open, exits at the
following open, and compares that fixed non-overlapping cadence with
time-matched always-long local-paper replay. It writes only source-safe
precommit and summary JSON beneath
`D:\thericher-v2\model-artifacts\etf-d1-trend-regime-v1`; no raw bars, features,
credentials, broker payloads, checkpoints, or replay event log are persisted.
It is offline with respect to KIS and makes no model-selection, GPU, Paper, or
live claim. IWM's source-limited history remains mandatory.

## Legacy Evidence

Terminal metadata-only KIS probe/capacity-map scripts have been removed from
the executable surface. Their external summaries remain historical evidence,
but they do not restrict current collection, scheduling, raw retention, or
paper execution.

## Tiingo IEX r1 Source-Isolated Runtime Integration

The completed Tiingo IEX M5 r1 integration is a reproducible runtime check, not
a predictive campaign. It runs only the pinned external r1 snapshot through the
networkless `research` service, first with `--phase cpu` and then once with
`--phase cuda` after CPU completion:

```powershell
docker compose --env-file .env.example --profile research run --rm --no-deps `
  research python scripts\run_tiingo_iex_r1_representation_integration.py `
  --phase <cpu-or-cuda> --run-label <new-label> `
  --snapshot-dir /app/market_data/us_equities/fixed_etf_intraday/canonical/tiingo_iex_5m/snapshot=2026-07-19-tiingo-iex-5m-r1 `
  --market-data-root /app/market_data --artifact-root /app/model_artifacts `
  --repo-root /app
```

The loader reattests pinned manifest, raw-source, and compressed-artifact
hashes, then compares the gzip payload with the exact canonical CSV rebuilt
from the raw sources. The payload comparison is portable across zlib encoders;
it does not rewrite the snapshot. The receipt contains only source hashes,
aggregate window geometry, architecture identities, categorical completion, and
memory cleanup. It has no network, token, KIS, broker, return/holdout, loss,
prediction, raw-row, or retained-weight path. Do not rerun or extend this
closed lineage to select a model or feed Paper.

## Recovery

At a task start, after interruption, and before trusting a checkpoint:

1. Inspect active processes, cache indexes, and current external state.
2. Reattest input, snapshot, manifest, dataset, checkpoint, and output hashes.
3. Classify each job as `resume`, `restart`, `reconcile`, `complete`,
   `unrecoverable`, or `operator`.

For local simulation, the event log is authoritative. For KIS Paper, reconcile
against broker facts before replacing an unknown submission. A recovery fact is
not a reason to introduce a new report or approval gate.

The intraday collector automatically removes an explicitly marked legacy
`candidate_batch` conflict from active index state while preserving its
immutable artifact. Do not edit the index, revive that artifact through orphan
recovery, or create a replacement scheduler: the next owned collection retries
from its normal cursor scope and continues independent targets in the same
cycle.

A retained-cache conflict in the fresh head cache is different: use only the
installed head/session-capture quarantine path above. It keeps the old raw
artifact immutable, rejects the conflicting response, and waits for the next
fresh provider page rather than silently treating a newer observation as a
revision of a completed bar. The shared index contract fails closed for a
malformed quarantine identity, and persisted collection scope prevents a
historical terminal page from becoming a quarantine target.

## Verification

Run at every bounded goal boundary:

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

An isolated role package committed during an active company objective is not a
goal boundary by itself. Run its focused changed-path tests, relevant Ruff,
Compose parsing when Compose/runtime wiring changes, and `git diff --check`;
reserve the full authority command for company-objective integration, a changed
shared runtime/control root, or an explicit current-goal requirement.

The focused serial group covers the changed production and contract paths. The
parallel command is the full-suite authority: it must exit zero, use a fresh
isolated child beneath local non-reparse `C:\trpy\runs` when available,
otherwise `D:\trpy\runs`, and retain the expected test/skip cardinality. Fast
feedback and authority runs share a cross-session `Global` mutex. Authority
mode checks both known C: and D: managed roots for surviving workers/leases,
even when the preferred drive changed. It does not allocate or delete content
under the non-selected root. It fail-closes for a held helper lease, active matching Python worker, mutex
conflict, unreadable active-process probe, mismatch, nonzero exit, or retained
current-run temp root. An inactive retained sibling root is diagnostic residue,
not a blocker for a new isolated run; the helper does not recursively remove
it. It verifies the resolved parent, active child, and every current-run
descendant before cleanup. Legacy direct `C:\trpy\r-*` roots remain outside the
active root and are never moved or deleted by the helper.

### Fast Local Test Feedback

For repeatable Windows feedback between goal boundaries, use:

```powershell
.\scripts\run_parallel_tests.ps1
```

It runs the same suite with up to eight `pytest-xdist` workers (bounded by the
host CPU count) and file-level distribution. The helper gives each run a short,
unique base temp path beneath the shared local `C:\trpy\runs` root when it is
available, otherwise `D:\trpy\runs`; this avoids Windows worker-path length
failures, uses this host's measured faster NVMe scratch drive, cleans a
successful run's private temp path, and leaves a failed run available for
diagnosis. It is not a market-data or model-artifact root. Override the worker
count when needed:

```powershell
.\scripts\run_parallel_tests.ps1 -Workers 4
```

On 2026-09-22, C: had 245.5 GiB free and was NVMe; D: was SATA. Alternating
100 x 4-KiB `Flush(true)` probes under the active workload took C: 79/67 ms
versus D: 21,468/20,260 ms. The unchanged optimized depth-dispatch test passed
in 3.43s on C: versus the earlier 316.40s D: run. These are measured runs,
not an unconditional speed ratio for every test. They replace the old
near-floor C: preference for D:. Recheck capacity/performance if that premise
changes. No market-data/model-artifact path, test assertion, worker count,
mutex, lease, reparse check, or cleanup protection was weakened. A subsequent
cross-root regression covers an orphan on the non-selected drive, held lease,
missing/inactive roots and failed process probes. The final helper's focused
authority run passed all 11 helper tests with cleanup in 7.04s.

It has no KIS, credential, Docker, market-data, or artifact access. The
2026-09-22 weekly full serial diagnostic passed 3389 tests/19 skips in 1621.44s;
the same snapshot passed the eight-worker helper in 304.13s. The later nine
cross-root regression cases separately passed with the final helper. The final
suite, including those cases and 24 learnability tests, passed 3422 tests/19
skips in 289.24s with clean-root cleanup. On
2026-07-31, the earlier serial baseline was 1769 tests/14 skips in 806.07s,
with matching four/eight-worker counts. Run serial `pytest -q` at least weekly
and before a material live-route
or execution-recovery promotion. It is a compatibility diagnostic rather than
a routine goal-boundary hold.
