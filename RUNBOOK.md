# Runbook

## Current Owned Runtime (2026-10-15 KST)

Workdir C:/Users/Public/Documents/thericher-v2.
A=D:/thericher-v2/model-artifacts; M=D:/market_data.
ONE company objective: current-nas-owned-model-paper-cycle-v1.
AGENTS.md owns authority/risk; HANDOFF.md owns current evidence.
KIS Paper work is delegated. Never read/route KIS_LIVE_*.

### Existing nightly,23:50 KST

Task: thericher-kis-paper-daily-spy-session.
Ready/enabled, next Oct15 14:50 UTC. Exact XML/argv/identity/bank unchanged.
Image sha256:3ccb2250abcc7b11c6ab5f7f048a38b145962755935bace495efc0ac985f3ce7.
Frozen driver/472-public-file repository and image470-file map isolate it
from mutable development SRC. No secrets were copied into the snapshot.
A/execution/current-paper-frozen-deployment-20261015-v1/after.json

Quiet Action remains Pythonw -B; every child uses CREATE_NO_WINDOW.
A/execution/current-paper-shared-loop-20261014-v1/quiet_dispatch.py
Driver e5867a8a/quiet6d51b09d; original TaskXML f35811a0 unchanged.
freeze.ps1 already consumed. Do not edit frozen source/driver or rerun creators.
Rollback before-quiet_dispatch.py is retained in the frozen-deployment root.

### New model,22:40 KST

Task: thericher-kis-paper-current-nas-model-20261015.
Ready/enabled, first Oct15 13:40 UTC. Installation is NOT submit/fill/closure.
Image sha256:ce219a8dd26c056563df916f184d17ae5942c55fcd57f502175c4c6fc90c160f.
A/execution/current-nas-owned-model-paper-deployment-20261015-v1/installed.json
A/execution/current-nas-owned-model-paper-deployment-20261015-v1/deployment.json
Full source/installed14-trigger/unchanged-nightly native readback:
A/execution/current-nas-owned-model-paper-deployment-20261015-v1/after-installation.json

Host c6e4c034/worker9e1c0473, exact474-file manifest130d1c33,
launcher4892baa8/configa13fa7d9. Fixed targets/input/policy source bound.
Same native private/runtime/emergency volumes and original shared tenth;
no new bank or foreign inventory adoption.

Finite trigger dates: Oct15/16/19/20/21/22/23 UTC.
Each date13:40..14:36 and15:05..19:41 UTC, four-minute interval.
Existing nightly gap plus active-owner/due admission;8-minute OS limit,
one280-second native visit,1auth/1combined-submit/1cancel/128calls maximum.
No nested retry scheduler. Interactive user must remain logged in; computer/
Docker must be available. A missed trigger is not a completed opportunity.
Read-only powercfg check Oct15: current high-performance AC/DC automatic sleep
and hibernation delays are zero (disabled). No power settings were changed.
This does not prevent a manual shutdown/logoff or Windows Update restart.

New entry uses ONLY the fixed Oct15 session. Later visits recover retained
identities without reselection/expiry renewal. Earliest owned exit Oct21 regular
OPEN, then later owned exit/recovery. Research target fifth-session CLOSE is
not an execution-parity claim. Keep original request timestamps/TTL/unknowns.

Pure target/score creators and schedule.py --install have ALREADY run.
Do not rerun them or manually invoke the Task/host to inspect results.
Inert source imports/tests are distinct from --execute runtime effects.

### Other preserved owners

Accounting83 r6: thericher-kis-paper-five-387ee5f6c7c6-accounting,
next Oct15 20:25 UTC /Oct16 05:25 KST. Runtime remains unknown.
A/execution/future-accounting-data-source-firstcause-r6-20261015-v1/parent-installation/after.json

Goal83 exit Oct17 04:50/recovery05:00 KST. Goal97 entry Oct19 22:30/recovery22:40,
exit Oct24 04:50/recovery05:00 KST. Original113 archive/image/basis/claims
retained. Do not replay oldindex2 or equate cohort no_owned_intent with globalflat.
Old113/current3ccb/newce219 generic multi-stock reader compatibility passed,
NOT the whole old overlay or live broker runtime.
G10721:50 UTC and NAS-forward21:40 UTC retain their Data-owned schedules.

## Inspect Without Side Effects

