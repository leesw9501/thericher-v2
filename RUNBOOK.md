# Runbook

## Modes

- `off`: no broker work; data/research and local simulation are available.
- `local_simulation`: broker-free replay; fills remain `source: local_paper`.
- `kis_paper`: KIS virtual account and virtual orders. This is standing
  authorized for the private project.
- `kis_live`: real-money behavior. It is unavailable: do not read
  `KIS_LIVE_*` or construct a live route.

Existing KIS clients must pin the virtual-paper host. A caller selecting a live
mode must fail before paper credentials are used.

## Long Codex Task

```powershell
.\scripts\start_next_codex_task.ps1
```

Read the files it prints and then execute the single current objective in
`NEXT_CODEX_GOAL.md`. Codex assigns ready Data, Engine Research, Execution,
and temporary Validation work, integrates it, verifies, commits, pushes, and
refreshes the next objective. Do not stop for routine paper-work approval.

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

Install the continuation owner only after a successful bootstrap:

```powershell
.\scripts\install_kis_paper_schedules.ps1 `
  -ScheduleName thericher-kis-paper-daily-broad-backfill
```

It triggers Tuesday through Saturday every 30 minutes from 07:15 to 20:45 KST.
`IgnoreNew` retains one active 14-hour/24,000-chunk worker; a later trigger
recovers a failed worker without a duplicate collector. The Windows task limit
is 870 minutes so Docker startup and final receipt writing fit outside the
worker's 840-minute bound. Do not hand-edit its index or launch a second worker
against the same cache. Inspect only source-safe aggregate receipts/index facts
before relying on its coverage.

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

After a `complete` postrun, an explicit offline chronology observation may
record only the frozen candidate's aggregate per-target bar-count and calendar-
span buckets:

```powershell
uv run --offline python scripts\observe_kis_paper_daily_broad_panel_chronology.py `
  --postrun-receipt D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-panel-postrun-v1\<receipt>.json `
  --baseline-manifest D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1\panel=2c3b9ddddc7160620210\manifest.json `
  --candidate-manifest D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1\<candidate>\manifest.json
```

It reattests the existing complete postrun and panel manifests, then writes one
external aggregate-only observation. It never emits a global common-history
threshold or a `feasible`/research-eligibility verdict: current-listing and
source-limited targets make such a boolean misleading. The observation is
perishable by candidate generation and is not a split, target, model, GPU,
ranking, Paper, or live input.

## KIS NAS D1 Forward Cache

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
`thericher-kis-paper-intraday-head` runs Tuesday through Saturday at 00:31,
02:31, 04:31, and 06:20 KST. The first three starts align one minute after a
10-minute US bar boundary; the final start remains a coverage collection after
the regular session. Each data collector invocation keeps the four-page-per-
target maximum. The capture coverage selector, not the schedule, still requires
an exact 390-minute declared QQQ session before it can call a whole-session
observation complete. That rule does not apply to the bounded runtime selector:
it accepts one verified, same-session, contiguous 90 completed-minute QQQ/NAS
window ending on a 10-minute boundary and emits a precise stale/missing/gapped
fact otherwise. Historical Research uses separately qualified inputs and does
not wait for this task.

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
immutable `runtime-freshness-v2` validation namespace, so it can reattach an
older receipt without overwriting it; legacy receipts without these new fields
remain replayable under their original scope.

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

The one existing `thericher-kis-paper-intraday-head` task invokes this same
capture mode before its bounded local and QQQ Paper consumers. It adds no new
Windows task, and its page cap, concurrency, and collector exit authority stay
unchanged. An eligible 90-minute runtime window may now produce a provisional
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

It writes a sanitized local runtime snapshot. Do not pass `.env` values on a
command line or emit credentials, account numbers, raw response bodies, or
tokens in logs/artifacts.

The bridge reports its fixed `read_only` scope and whether the account snapshot
is complete. It is not a `safe_to_submit` approval proxy: a later paper executor
uses a fresh account view together with its own virtual-route, intent, and
unknown-outcome checks. An unavailable bridge artifact may retain only its
allowlisted endpoint, transaction ID, HTTP status, and a narrow KIS `msg_cd`
code; never a broker message body, `msg1`, account identifier, or free-form
response text.

The current-image bridge reached `balance` (`VTTS3012R`) and received HTTP 500
with `EGW00201` on 2026-07-21 UTC after a successful image rebuild. It sent no
order. KIS's official sample repository identifies that code as exceeding the
per-second request limit. The real read-only transport now spaces valid external
requests by at least one second using an injectable monotonic policy. A rebuilt
bridge then completed at `20260721T223701135634Z-complete.json` with only
sanitized position/open-order counts and USD currency labels. It made no order.

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
limits. The Paper quote and daily-session tasks retain `IgnoreNew` and a
90-minute limit but deliberately omit `StartWhenAvailable`: a late wake or
login must not create an off-cadence Paper session. The daily-backfill task is
data-only and has a 390-minute task limit around its declared six-hour inner
budget.

The Codex app daily operating review runs at 08:10 KST. It is the concise
operator-summary and integration pass for the prior daily-SPY head/session,
quote-session, and intraday-head sanitized outcomes. It performs no KIS call
itself; the named Windows tasks remain the only recurring KIS-facing
execution/data jobs.

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

The installed Windows tasks run the head at 22:15 KST and the receipt session
at 23:50 KST, Tuesday through Saturday. The session may honestly record a
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
reconciliation, but never blocks a later distinct Paper intent or another lane.

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
collection, or research. A legacy state without that durable submission time
returns `submission_time_missing` without reading credentials or calling KIS.
Before any history request, the probe requires the persisted run, client-order,
and decision identifiers to agree with the requested receipt identity. A
missing state or identity mismatch is categorical unavailable evidence, never
proof that an order was not submitted.

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
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

### Faster Local Test Feedback

For repeatable Windows feedback between goal boundaries, use:

```powershell
.\scripts\run_parallel_tests.ps1
```

It runs the same suite with up to eight `pytest-xdist` workers (bounded by the
host CPU count) and file-level distribution. The helper gives each run a short,
unique base temp path beneath `C:\trpy`; this avoids Windows worker-path length
failures, cleans a successful run's private temp path, and leaves a failed run
available for diagnosis. Override the worker count when needed:

```powershell
.\scripts\run_parallel_tests.ps1 -Workers 4
```

It has no KIS, credential, Docker, market-data, or artifact access. The command
above is a faster feedback path, not a replacement for the authoritative serial
verification at a bounded-goal boundary. On 2026-07-27, the same full suite
completed with `1365 passed, 13 skipped` in 102.86 seconds using eight workers
and in 510.80 seconds serially. Use the parallel helper during implementation;
retain the serial run only for the final goal-boundary proof.
