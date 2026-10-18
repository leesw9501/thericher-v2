# Runbook

## Current Owned Runtime

Workdir: C:/Users/Public/Documents/thericher-v2.
A=D:/thericher-v2/model-artifacts; M=D:/market_data.
Follow AGENTS.md/HANDOFF.md/currentstateboards. ONE company outcome
current-nas-owned-model-paper-cycle-v1 remains unfinished owned exit.
Private Paper work is delegated, never KIS_LIVE_*/real money/paid/public work.
Do not print credentials/account/order IDs/raw bodies/prices/private amounts.
Do not rerun completed creators/installers/numerical fits just to refresh time.

| Owner | Current Runtime / Next Opportunity |
| --- | --- |
| NASmodel |Samefinite thericher-kis-paper-current-nas-model-20261015,image87697f8e;8retainedFULLfills, ownedexit>=Oct21USOPEN.|
| Newfixedensemble |thericher-kis-paper-current20-equalrank4-20261018,Ready/Enabled,image378f2034,31finitestarts/PT5M;firstOct19 15:10UTC=Oct20 00:10KST.|
| Nightly |thericher-kis-paper-daily-spy-session,image30433095,23:50KST;exactOct17 00:52recoverycomplete/all28terminal.|
| Goal97 |Distinctowner,entryOct19 22:30/22:40KST,exitOct24 04:50/05:00KST.|
| Current20RTH1m |Quiet06:50KST Tue-Sat,firstOct20;notobservedcapture.|
| D1marks |thericher-kis-paper-current20-shadow-d1-marks-20261020,07:30KST firstOct20,21finitevisits throughNov17;futureoutcomesUNKNOWN.|
| NEW8D1 |thericher-kis-paper-current25-new8-d1-marks-20261020,ReadyEnabled/21finite/PT15M/IgnoreNew/noDemandStart;firstOct20 08:00KST,lastNov17.|

All original bank/identities/request reservations/ownership remain. Newensemble
five desired .005-original-basis targets/<=.025 together inside SAME original
shared .10 envelope. Entry ONLY USOct19 until20:00UTC, no later re-entry/
backups/rerank/foreign adoption. Exit not beforeNov17 15:10UTC/recoveryNov20.
Twenty fully held RTH sessions+partialentry/exit, NOT research OPENparity.
No newensemble invocation/submit/fill yet. Model output is an untrusted proposal;
native fresh brokerfacts/risk/reconciliation still required before each effect.

Existing web monitor remains loopback http://127.0.0.1:8787.
No public exposure/UIredesign in this package; health is not fresh custody.

## Exact Runtime Bindings

Newensemble frozen repository/image/input:
A/execution/current20-ensemble-paper-deployment-20261018-v1/recovery-r1/
parent-deployed.json.
Image sha256:378f203475a794b089d44348f683e1073da92ac4180c1f3968ddcd89e6e9cc8a.
Source ca19a4991691152325bb2d143453bc08270454151ca872d63506122621df76e1.
A/execution/current20-ensemble-paper-runtime-20261018-v1 inputmanifest473a759d,
semanticbb77d43f,contractf66ee5fc,launchbindinge98bfda3.
Physicalpythonw C:/Users/User/AppData/Roaming/uv/python/
cpython-3.14.3-windows-x86_64-none/pythonw.exe,console0/hiddenchildren.
A/infra/current20-ensemble-paper-schedule-20261018-v1/final-binding-r3/
parent-idle-null-activation-1/installed.json.
Only one disabled Register then unusednativeNULL idlecalibration/Enable;
all249otherdefinitions unchanged. Do not rerun installer/input creator or use
superseded images353/launchbindinga7.

Newensemble publicreceipt/privateoffline reader:
A/execution/current20-ensemble-paper-outcome-reader-20261018-v1/READY.json
and RECIPE.json.6source/SYN groups+public-only Linux3.12 image378 smoke PASS;
private-phase Linux/result is NOT observed. After natural opportunity use its
exact run/source/image/time binding, named-owner quiescence and strict native
RO private parser. Never use observe()/strategy/collector as a reader.
Exact pending request takes precedence. Historical cumulative fills are not
newfill deltas; missing receipt/exitcode/timestamp is UNKNOWN, not success.

