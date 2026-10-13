# Data Stateboard (시장데이터 담당)

Current projection 2026-10-14 KST; policy AGENTS.md; ONE goal NEXT_CODEX_GOAL.md.
Market data D:/market_data; artifacts D:/thericher-v2/model-artifacts.

## Current Ownership

Data owns market data/availability; Execution owns accounts/orders. No new Data
API/task work now. Parent reports SPY r2 EXIT closed19:04:21UTC:1sell/23GET/1token,
baselineflat confirmed and observer restored; not independently reattached here.
Next owned G107 due Oct13 21:50UTC (Oct14 06:50KST); waits stay worker-owned.
Input expiry never blocks persisted original-contract unknown-intent recovery.

## Exact Evidence Roots

ETF = D:/thericher-v2/model-artifacts/data/current-paper-etf-input-refresh-20261014-v1
ETF_RUN = ETF/runs/786a7b63f8c34672b27dbb4ac92f6df2
RAW = D:/market_data/us_equities/kis_paper_private/current-paper-etf-input-v1
G107 = D:/thericher-v2/model-artifacts/data/kis-peer-relative-momentum-prospective-preparation-v1
R3 = G107/capture-r3
DEPLOY = R3/deployment/835d74554a404f1382a4572b3ebbe716
Roots plus exact relative names below resolve immutable evidence; no latest selection.

## Actual Paper Input

Oct13 17:45:00.231738..17:45:16.434015UTC:1token POST/12daily GET/16.2023s,
0account/order/live. SPY/AMS,QQQ/NAS,TLT/NAS,GLD/AMS each253 completed sessions
2025-10-09..2026-10-12; currentUSOct13 excluded.3pages/name,2identical overlaps/
name deduplicated,45outside-window rows/name excluded; no missing imputation.
SPY baseline2 first available17:45:02.678357UTC, raw FI02.638189UTC; never
consumer-now or backdated. Snapshot publication clocks for every ETF are in
ETF_RUN/outcome.json (5dc5d35e...); exact manifest/raw SHA refs, raw bytes only RAW.
Original ETF/worker.py (d07b4f65...), ETF/recipe.json (5ccc2ee6...),
ETF/DataMeta.json (d06d074b...)
and prior readers/tests/receipts stay immutable. Owner released/client exited.
ETF_RUN/reader-verification.json (0b39d293...):13actual offline reader checks.
ETF/postpublication/actual-validation.json (463eb1df...):253x4+baseline2 validated;
request counts/routes/clocks, calendar/dedup/positive OHLCV/availability/age bound.
10prelaunch+5reader SYN; details/counts/source pins remain in those existing artifacts.

## Reader Contract

Use ETF/archive_reader.py (6fd0a9f6...) for replay, not frozen worker/consumer_reader
whose recipe_check/calendar(now) wrongly expires archived reads on US-date rollover.
API read_context(exact_manifest_path,exact_manifest_sha256,required_count=2|21|253,
recipe_sha256=5ccc2ee6...,as_of_utc=optionalUTC); verifies original code/recipe/raw/
manifest and retained253calendar420dc011..., never calls current recipe/calendar.
Returns private/repr-hidden observations with explicit provider_date from CSV,
unchanged Bar, actual first_available_at_utc and descriptive age (even negative).
Current-intent freshness/session eligibility belongs evaluator, not archive reader.
Bar.start_ts is NOMINAL provider-date UTC-midnight label, not a NY session instant:
Oct12T00Z converts to NYOct11; use explicit provider_dateOct12 without retimestamping.
Recipe.close_utc is calendar metadata, not observed provider close. Source-observed,
uncertain provider finality, MODP0/corporate actions unverified, not PIT/total return.
Fresh isolated namespace: batch-read Data FIRST; after native unload import
RepoContracts and copy unchanged fields into RepoBar/Timeframe.D1.1014 copies checked.
ETF/postpublication/adapter-order/read_first.json (26bafd5a...) and
ETF/postpublication/adapter-order/repo_preimport.json (b8c39baf...);2focused pass.
Direct old worker preimport conflict
occurs AFTER1packed-cache read/hash, BEFORErow decode/credentials/network, not all IO.
ETF/postpublication/archive-reader/verification.json (7f44607d...):5actual today/
tomorrow canonical replays identical;14focused pass/hash/type/session kills,0provider.
No current-source requalification, forecast rewrite or novel label/availability claim.