Source-safe Task facts only; never output Action argv containing secret values,
raw broker bodies, account/order identifiers, private prices or amounts.
The known Action paths/configs here contain only public source identities.

```powershell
Set-Location C:/Users/Public/Documents/thericher-v2
$PSModuleAutoLoadingPreference = 'None'
Import-Module ScheduledTasks
Import-Module Microsoft.PowerShell.Utility
foreach ($name in @('thericher-kis-paper-daily-spy-session','thericher-kis-paper-current-nas-model-20261015')) {
    $task = Get-ScheduledTask -TaskName $name
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

New model launch pointer:
A/execution/current-nas-owned-model-paper-deployment-20261015-v1/launch/current.json.
Bind pointer hash -> immutable launch -> exact runtime receipt hash/source/image/
clock -> strict native cycle/intent/fill/book. No latest-file scans/task-exit
fill inference. Active owner remains exclusive; missing outcome is unknown.
Native offline private readers use network-none, exact pinned image/source and
read-only private mounts. Never execute observe(), a strategy worker, collector
or broker method merely to read evidence.

The old nightly reboot-recovery/read_owned_dispatch.py has STALE driver/image/
time constants. Do not alter its historical source or use it as current proof;
use the current r2 reader below, bound to drivere586/image3ccb and modelce219.
Historical pure read_private_cycle.py covers the daily cycle, NOT the new model
pointer. Model attribution uses read_native_model.py, not recovery-capable code.

Current reader readiness/source pins/actual safe preflight:
A/execution/current-nas-owned-model-paper-readback-20261015-v1/r2/ready-parent.json
73focused/Ruff/noP1P2; native tenBUY/tenSELL/restart/unknown/missing-state and
false-flat/journal-only cases tested. Default inert. Absent model pointer or
pre-reservation-only journal yields countsnull/unknown, never inferred zero.
Actual current RO preflight:6owners16intents/modelnotrecorded/privatebytesstable;
remaining original cap positive_below_desired, not fresh broker buying power.
No forced liquidation or added capital. Native models may be reduced/rejected.

After the respective natural opportunity (future bounds are deliberately invalid
before their time), use the source-pinned public receipt reader:
```powershell
uv run --no-env-file --extra dev python -B D:/thericher-v2/model-artifacts/execution/current-nas-owned-model-paper-readback-20261015-v1/r2/read_owned_dispatch.py --read --profile model --not-before '2026-10-15T13:40:00+00:00'
uv run --no-env-file --extra dev python -B D:/thericher-v2/model-artifacts/execution/current-nas-owned-model-paper-readback-20261015-v1/r2/read_owned_dispatch.py --read --profile nightly --not-before '2026-10-15T14:50:00+00:00'
```

Before a native private read confirm named execution owners are quiescent, then
check reader SHA f7990232992f17409d3626ecc83b43db4025ffa1c38be89a30ea1a679aa24039.
Use ONLY an offline reader, never the deployed strategy worker. Example after
source/owner checks, with a unique owned container name/label for typed cleanup:
```powershell
$readerId = [Guid]::NewGuid().ToString('N')
docker run --rm --name "thericher-offline-model-$readerId" --label "thericher.offline.native-read=$readerId" --network none --read-only --log-driver none --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 1 --env OPENBLAS_NUM_THREADS=1 --mount 'type=volume,source=thericher-v2-paper-canary-private-acct-20261007-v1,target=/app/private,readonly,volume-nocopy' --mount 'type=bind,source=D:/thericher-v2/model-artifacts/execution/current-nas-owned-model-paper-readback-20261015-v1/r2,target=/reader,readonly' sha256:ce219a8dd26c056563df916f184d17ae5942c55fcd57f502175c4c6fc90c160f python -B /reader/read_native_model.py --read
```

The canonical private VOLUME mounts at /app/private, NOT /app/private/canary;
the latter hid the nested book in Parent's first two harmless RO probes. Keep
their unknown results, never recreate an apparently missing book. The original
dispatch reader's nightly audit missed its exact public quiet file; r2 permits
only that pinned file and still rejects sibling reads. No schedule/risk change.
Native counts are cumulative exact retained model-cycle links, not per-trigger
deltas or fresh broker inventory. Read receipt binding separately; hash/time/
input-policy linkage does not prove a particular OS trigger caused each fill.

Scheduler Operational logging disabled. Exact marker/time/hash chain under an
assumed-honest host is NOT cryptographic OS-scheduler-origin proof. Fees/settled
cash/net PnL remain not_observed unless exact independent evidence proves them.

One Codex app heartbeat named 오늘 모의투자 실행 결과 확인, id automation,
runs once Oct16 00:05 KST after both owned opportunities. No recurring report,
task replay, substitute order or follow-up chain. It inspects exact evidence,
not raw private output, and notifies only on material result/failure/operator
decision. It does not replace the Windows workers or prove they ran.

## Verification

Fresh exact source authority:
A/verification/current-nas-owned-cycle-20261015-v1/authority.json
925 changed-path serial pass; fresh clean8 full16,488pass/22skip/351.816sec,
16,510collected/helperexit0; source1,342/digest4a1e461984894e82caa21601bcb0673dfab7cd85bb5924a8dd916bd24c71bc46.
Ruff/default/research/accounting sample-env Compose passed.
External deployment12SYN/native COM14triggers/actual installation readback passed.
Claude categorical supported-with-limits is advisory, not runtime proof.

Credential-free commands from the absolute workdir:
```powershell
uv run --no-env-file --extra dev pytest -q <changed-test-paths> --maxfail=1 --durations=15
& C:/Users/Public/Documents/thericher-v2/scripts/run_parallel_tests.ps1 -Workers 8 -RequireCleanTempRoot -PytestArgs @('--maxfail=1','--durations=15','--junitxml=D:/thericher-v2/model-artifacts/verification/<fresh-owned-run>/pytest.xml')
uv run --no-env-file --extra dev ruff check .
docker compose --env-file C:/Users/Public/Documents/thericher-v2/.env.example config --quiet
docker compose --env-file C:/Users/Public/Documents/thericher-v2/.env.example --profile research config --quiet
docker compose --env-file C:/Users/Public/Documents/thericher-v2/.env.example -f C:/Users/Public/Documents/thericher-v2/docker-compose.yml -f C:/Users/Public/Documents/thericher-v2/docker-compose.accounting.yml config --quiet
```

Changed-path serial scratch: a freshly checked nonexistent SHORT non-reparse
C:/ts/<unique> child. Existing long-path QQQ persistence failures were retained,
not hidden by relaxed tests. Never reuse a pytest --basetemp that auto-deletes
unknown contents. Full helper's Global mutex/leases/checked C:/trpy cleanup
remain unchanged; no failed/partial authority reuse or cleanup-denial bypass.
MD/external-only work can reuse authority ONLY if tracked production/test/script/
dependency/config digest is exact. External code needs its own native checks.

## Research / Recovery Knowledge

Creators/fits/readers with exclusive outputs are frozen after use. Inspect exact
saved receipts, not a second invocation. Data raw under M; models/checkpoints/
research artifacts under A; Docker /app/model_artifacts. Keep D:15 percent free.
No implicit .env load in research/verification.

Latest independent results:
A/research/native-recurrent-attention-relative-ranking-development-20261015-v1/independent-parent.json
A/research/daily5-absolute-utility-linked-math-recovery-20261015-v1/linked-parent.json

Absolute-utility originalcreator failed,3CPUfits retained; linked math-only
publication27newcells45controls,0refits,95.1834active/1,645.4028end within180/1,800.
Only derived mean-log scalar tolerance1e-14; exact othermetrics/NAV/exposure and
economic criterion unchanged. No qualified alpha/untouched replication/Paper
adoption. Old ABI/publication failures and clocks stay immutable.
GPU/CUDA is usable, no permission/runtime hold; no active training allocation.

Token mixed-OS flock/byte locks alone did not coordinate. Current token writers
need atomic directory exclusion plus same-OS legacy locks; no age-based reclaim
or timestamp reset. Existing historical writers are not universally upgraded.
Scoped snapshot60-second issuance floor does not change Data's frozen300 guard.

Last actual marks: realizedgross positive, unrealized/totalmarkedgross negative;
no net-profit claim. Old task definitions/rollback and all private custody stay.
Korean-first private Docker monitor remains deferred; reference127.0.0.1:8787
was not freshly checked. No public service/tunnel or new paid dependency.

History: git show 3dbca52:RUNBOOK.md. Historical commands are retrieval only,
never a reason to replay a creator or consumed scheduled opportunity.
