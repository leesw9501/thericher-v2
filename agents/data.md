# Data Stateboard (시장데이터 담당)

2026-10-28 KST. A=D:/thericher-v2/model-artifacts; M=D:/market_data.
Parent owns shared MD/Git. Roles/MDs are memory, not running-process proof.
Closed detailed history: Git158bd51a and exact immutable consumers below.

## Existing Useful Inputs

| Input | Evidence / limits |
| --- | --- |
| KIS20 long daily | Sourceb7fd03a8;90,819canonical MODE1 rows at M/us_equities/kis_paper_private/current20-daily-long-history-capture-20261017-v1. Missing8,761keys retained, per-symbol range differs. |
| NVDA mode check | current-kis-adjusted-daily-history-20261028-v1 Consumer/f17ce4b4:1POST4GET0retry;100old dates/400OHLC exact match. Reuse history, no duplicate1110GETbulk. Not allCA/TR/PIT/finality. |
| Existing49ac | CONFIGacc496 ALREADY references that exact KIS history, not FirstRate. Same producer36d6/current F3 definition; no first-KIS-training/realignment story. |
| Current coherent head |16f2:20GET1POST/2000rows throughOct27; Source3b474a7d F3 17x20x18/allknown/PUBLISHEDa6b56a3f20:45:57UTC. Current model forwards already consumed. |
| Frozen minute corpus |0dd26b49/Manifest0593fb00:33common sessions; FIT882/INNER252/LASTDEV252, QQQ target/SPY context/C120H60. PRICE endpoints only, not full-minute DD. |
| Oct19 gap |QQQac536477+SPYa7cb14a8 each1POST4GET/480rows/390RTH; closed, separate captures; current33 unchanged. |
| Sep15 probe |current-kis-september-intraday-seek-20261028-v1:1POST2GET/emptyboth. Exact cursors only, no whole-source/retention-floor conclusion. |
| Other existing minutes |Sep28QQQ/SPY390each later independently verified; skipped, not newly acquired. Exact cache-manifest refs in recent-core job. |

Historical/currenthead overlap1,860keys has NOT been numerically reconciled.
No silent splice/rescale/overwrite or missing-data imputation. A later complete
window need not require390whole-day bars, but actual required path must exist.

## Wider Chronological Corpus Ready

Hypatia produced current-long17-wide-chronological-packets-20261028-v1/READY.json.
Actual iteration4 Source28c8cbe941d2ab2e527934a9b1037e5ee4ded50228c46b33c0586bb7bf0d5cdc.
M/us_equities/research_inputs/current-long17-wide-chronological-packets-20261028-v1.
Same-history-only/F3 17x20x18, global e%5==3/H5 raw SIMPLE.
FIT2015..2022, INNER2023..2024, DEV2025..Oct9_2026.

| Role | Scheduled | Endpoint eligible | All five closes |
| --- | --- | --- | --- |
| FIT |402|354|352|
| INNER |99|83|82|
| DEVELOPMENT |89|89|89|

NaN/known masks retained, no future-label-driven feature selection.
2970required frames reused/5computed. Real native Ridge/cold and one actual
projection/saved independent verify passed,64inputs unchanged/ownedCIDs closed.
train/{FIT,INNER}/{features,targets} separate from development_features and
development_outcomes. Engine fits mount train only, not raw/all payload root.
Typed ABI/consumer.py in iteration4; original11/15 hardcodes are not the new ABI.
Data partition1200/3600, corrected conservative upper848.9s; family earliest
05:15UTC/hard09:15. Original launcher timezone bug/supplement retained;
four software iterations exhausted: do NOT rerun it or reproject completed data.
Fresh same-split control required; old controls trained on new DEV are in-sample.
Ruff was unavailable in worker. Parent's later frozen-source check found30
style issues (29E501/1E731), not PASS; no immutable-source rewrite/reprojection.

## Actual Capture Recovery / Next

Jason01a180f4-bdfc-73b2-8032-1b26eed55c66 owns
current-kis-recent-core-minute-capture-20261028-v1.
Finite six stocks AAPL/AMD/MSFT/NVDA/JPM/JNJ plus QQQ/SPY, recent dated cursors.
Original2700active/7200elapsed/max900GET/no wire retries. First attempt1POST0GET
closed because NEW fallback classified every Python as a collector. One actor
41504 maps to Engine native Source0ed; historical other actor remains unknown.
Parent authorized one additional POST for bounded successor inside old clocks/
remaining caps, preserving old failed debit. Do not claim running/success from
callback/oldcache skips. Final r2 Source5ee36f78/manifest185d1bf4:
1POST517GET/123newcomplete symbol-sessions/47,970RTHminutes/61,200retainedrows,
36oldcache-skips. Combined failed+newPOST2,0wire retries. Owned-time stop
2680.642845/2700, not provider floor. Root/Job/OS/token gate closed;
Parent26hashes0mismatch. No old cache/current33 mutation.
Unfinished-cursor classification0c247 completed; targeted recovery8d63c42f
then made37GET/1POST/0retry,4,440rows/3,309required timestamps/15intervals.
No old-root overwrite,240overlaps/0conflicts; root/Job/OS/cache/token closed.
Parent16refs0mismatch. AMD/QQQOct7_12:42 persisted; no identical new requests.