NAS public launch:
A/execution/current-nas-zero-quote-recovery-deployment-20261015-v1/launch/current.json.
NAS strict offline source:
A/execution/current-nas-owned-model-paper-readback-20261015-v1/r2/ready-parent.json.
Uses image87697f8e and read_native_model.py, not daily private parser. Bind exact
launch/receipt/input/image/source/time before current cycle/intent/fill/book.
Its73focusedcases reject journal-only/missing state/falseflat. Retained custody
does not imply a fresh broker balance or net PnL.

Nightly installed/final exact recovery:
A/execution/nightly-typed-recovery-deployment-20261017-v1/parent-installed.json.
A/execution/nightly-typed-recovery-deployment-20261017-v1/
native-reader-v2/parent-native-outcomes.json.
Exact current average-cost one-sell attribution:
A/execution/current-daily-gross-attribution-20261017-v1/fresh-current-r1/current-result.json.
RealizedGROSS positive for that linked daily sell, not model/global/netPnL.
Original23:50 failurecause remainsUNKNOWN; recovery does not prove codecausality.
Old reboot-recovery reader constants/old daily read_private_cycle.py do NOT
cover currentmodel/newensemble. Never reuse a frozen reader for a new profile.

Canonical private volume:
thericher-v2-paper-canary-private-acct-20261007-v1 mounts /app/private,
NOT /app/private/canary. A wrongly nested mount once hid the book; never recreate
or adopt apparently missing state. Private readers:networknone/readonlyexact
private+source mounts/pinnedimage/uniqueownedcontainer/typedcleanup, no credentials.
Fees/settledcash/netPnL stay unobserved without exact evidence.

## Source-Safe Inspection

Read-only Task facts, NOT invocation or fill evidence:
```powershell
Set-Location C:/Users/Public/Documents/thericher-v2
$PSModuleAutoLoadingPreference = 'None'
Import-Module ScheduledTasks
Import-Module Microsoft.PowerShell.Utility
foreach ($name in @('thericher-kis-paper-current-nas-model-20261015','thericher-kis-paper-current20-equalrank4-20261018','thericher-kis-paper-daily-spy-session')) {
    $task = Get-ScheduledTask -TaskName $name -TaskPath '\'
    $info = $task | Get-ScheduledTaskInfo
    [pscustomobject]@{
        task = $name
        state = [string]$task.State
        enabled = $task.Settings.Enabled
        next_due_utc = $info.NextRunTime.ToUniversalTime().ToString('o')
        last_utc = $info.LastRunTime.ToUniversalTime().ToString('o')
        last_result = $info.LastTaskResult
    } | ConvertTo-Json -Compress
}
```
Do not output Action arguments/private fields. Check actual owner/lease before
a private read/recovery. Scheduler Operational logging disabled; hash/time/marker
provenance assumes honest host, NOT cryptographic OS scheduler-origin proof.
No task-exit inference, latest-file discovery, foreground market/quotasleep or
manual future-Task replay. Preserve exact owned next_due.

## Current Research / Data

25new versions complete:6ranking+9ablation+4cohort+3recency+3full25(21CUDA4CPU).243ancestral
versions=156CUDA+87CPU incloneoldinvalid, not architectures/alpha. Training
leases released. Allocation81cells independentPASS/economicFAIL;new8transfer
21cells primaryFAIL/independentretainedPASS185pins.5+4+3futurechallenger actualforecasts
complete preOct19OPEN;21future outcomesUNKNOWN, no oldreforecast/Paperswitch.
Exact numerical roots/seals/failures/caps: HANDOFF/Engine/Steward boards.