## Retained Faults

ETF/postpublication/original-scope-failure.xml:old ETF/test_worker.py (bb35e4f8...):9pass/
1fail because prepublication cache/runs-absent assertion sees legitimate published
data. No deletion/rewrite. Isolated copied SYN suite patches MARKET to tmp root;
ETF/postpublication/isolated-focused-final.xml:17pass including date/age/phase kills.
pacing_measurement_phase_mismatch: early Boundary-check min1.2500252s precedes
variable source recheck/publication; published pre-opener marker min1.245146s,
5gaps below1.25. Exact wire-start pacing UNKNOWN, not guaranteed; no invalid bars/
provider error inferred. Future successor may move final pacing after recheck;
no frozen patch/retry now. Details/reproducer in actual-validation.json above.

## G107 Owned Future

Five R3 Actions applied17:14:18UTC, preserved pythonw/principal/triggers/settings
and original six21:50..21:55UTC windows. Remaining datesOct13/14/15/16/19;
Oct12 unchanged/incomplete. Last readback Ready; real capture/principal run not
observed here, pages/ETA unknown. Source-ready is not capture success.
R3/source-release.json (5627e32b...), R3/bundle.json (b80fb7c3...),
R3/job.private.json (7464cb28...):
35pins/28package files/26native origins;32copied R2 dependencies unchanged, only
gate08fcc345... replaced; narrow entry qualification changed, safe_reader unchanged.
R3/independent-check.json and R3/focused.xml (53pass); DEPLOY/outcome.json (91ed2050...),
DEPLOY/fresh-readback.json (e4a585fb...);11private rollback XMLs/non-Action hashes exact.
R3/read_first_capture.py needs caller-pinned exact launch path+SHA; v3 started/
preflight/outcome schema, no latest/raw output or retrospective prospective closure.
Original R1 first exception unobserved; mutable-pin diagnosis is reconstruction.
Measured lockf/flock cross-OS fault is separate. New token-only atomic directory+
OS lock coordinates new participants, not all legacy writers; schema/300s unchanged,
state atomics only (not HTTP), no TTL reclaim; explicit proven-dead recovery only.
Observer240s can starve Data300s fresh-token floor: Parent coordinates named slots,
not a global permission hold. Existing clients/token lifetime are separate.

## Retained Input Support

G107/verification-1791910057033/verification.json:exact daily512 manifests/packed
rehash and masks. Prior35 old800:342695pairs/765slots; later71:18162pairs/36slots,
earliestAug17; first14later actions lack35 prior bars without a new source contract.
Current21 supports504scalar RSI14 names,0prior35; trailing20 RSI sequence only7
initialized positions. Seed-only minimum34bars, prior35 supports20, not convergence/
TA-Lib equivalence. Existing raw_context ABI only21; no splice/imputation/old trial rewrite.
131ee1fe908... superseded unfinished;130target f4281218.../intake1534... preserved,
result rejected. Existing ab65/G107 ownership separate from Paper; no wholesale
collector/head/forecast/cursor restart. No source/cache/test changes in this MD refresh.

Everything below is frozen historical evidence, not current dispatch. Old
"no manual invocation" study restrictions apply to that retained attempt only.

## Retained Evidence