Guard lesson: Data admission scopes to actual cache/account/token collectors,
not all unrelated Research/Python/GPU processes. Reuse exact named/source/
argv collector matching, fresh actual Task/process/root lineage and token
atomic+legacy exclusion. No ready=True, genuine unknown-writer bypass, age
reclaim, request flood or company-wide wait. Sagan Source324182c2 is a qualified
collector-scoped example without the erroneous unmatched-Python fallback.

## New Pooled Stock Research Input

Tesla produced current-core8-c120h60-packets-20261028-v1/ACTUAL-READY.json,
Source1d4fae4a: one actual projection/cold PASS, six stock targets plus QQQ/SPY.
ONE C120/H60, origins11:30/12:30/13:30ET; RAW_SIMPLE/full60bar path.
FIT216/147eligible throughOct13; INNER90/87 Oct14..20; DEV90/90 Oct21..27.
Typed features[N,120,3,5] and target/path consumers physically separated by
role. Optional first-lag/flat-range masks stay unknown; required raw completeness
is past_complete, not all derived features observed. No price imputation.
Canonical start+publicationlag/entry boundary is offline assumption, not
provider finality, measured historical availability or live/Paper parity.
Original producer has Windows codec path: Engine must smoke exact actual
consumer/bootstrap before fits, not assume Linux portability from Windows cold.
Actual model training is Engine's separate contract, not Data READY evidence.

Window-level V2 is now READY865b1da8:
current-core8-window-complete-packets-20261028-v2/READY.json,
396same keys/FIT197/INNER90/DEV90eligible,53additional windows,0GET/0fits.
Oneprojection/4softwareiterations/cold+independent values/masks/source PASS.
No full390-session gate or imputation. Capture-incomplete QQQ/SPYSep29_11:29
and AMD/QQQOct7_12:42 remain unknown. V1/closed Engine families unchanged;
V2 is future input only, not an automatic refit or fresh independent sample.

## Current Monthly Input

Monthly source56429 READY95FIT/23INNER/21DEV, same retained KISb7/no newAPI
in that producer. Feynman closed after exact missing-key failure handoff.
Volta kernel8025a865 requires252official closes/251returns,17stocks+SPY/QQQ,
firstmonthlyOPEN to nextmonthlyOPEN (NOTexactH20), physically split features/
outcomes/roles. MissingQQQ is not required; causal eligiblemask/strict role
purge/retrospective availability limits retained. Native actual file/role/
consumer proof before payloads. Original source/packet bytes stay immutable.
Parent defines MODE1 adjusted-price-proxy analytics in normalized synthetic
units; do not invent corporate actions or claim actual nominal shares/PnL.

Parent endpoint recovery COMPLETE:
current-long17-monthly-daily-mark-recovery-20261028-v1/endpoint-only-r1/
QUALIFIED-FINAL.json SHA2db664cc,10keys/total10GET2POST0retry. Original q01
body reused, no repeated request. All10 strict OHLCV rejections remain due
to unused LOW faults; valid positive OC/exact shared OC comparison only.
Job/OS/cache/token positively closed; original156.18 included in310.833/600.
Initial SYN string-vs-Path caller defect preserved; corrected native3queries
shared one RAM client and retained strict rejects. Claude GO_WITH_LIMITS.
New monthly-open-close-overlay READYa167db6d/DELIVERY.json:
oneprojection/10keys20OC/120past-close masks restored; same95/23/21cohorts,
DEV unchanged. Native/cold/independent proof PASS,20source72packet files
unchanged;322.66/600active,2softwareiterations/launchfailure preserved.
Carson closed after direct Engine handoff. Only absent exact OC keys,
unchanged calendar/roles/causal eligibility; no strict Bar/OHLCV promotion,
future-completecase filter or original overwrite. Engine binds new DataVersion
before first compile. No API/fit/evaluation in this overlay.

## Scheduled Fresh Input

Installed thericher-current20-ridge-point-preparation-20261029-v1:
Oct28UTC20:10/Oct29KST05:10, Data20:30/whole20:40 hard end.
Source324182c2 ->0978 refresh ->5785 Ridge factory; readonly public point only.
Parentc5b0/plan722e/readback13PASS. No actual future point yet.
Existing quiet head/daily collectors stay intact. Fresh-session work precedes
backfill; storage15percent D floor/20percent warning. Quality limits constrain
claims/consumers, not unrelated Paper/research permission.