FINALsource43379rows/9invalidgaps/1432missingsessions:
A/data/current20-universe-breadth-daily-capture-20261018-v1/
timing-recovery-r4/ENGINE-INPUT.json,manifest43aad063/readback2c096dd5.
535142lineagechecksPASS,493GET6POSTattempts;all9exactcursorsclosed repeateddate
2007Augboundaries, notglobalfloor. No more identicalolderprobes. Oldstudy binds
strict-valid-subset19555,transfer8414; no silent data substitution.
Failed dynamictiming wrapper produced0GET/1pendingPOST; three native SYN
support fixed wrapper, NOT actual recovery.1560/1500active overrun retained.
Do not rerun originalcapture/creator or reset timing/pending state.
Current25 fourfit/72cell actuals:
A/research/current25-training-cohort-development-20261018-v1/technical-r3.
Oldfailed0market root is not actual4fit result; no duplicate fit/forecast.
NativeSYN failures and explicit25rank mathrepair preserved; retainedreview
PASS507pins/72NAVs/12bit-exactcontrols,independentseal a55dc25d.
Fixed-recency COMPLETE:
A/research/current20-fixed-recency-cudnn-development-20261018-v1.
native-dtype-recovery-r2/FROZEN-ACTUAL8975efb5,3fits/18cells/bothprimaryFAIL
growthup/DDworse. NewGRUuniform39/best19,recency23/best3,actual110.13/67.54s;
INNERpat20/LR/bestrestore, not convergence/isolatedbackendcausality.
Complete current25-complete-history-fast-experts-development-20261019-v1:
FINAL43379source/old17rows-scalers-reference-4001dates exact;3fits HGB73best53/
GRU65best45/37best17, INNERpat20;81knowncells new8matchedFAIL/PASS/FAIL,
independentPASS150480checks/81bit-exactNAVs/42controls/791pins, sealdd885a57.
Actual/FROZEN-ACTUAL5facb63a/680pins, model-only
catalogca0ad8bb. Preserveoriginal415.775controlpathfailure; linkedunconsumed8
new8forwards/81firstreplays, no refit/old17reforward. Nextnew8prospectivepairs
fixedALLsixarms/zero fits, ACTUALv2firstwriteOct18 16:39:19.458487UTC/0d1512a9,
Parent48+16weights/hashchainPASS. V1sourceimportfailure0models/21.434s remains
UNAVAILABLE90d0ced6; informednewversionfamily2/2attempts closed. All-inworker
56.973/180 includesSOURCE15.050; accounting-addendum-r1 correctsnumsubtotal.
SeparateNEW8finite21marks ACTUALLYinstalled at
A/data/current25-new8-prospective-d1-marks-preparation-20261019-v1/
parent-install-1/installed.json SHA035861cf. Currentcontract0bb10838/family5391e029/
SOURCE36e52109/16groups, parenthash-onlycontroller952770c9/3groups, oneRegister
disabled/oneEnable/0invoke/allothers unchanged. Neverrerunparentinstaller.
Datafirst08:00KSTOct20capturesUSOct19, lastNov17capturesUSNov16; notNov17USexit.
Old20feeds unchanged. OfflineconsumerA/research/current25-new8-future-measurement-
reader-20261019-v1/ABI.md; actual6publicationPASS,21missingdays=>24riskyUNKNOWN/
3analyticcashKNOWN, notaccountprofit. Parentexplicitpacket/dayrefs, no latestscan.
TimesFM2.5 ACTUAL oneCPUbatch/oneRootforward/8x21point/0fits-GPU-retries;
current25-new8-foundation-future-benchmark-20261019-v1/cpu-forecast-r1/
actual-map-index-r1/HANDOFF-ACTUAL.json, sealbfe2316a. FinalwriteOct18
17:22:20.564931UTC; Parent independentpublication-r2 verifiescounts/source/
all8scores+weights. Forecast never repeat; future21outcomes UNKNOWN.
Temporal-expert-composition-development-20261019-v1 CLOSED at nativeproof,
57SYNforwards21updates/0marketfits/0economics. SYN-TAIL-DISPOSITION.json:
originalSYN10 not qualified by changedSYN5, TCN2/2failed/PATCHlinkedonly.
Do not run old launch/caller/recovery. Separate Infra calibration
current25-temporal-native-calibration-20261019-v1 COMPLETE PASSoriginalcriteria/
3epoch/fullstate,50forwards16updates/80.281owned480/678.654elapsed900atcleanup,
lease released. Independent110pinsACTUAL-READBACK2d0552ab, no oldCqualification.
New marketSOURCE current25-temporal-experts-calibrated-development-20261019-v1
2fits/7200each/16000active28800end fromSOURCE17:42:22UTC. Parent exactcheck
READY26869e99/source27workersd2f6783f/GO dispatched; actualTCNmarketstart1
Oct18 18:02:37UTC/GPUallocation18:02:39/free22070MiB. Firstepochunobserved
at18:03:56, PATCH serial next. Do not run a second caller or reclaim its lease.
Ledger243closed plusoneactiveattempt, not completed-model/profitability proof.
Native-throughput SYN PASS/oneallocationreleased/4exactfullstate restores:
A/infra/gru-native-throughput-preparation-20261018-v1/native-probe-1/HANDOFF.json.
Synthetictimings/memory only, not market-speed/alpha/trajectory parity.
Before numericaldispatch exact input/split/scaler/commondate/contract binding,
real native solver/optimizer/checkpoint SYN, exclusive lease/headroom. No dummy
GPUuse/oldfitrestart or metadata-only zero-array-read blanket.

