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

Market data stays private, local, and unserved. Stop only the affected cache if
applicable source terms prohibit retention or if disk policy would be crossed.
Warn before projected free space falls below 20%; do not begin new large work
that would cross the 15% floor.

## KIS Daily Backfill

The active raw daily cache is at:

```text
D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json
```

Run a bounded worker chunk whenever the authoritative index says it is due:

```powershell
uv run python scripts\backfill_kis_paper_private_daily.py --execute
```

The worker reattests committed snapshots, recovers a matching orphan before a
new network call, obtains one paper token, requests up to two daily pages,
writes a raw snapshot plus manifest to `D:`, then atomically advances one
cursor. Read the index's shared retry time after a token event; that pacing is
observed source behavior, not an approval or quality gate. Do not run two
workers concurrently against the same index.

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

`data.kis_paper_intraday` is the offline consumer: it verifies every index,
manifest, and raw hash; maps KIS Korea timestamp fields to UTC; and delegates
5m, 10m, 1h, and 3h aggregation to an explicit `SessionWindow`. The first
observed pages include extended-session data, so do not treat the cache as a
regular-session strategy dataset until Data records that source semantics.

### Prospective Head Collection

Use the separate head cache when the goal is fresh in-session observations
rather than historical cursor continuation:

```powershell
uv run python scripts\backfill_kis_paper_private_intraday.py --execute --mode head --pages-per-target 4
docker compose --profile kis-paper-intraday-head run --rm --no-deps kis-paper-intraday-head
```

Head snapshots live below the sibling `intraday-head` cache root and never
advance the historical backfill cursor. The Windows Scheduled Task
`thericher-kis-paper-intraday-head` runs Tuesday through Saturday at 06:20
KST, after the corresponding US regular-session close in both US daylight and
standard time. It requests four pages per target: the summer envelope is 80
post-close minutes plus 390 regular-session minutes, so four 120-row pages
provide the minimum 480-minute coverage with a small margin. This remains a
bounded data-only invocation (at most eight minute-page calls): it does not
imply a complete session merely because it ran, and it has no account, order,
or live route. The next metadata-only inspection must still find one exact
390-minute regular session before Research may consume it.

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

`raw_market_data_retained: false` is never a control condition for the console,
a later collection, a KIS Paper call, an order, or a schedule. It records only
the absence of bytes for its own historical result.

When a due session ends before a canary intent exists, such as a directional
buy pause or quote failure, it refreshes the sanitized canary runtime to
`unavailable` with no account, order, quote, or broker-body data. The detailed
safe reason remains in the external session evidence; the console never keeps a
stale prior canary result as if it were current.

The installed Windows Paper schedules invoke their named Docker profile with
`--build`, so a due session uses the current committed image rather than a stale
service image. This is runtime reproducibility, not a new scheduling or Paper
approval condition.

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

Run a CPU baseline before an eligible GPU campaign. GPU work needs a frozen
dataset and falsifiable hypothesis; do not launch models solely to keep the GPU
busy. One GPU job runs at a time while other lanes continue.

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

## Verification

Run at every bounded goal boundary:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```