Goal100 COMPLETE ff5b936b... at A/execution/
kis-five-session-successor-observed-fee-reconciliation-v1/integration-evidence.json.
Source contractba204bcd.../canonical baseline25 pass; independent R2d9cc3e0c...
six groups pass,25 original pins unchanged. Original5/6 failureea627198... found
valid enriched replay rejected by wrong _advance ABI, now fixed in one call.
Source/currency/job/control/archive/cohort/cumulative fill/clock/coverage bindings
remain exact; explicit zero needs complete evidence. No acquisition/private
reads or actual fee/finality/settlement claim. Actual113f code/SYN result and
host cleanup are linked in closure; honest-host evidence, not provider proof.
Current assignment comes only from NEXT_CODEX_GOAL.md, not this closed study.
Goal101 source COMPLETE14fcc377.../held geometryc45e507d...,41 author/Parent
focused pass;13 reused pins unchanged, no packed read/numerical fit. Reuse
d83db2a1... input ABI, old800/later71 exact manifests
fd559b22.../1eaebbc3.... TRAIN134/DEV15/later9 episodes yield nominal536/60/36
held decision slots, not observed complete samples. Labels OPEN(t+1)->OPEN(t+2),
force terminalOPEN e+5; TRAIN terminal691 precedes DEV decisionCLOSE719.
Future mutation cannot alter prior selection/context; no future-qualified
missing-payoff deletion. Packed bars not rehashed by this planning audit.
Independent Engine input reviewcbbb707a...6 groups pass/28 source-metadata pins
unchanged. Interface wording excludes marks but code correctly includes
*_marks_indices in the frozen split; no scientific-row rewrite.
Goal101 CLOSED/technical failed44522a70... after actual3 fits, no result tables.
Typed later Panel71 ABI mismatch reproduced, actual first failure unknown.
Goal102 CLOSED/source-SYN3c98f73f...; independent typed reviewea713efb...6
groups passes/28 source-metadata pins unchanged, complete80/50 SYN marks.
No packed-row/actual model/runtime/finality claim. Goal103 same-input technical
reexecution CLOSED/rejected7a1cb985... does not become fresh data or replication.
Source10319f2b49c...4 groups passes/34 pins stable, no packed reads. Actual
runtime result5c94f579... has36tables130marks; no Data quality promotion.
Next input source audite4fe1834... at A/data/
kis-held-exit-causal-development-technical-reexecution-v1/next-input-r1/source-readiness.json
re-retrieves official Qlib definitions: OHLCV-only subset possible, VWAP absent
from these frozen inputs, not necessarily unavailable from every KIS endpoint.
First later decision20/current21 provide5/10/20 history;30/60 may need31/61bars.
No early-mark dropping, splice, interpolation, acquisition or window selection.
Source geometry71 context versus50 evaluation marks stays distinct. Next ONE
goal uses a fixed5/10/20 feature basis; this does not expand provider ownership.
Goal104 raw-context source COMPLETE a88cc7b3... at A/data/
kis-price-volume-basis-held-exit-development-v1/context-r1/release.json;
sourcee175fa79.../19 author and Parent19 SYN pass, no packed market reads.
raw_close_volume_context accepts explicit actual Panel/Panel71 registry and
the same caller's bound metadata/Data module class identities. d=e+age-1
returns raw CLOSE3/VOLUME4 rows d-20..d, never normalized-token substitutes.
Missing values remain missing; Data extraction does not choose eligibility or
features. Engine owns domain/paired support and exact source binding before fit.
Parent actual104 network-none runtime consumed the same old/later files;
result575d521d.../closure04f16af6... rejects15of36 model checks. This is not new
data, physical availability, PIT/finality or a Data quality promotion. Data-role
source review did not independently reproduce raw numeric rows. Existing
owners/due/coverage and limitations unchanged. Closed105 reused the same causal
entry context and source support; no acquisition, universe or window extension.
Actual result43e5ad42.../closureaa330c36...:1340 selected TRAIN rows/134complete
cohorts,24tables130marks, no new data/PIT/finality/corporate-action promotion.
Next106 uses same512 prior21 bars for a leave-one-out eligible peer statistic;
Data standby unless exact support/clock issue, no acquisition or universe gate.
106 CLOSED b00e112b.../resultf08beb14...:30development conditions pass on the same
seen inputs; not Data quality/PIT/finality or fresh replication. Next107 binds
existing current21 manifest/packed bytes and actual captured/archive clocks,
official six-session calendar, unchanged prior-only forecast before Oct12 OPEN.
Reuse current_input.py36bfbdac... build_frame explicit current clock/512 axis;
cursor792a1d07... startOct10 19:16:58UTC is not completion/availability evidence.
107 preparation COMPLETE5e164d61...; capture174141f7.../reader7707234d... and
job a7c621dc... bind actual forecast fd47fe89.../union13. Six Data-only tasks
installed/readback08668ca4... for Oct12..16/19 at21:50..55UTC. One client,
max2daily pages/name/1.25s measured pace, durable date cursor/whole300s.
Accepted/failure pages0/0 as no opportunity has run; next_dueOct12 21:50UTC,
remaining accepted pages/ETA unknown, recovery resume exact date. Required
raw support survives zero scale; missing date stays incomplete, not cash.
All468code pins stable/26loaded module origins pinned; no manual client/API run.
Original13 owners unchanged. Future economic result not observed.
Parent retrieved exact view/manifest.jsona0bb1864.../10584rows; declared packed
view/bars.csv.gz921380f5... now rehashed by107 freeze. Sciencebc32566d.../
calendar e0efd4b6... binds27 official dates/21prior+6forward; Parent parser
bridge6 SYN pass, not actual packed decoding or future capture. Actual source string
Oct10 19:28:42.228861+00:00; default PowerShell JSON converted display to+09,
not a source offset. DateKind String reattests exact source without conversion.
The instant was unchanged in the prior projection. Actual forecast formedOct11
16:02:06.573427UTC before next OPEN, not Friday decision availability,
response-level finality or physical OS proof. Independent metadata receipt
b57b9cea... supports clock/source links only, no independent private-body parse.
108 preparation COMPLETE61ee85b1...; source5b5a79d8.../release2a7f44af...
10 SYN plus5 composition pass. Actual preflight4af21579... consumed exact
SPY207824/QQQ210482 M1 bars once,8.15s;251official sessions including early
closes. TRAIN125/1488admit,DEV63/755,later63/744; selected OPEN/held-context
shortfall0. Chronological axis2aaeae79..., no future-complete intersection.
Source/input unchanged/child reaped;0labels/fits/metrics/acquisition, no PIT/
finality/physical availability or fresh-holdout/KIS parity claim.
109 COMPLETE/rejectedfe3d5e23.... Iterator2cdf29f3.../release30955295... reuses
same parser/axis/geometry;8 Parent focused pass. Actual single study consumed
the exact inputs with7440TRAIN held rows/755DEV/744later episodes, no new data,
source/split/admission change or quality promotion. Future107 unchanged.
Data next-direction source/metadata geometry review is daily512/5day support,
not new acquisition or an independent input-quality approval gate.
Source audit found older4-ETF sector strength/21-rebalance and covariance
allocation already exist; next stock-level beta selection is a bounded new
comparison, not a globally novel signal. Daily volume is only a capacity proxy;
inactive retail caps would not justify raising capital to force an experiment.
Intraday source-metadata audit: SPY/QQQ each25 dated regular390-minute timestamp
sets,2026Aug28..Oct2; historical collection does not prove decision availability.
Exact indexes M/us_equities/kis_paper_private/intraday-dated/
qqq-20260910/v1/index.json52fef8d3... and spy-20260930/v1/index.jsonba175be3....
FirstRate receipts A/data-receipts/firstrate-free-intraday/
firstrate-free-intraday-source-local-normalization-v1.json374fc885... and
firstrate-free-intraday-source-local-window-preflight-v1.jsoneb88b4a4... report
SPY207824/QQQ210482 bars and105872/108854 contiguous120-minute windows.
Raw bytes/values, paired session intersection, forward labels and complete
sessions were NOT revalidated. At most25 KIS session blocks, not independent
minute examples; effective sample unknown. Next-boundary preparation may check
chronological session splits and context/target overlap, not claim PIT/finality,
fresh holdout or training readiness. This metadata work does not hold106.
Goal99 COMPLETE/rejected879bb037... at A/research/
kis-stock-joint-entry-continuation-policy-development-v1/integration-evidence.json.
Actual1CPU2CUDA/35of64 fixed checks failed; no new data or quality promotion.
Independent Data reviewa6a12a05...6 groups pass; source limitations unchanged.
Goal98 COMPLETE c6e08a27...; Data evidence below retained.
Goal99 input preparation COMPLETE5d85f8b2... at A/data/
kis-stock-joint-entry-continuation-policy-development-v1/data-r1/input-preparation.json.
Sourced83db2a1.../23 author and Parent23 pass0.43s, Ruff clean. New decision
equals prior official CLOSE;21 completed bars provide20 feature steps, next
OPEN executes. Old08:30 loader clock remains historical metadata, not newtime.
Full finite TRAIN label support must end before DEV decision; strict raw-context
nonoverlap is optional descriptive geometry, never an added research gate.
Packed hashes linked from metadata, not independently rehashed by Data review;
Parent's later exact-bound runtime consumed them. Neither proves PIT/finality.
Data source/SYN complete4f2e1d64... at A/data/
kis-five-session-successor-owned-accounting-v1/data-r1/source-release.json.
Producer30e0ec11.../plan e24db6c8...;45 tests pass0.69s, Ruff/format pass.
Dynamic exact retained cohort/Oct19..23 close marks, source/hash/date checks;
economic20:00UTC distinct from physical [20:25,20:35) reads/archive.
Missing/failed/partial source stays slot_unknown, never latest/zero/finality.
Actual-default G97 job374/controla9/exchange337 image SYN passed3.951s;
independent bridge6 groups86c59e67... pass. Pending coded SYN stays incomplete,
not qualified marked PnL, actual calls/PIT/finality or future input evidence.
Independent review10f73760...:6 groups pass,13 pins unchanged; no actual calls.
No universe/backfill/model change.
Goal98 finite accounting firstOct20 05:25KST; existing Data/shadow owners unchanged.