Actual DataAction repair Oct18 15:29UTC:
A/infra/data-dispatch-spacing-runtime-freeze-20261018-v1/
parent-rth-retarget-1/retargeted.json SHAafc4717a;
parent-d1-retarget-1/retargeted.json SHA04ea3e46.
BothEnabledReady,firstOct20 06:50/07:30KST unchanged. OnlyAction paths changed;
SDK53bb68ee/READY9743b9c4/90payloadfiles12allowedchanges, originalfae79e85D1
contract/custody/cache/token gates/21triggers remain. BEFORE XML and known-ours
rollback saved BEFOREDisable; otherdefinitions exact eachtransaction. No task
invocation/newTask/schedule/globalpacing claim. Never rerun adoption/transaction.
Exact rollback proposal/restoration-disabled instructions:
A/infra/data-dispatch-spacing-runtime-freeze-20261018-v1/PARENT-RECIPE.md.
Nightly image30433095 independently NOT_AFFECTED, not retargeted.

Trusted GPU research image:
sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039,
PyTorch2.7.0+cu128/Python3.12. Existing safeNPZ/COMMITTED/safetensors only.
Actual source/kernel/runtime variants and limitations remain explicit.
Marketbytes M;features/checkpoints/generatedresearch A;Docker /app/model_artifacts.
Keep D:15percentfree/warnprojected20percent. Credentials via scopedPaperloader
only; credential-free tools use uv --no-env-file/.env.example, no implicitdotenv.

## Verification

CURRENT full authority:
A/verification/deployed-data-pacing-recovery-20261018-v1/authority.json.
1360files/digestf81653d809b0bbb175479cf4e136a09dd88b37c71ac0085e62860718f9e74389.
132focused/322changed-pathserial,clean8 full18314PASS22skip/18336collected/helper0
in386.86s;
Ruff/default/research/accounting sample-envCompose PASS.
This supersedes old verification summaries, not deployed historical images.
AGENTS/DECISIONS control hashes also must match for reuse. Docs/external-only
work revalidates exact source/control digests and fresh external focused/native
checks; repeatedrepo tests cannot validate external code.

Trackedcode/control/materialExecutionrecovery needs changed-pathserial+fresh
fullhelper, no failed/partial/unclean authority reuse:
```powershell
uv run --no-env-file --extra dev pytest -q <changed-test-paths> --maxfail=1 --durations=15
& C:/Users/Public/Documents/thericher-v2/scripts/run_parallel_tests.ps1 -Workers 8 -RequireCleanTempRoot -PytestArgs @('--maxfail=1','--durations=15','--junitxml=D:/thericher-v2/model-artifacts/verification/<fresh-owned-run>/pytest.xml')
uv run --no-env-file --extra dev ruff check .
docker compose --env-file C:/Users/Public/Documents/thericher-v2/.env.example config --quiet
docker compose --env-file C:/Users/Public/Documents/thericher-v2/.env.example --profile research config --quiet
docker compose --env-file C:/Users/Public/Documents/thericher-v2/.env.example -f C:/Users/Public/Documents/thericher-v2/docker-compose.yml -f C:/Users/Public/Documents/thericher-v2/docker-compose.accounting.yml config --quiet
```
Helper Globalmutex/lease/process/exactworker-count/skip/nonreparse childcleanup
remain. Synthetic Scheduler tests mock ALL entrypoints with autoloadNone.
Testscratch short freshchecked C:NVMe, not a reused auto-deleting pytestpath.
Detailed frozenhistoricalcommands/results remain Git1ce5f45/immutable roots;
do not treat them as current execution instructions. Recovery: resume/restart/
reconcile/complete/unrecoverable/operator by actual ownership/evidence, not age.
