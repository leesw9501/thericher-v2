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

If a page is repeatedly structurally invalid, diagnose only safe structure
(counts, field names, validation class, and session metadata), preserve the
failure evidence, and stop that target when the source-quality limit is clear.
Do not brute-force the same page or silently accept its remaining rows. This is
data correctness, not an approval condition for other KIS Paper or research
work.

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
uv run python scripts\backfill_kis_paper_private_intraday.py --execute --mode head --pages-per-target 2
docker compose --profile kis-paper-intraday-head run --rm --no-deps kis-paper-intraday-head
```

Head snapshots live below the sibling `intraday-head` cache root and never
advance the historical backfill cursor. The local
`thericher-kis-paper-intraday-head` automation runs Tuesday through Saturday at
02:35 KST, which maps to the same US weekday mid-session. It is a bounded
data-only invocation: it does not imply a complete session merely because it
ran, and it has no account, order, or live route.

For an offline KIS-cache replay after a complete session has been retained:

```powershell
uv run python scripts\run_kis_paper_intraday_local_paper_baseline.py --session-date 2026-07-21 --symbol QQQ
```

The command makes no network or credential access. It writes only a sanitized
local-paper summary under the external model-artifact root.

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

## KIS Virtual-Paper Canary

The quote-derived execution-learning command is a virtual-paper US buy-limit
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
a safe no-submit result. It accepts only a KIS-success quote and rechecks both
that time window and the limit validity immediately before submit. The helper
does not yet claim a full holiday or early-close calendar. The local
`thericher-kis-paper-quote-session`
automation invokes this command once per weekday at KST 23:35. Re-running an
existing run ID reconciles its persisted intent before any replacement submit.
Its cancel-after-submit choice is durable, matching accepted open orders resume
cancellation after a restart, and sibling run IDs are serialized at the private
state root. A non-success submit response or completion evidence after a cancel
is `outcome_unknown`, not a clean result or retry cue. Do not pass secrets or
account values on the command line.

The canary may be invoked by a scoped recurring Paper schedule during eligible
sessions. There is no one-shot or per-goal execution quota: a distinct new
intent can proceed after the scheduler's technical session, pacing, concurrency,
and durable-state checks. An ambiguous intent remains unrepeated until its own
reconciliation, but never blocks a later distinct Paper intent or another lane.

The first token attempt on 2026-07-21 returned `auth_rejected` before a
submission. The latest read-only bridge attempt reached the account boundary
and returned `balance_rejected`; no order was sent. Both are integration facts,
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