## Existing Input And Owners

Current21 Goal82 is CLOSED only for its exact scope:
M/us_equities/kis_paper_private/stock-five-session-current512/v1/goal82-20261009/
cursor.json.512attempts/511accepted/1rate_limited;504full21/8empty,
10584rows/246eligible. Manifest a0bb1864.../packed921380f5...,707.150s;
minimum delegate gap1.250026s. Remaining0/next_due null, not global exhaustion.
Source A/data/kis-stock-five-session-current512-input-preparation-v1.
Current21 is inference context, not future five-session labels.

Existing ab65 owner A/data/kis-stock-prospective-pair-owned-endpoints-v1:
thericher-kis-data-prospective-pair-ab65b62bdda00246-entry/-exit.
42 peers, next_due Oct12/19 21:40UTC (Oct13/20 06:40KST).
Retained cursor0/accepted0/failure0/remaining42/ETAunknown/not_observed.
One client/token;1s market-start/300s fresh token; no manual launch or scope change.
Goal90 five-close capture belongs to Execution, not this cache.

Old512 M/us_equities/kis_paper_private/daily-nas-broad512/v1/goal77-numeric-recovery-r2:
800dates/360686rows/391full/121sparse, fd559b22.../409fd7ad....
Later512 M/us_equities/kis_paper_private/daily-nas-broad512-later/v1/
fixed512-20260728-50sessions-r3/view:71context+50 already-seen targets,
1eaebbc3.../d436ab4e.... Neither panel is fresh holdout.
Trio SPY/TLT/GLD2686 OC dates; SPY/GLD4813; M1SPY/QQQ25 complete paired sessions,
Oct7 incomplete. Original128/800/87974 and separate f78/remainder unchanged.
Exact earlier source contracts/cursor facts remain in RUNBOOK/Gita81a1ae.

## Limits And Recovery

KIS private retention is standing-authorized; keep raw bytes M, artifacts A.
Current-listing/nonPIT/raw-action/nonTR/revised-value/nominal-availability
limitations narrow claims, never block independent research or Paper.
Tiingo Starter/Trial applicability unresolved: no new acquisition/numeric study.
Ended Norgate trial off; FINRA/FRED uncertain rights are not fallback permission.
Preserve D:15% (fresh task-start40.05%, C:24.99%).
Recover exact plan/cursor/receipt identities, not latest-file/cache-time inference.
Changed source or missing input yields scoped unavailable; parent integrates.
