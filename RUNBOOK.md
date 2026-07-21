# Runbook

## Modes

Policy distinguishes four execution concepts:

- `off`: data and research only; no fills or broker calls.
- `local_simulation`: broker-free simulation; existing fill source is
  `local_paper`.
- `kis_paper`: KIS virtual account after explicit authority and capital
  approval.
- `kis_live`: KIS real account after separate explicit authority.

Current code may expose a smaller mode enum until the execution contract goal
implements this separation. Default behavior remains off and broker-disabled.

## Long Codex Task

Start with:

```powershell
.\scripts\start_next_codex_task.ps1
```

Read the files printed by the script, then use `GOAL_SCRIPT.md` as the short
operator launcher and `NEXT_CODEX_GOAL.md` as the only authoritative objective.

Codex should:

1. Check recovery state and uncommitted work.
2. Decompose the company outcome into disjoint Data, Research, and Execution
   work packages.
3. Run ready packages in parallel through role agents or existing workers.
4. Integrate shared contracts and independent Validation evidence.
5. Run verification, commit, push, and refresh the next goal.
6. Continue with the refreshed goal while no real approval or external blocker
   requires the operator.

Do not stop merely to ask which required lane should work next. Do not use
fixed lane percentages or forced rotation.

## Existing Workers

Engine Research claims one queued Docker research job and exits:

```powershell
uv run --extra dev thericher-v2-engine-research-agent run-once
```

Data claims one queued non-GPU data job and exits:

```powershell
uv run --extra dev thericher-v2-data-agent --artifact-root D:\thericher-v2\model-artifacts run-once
```

Queue and run state stay outside Git under the role's external artifact root.
Goal-owned schedules are allowed when their owner, input/output bound, evidence
path, recovery behavior, and resource limit are explicit. These workers are not
unbounded daemons or autonomous cross-lane coordinators. Verify a stale lock
against the real process/container before changing it.

Execution has no executable worker yet. Use temporary role workers and fake
transports until a recurring KIS paper objective justifies one bounded
single-shot worker.

## Docker Local Runtime

The Compose `engine` and `web` services share a Docker-local named runtime
volume. The current default `engine` command only prints a daily report; it
does not produce local-paper events, so a freshly started console correctly
shows no local activity. A later explicitly invoked Docker-local simulation may
write that runtime. The web monitor mounts runtime read-only and has a separate
writable emergency-state volume. A Windows-host runtime is deliberately
separate from this volume. Do not run a host-side simulator against the
Docker-local console runtime, and do not run competing Docker event-log writers
at the same time.

The `kis-readonly` Compose profile is a deliberately invoked one-shot reader,
not a service or retry loop. It receives only the four interpolated
`KIS_PAPER_*` values; it neither mounts `.env` nor receives live values. It
atomically replaces the generic console snapshot only after a complete typed
read; the web accepts it only while `now < expires_at` and otherwise renders
`unknown` or `unavailable`. The schema labels the exact
`ord_psbl_frcr_amt` source value as orderable foreign funds, not settled cash,
account equity, margin capacity, or general buying power. A normal approved
invocation is:

```powershell
docker compose --profile kis-readonly run --rm --no-deps kis-readonly
```

If a fresh complete sanitized runtime snapshot exists but its minimal external
evidence failed to write, use this recovery command before the five-minute
expiry. It reads no credential or KIS endpoint:

```powershell
docker compose --profile kis-readonly run --rm --no-deps kis-readonly `
  python -m thericher_v2.execution.kis_paper_console_bridge `
  --recover-evidence --repository-root /app `
  --runtime-snapshot /app/runtime/state/paper_account_snapshot.json
```

Do not use recovery to refresh stale state or to create a retry loop. A new
read must belong to a new bounded objective.

The separate `paper-capital-proposal` profile has no network, KIS/Tiingo
environment, public port, writable runtime, or approval persistence. It reads
only the generic snapshot and prints `abstain` or an operator-review candidate.
Run it only after the operator supplies a cap in the snapshot's native currency:

```powershell
docker compose --profile paper-capital-proposal run --rm --no-deps `
  paper-capital-proposal python -m thericher_v2.execution.paper_capital_proposal `
  --runtime-snapshot /app/runtime/state/paper_account_snapshot.json `
  --currency USD --operator-ceiling 500
```

The command uses `min(source-labelled orderable foreign funds, operator
ceiling)` only when the snapshot is complete, unexpired, same-currency, and has
no positions or open orders. It does not use the separate reference-orderability
amount to size, convert FX, approve capital, or submit an order.

## Data Acquisition

Use `D:\market_data`. Never download market data into the repository.

Data may be acquired automatically when it is useful, no-cost, no-auth,
license-compatible for private use, bounded, and deduplicated. Paid, logged-in,
manual-agreement, private-API, or unclear-rights sources require operator
approval.

The operator has separately authorized a bounded local KIS Paper market-data
cache for this private, noncommercial, nonpublic project. Keep it under
`D:\market_data`, attach a provenance manifest and request budget, and never
serve, publish, or redistribute it. Stop that source immediately if an
applicable KIS or exchange term is found to prohibit retention.

Warn at a projected 20 percent D-drive free-space level. Stop new large data or
training work before crossing 15 percent. If operator action is needed, report:

- source and current URL,
- symbols, dates, timeframe, and format,
- expected size and current price,
- exact acquisition steps,
- engine-loop value and free alternatives,
- blocker and decision requested.

Stop pursuing a source after two bounded automated failures, when rights are
unclear, or when marginal coverage no longer improves a named engine loop.

## Research Campaigns

Do not add another artifact-specific job kind when a campaign parameter or
generic primitive can express the question.

A campaign freezes:

- dataset and snapshot IDs,
- realizable target and feature timing,
- chronological train/calibration/validation splits,
- purge/embargo and sealed holdout policy,
- fees, spread, slippage, FX, and sizing assumptions,
- naive and CPU baselines,
- primary after-cost metric and falsification checks,
- breadth/depth/ensemble/replication budget and stop rules.

Existing short 1m evidence is pipeline/development context until Data records
enough independent chronological coverage. CPU preparation may continue while
GPU work is held. Once eligible work exists, run one GPU job at a time through
Docker `research`, using BF16/mixed precision, cached materialized inputs, and
recoverable checkpoints where appropriate.

Free public assets stay in research. Record source, version, hash, and license;
prefer safe serialization; isolate unavoidable untrusted formats. Never pass
model code or checkpoint loading into Execution.

## Claude Challenger

Ask Claude once at a bias-prone decision boundary defined in `AGENTS.md`.
Containment and emergency stops never wait for review; Claude challenges the
subsequent recovery or resume decision.

The prompt should include only redacted evidence identifiers and ask for:

1. the claim,
2. the strongest kill test,
3. leakage, survivorship, and selection-bias risks,
4. the naive baseline and blast radius,
5. what would reverse the conclusion,
6. a verdict of `unsupported`, `uncertain`, or `supported-with-limits`, plus the
   smallest decisive next action.

Do not send credentials, account identifiers, raw sealed-holdout labels, or
unnecessary row-level data. Do not create a Claude report family. Record a
review only when it changes a durable decision or a named promotion/recovery
boundary.

## Bounded KIS Historical Capability Probe

This one-time procedure improves the data-collection loop by checking the
smallest KIS historical response shapes that could later inform a
KIS-compatible input contract. It is not an archive, a retention test, a
dataset acquisition, a model input, or a broker-account check.

The operator-approved scope is fixed: one `KIS_PAPER_*` token; only `QQQ` and
`SPY` on `NAS`; at most three daily pages and three raw-`1m` pages in total;
no order, cancel, account, position, buying-power, open-order, or live endpoint.
It retains only sanitized fixed-scope metadata under
`D:\thericher-v2\model-artifacts\data-agent\kis-paper-historical-data-probe`.
Raw values, cursors, response bodies, credentials, and account facts are never
printed or persisted.

Run exactly once after checking the external control reservation:

```powershell
uv run python scripts\probe_kis_paper_historical_data.py --execute
```

The reader stops after the two paper app values and never reads account/live
values. Its approved `.env` prefix is `THERICHER_MODE=off`, optional
`THERICHER_HOST_MODEL_ARTIFACT_ROOT` / `THERICHER_MODEL_ARTIFACT_ROOT`, then
nonempty `KIS_PAPER_APP_KEY` and `KIS_PAPER_APP_SECRET`; put Tiingo, account,
and live keys after that prefix. Do not paste values into commands, logs, or
task messages.

The external lifecycle is `reserved -> network_started -> summary_written`.
Any lifecycle record blocks a retry. A successful sample can establish only
dated endpoint/paging/field-presence facts. It cannot establish long retention,
rate limits, adjustment/corporate-action semantics, point-in-time coverage,
storage rights, or model fitness.

## Bounded KIS Raw-Minute Qualification

This one-shot procedure improves the data-collection and paper-trading loops:
it tests whether a KIS-native completed-bar input can be reconstructed without
turning the broker into a historical-data archive.

This exact v4 procedure was consumed on 2026-07-20 and completed terminally
`rejected` as `minute_response_rejected`; its reservation now blocks every
repeat. The command below is preserved as historical operating context only.
Do not invoke it again or rewrite its sanitized artifact.

Run only during the fixed, preverified **2026-07-20** Nasdaq session window,
13:30 through 15:40 New York time on a ten-minute boundary and seconds 10-45:

```powershell
uv run python scripts\probe_kis_paper_raw_minute.py --execute --confirm-no-exception
```

The date is pinned after checking Nasdaq's official
[2026 trading calendar](https://www.nasdaqtrader.com/Trader.aspx?id=calendar):
July 20 is neither a listed closure nor early close. The script rejects every
other date before configuration, reservation, or network access; it is not a
general exchange-calendar implementation.

Before supplying `--confirm-no-exception`, independently check the official
Nasdaq calendar for a new closure or early-close exception. Outside that window
the command must return before reading `.env` or making a KIS network request.
Inside it, the runner requires that explicit confirmation and first checks the
external one-shot reservation in the shared control root. It then preflights
only the approved paper-app configuration; a malformed layout exits without an
attempt marker or summary. On success it rechecks reservation and a fresh clock
immediately before atomic reservation, checks again immediately before token
issuance, and once more after OAuth immediately before the first raw-page GET.
It issues at most one token request, reads one `QQQ`/`NAS` raw `1m` page and at
most one continuation using the documented `PINC=0` to `PINC=1` / prior-minute
`KEYB` contract. The continuation must have no overlap and begin exactly one
minute before the first page's oldest timestamp. The runner rejects HTTP
redirects, accepts at most 120 rows per page, writes only sanitized metadata
under the pinned `D:\thericher-v2\model-artifacts` root from typed
evidence/failure input, synchronizes its reservation lifecycle before a
possible side effect, and never calls account, order, cancel, or live endpoints
or writes raw rows to `D:\market_data`. A blank dashboard-token placeholder may
precede the paper app keys; a nonempty dashboard value belongs after them and
is never loaded by this narrow reader.

For historical code context, the local builder is now aligned with the current
official raw-minute sample: it emits `custtype=P`, empty first-page `tr_cont`,
and continuation `tr_cont=N`, without `FILL_GUBN`. This local request-shape
alignment cannot diagnose or reopen the consumed v4 rejection and does not
authorize another network observation.

The runner also skips a continuation when the first page's original exchange
timestamps are not strictly descending by one minute. It does not sort or repair
the page before computing `KEYB`; it returns sanitized first-page metadata with
the cursor available but unrequested. This is a local safeguard, not an
observation qualification or a reason to reopen v4.

A one-shot response is always `observed` or `rejected`, never a promotion. Its
external attempt marker records `reserved -> network_started -> summary_written`;
if summary persistence fails, `network_started` remains and blocks retry. A
future, independently scoped Data objective may assess timestamp-label evidence
and ask Claude before any capability update.

## KIS Raw-Minute v1 and Capacity Map

`kis-paper-raw-minute-observation-v1` is terminal. It ran once at
`2026-07-21T13:43:14Z`, made one token and two raw-minute page attempts, and
finished `rejected` / `minute_response_rejected`. Its marker and ledger are
complete, and its one-shot automation is paused. Do not run its command again.

KIS Paper market-data/account/order work and goal-owned schedules are authorized.
The following capacity-map commands are historical context only; both objective
IDs have reached terminal `rejected` markers and must not be rerun:

```powershell
uv run python scripts\map_kis_paper_historical_capacity.py --track daily --execute
uv run python scripts\map_kis_paper_historical_capacity.py --track minute --execute
```

The daily track accepted two 100-row pages before its third request rejected,
so the planned second anchor was not reached. The raw-minute track accepted one
120-row internally contiguous page before its second request rejected. Neither
needs a regular-session calendar guard because neither is a trading action.
Each has a separate objective ID and summary hash; a later attempt must use a
new objective ID rather than replaying a terminal one.

External summaries record only page counts, date/timestamp bounds, page order,
duplicate/gap facts, continuation availability, and sanitized outcomes. Rows,
prices, cursors, credentials, account values, and response bodies remain in
memory. The completed private daily collector used the observed two-page
boundary as a pacing fact. The capacity maps still do not by themselves prove a
general archive, model-input contract, or order-endpoint capability.

## KIS Private Daily Collector v1

`kis-paper-private-daily-collector-v1` completed at `2026-07-21T14:52:28Z`.
It used only `dailyprice` / `QQQ` / `NAS` / `MODP=0`, one KIS Paper token, two
daily pages, and one measured two-second inter-page delay. It retained 199
unique daily rows from 200 input rows after removing one exact overlapping
date. The private raw file lives only under
`D:\market_data\us_equities\kis_paper_private\daily`; its SHA-256 is
`13a904a2e68c0405535fd67d96bd2b630036cc76ddc3d6b9d2a016e229291c4d`.

The atomic manifest is
`D:\market_data\us_equities\kis_paper_private\daily\snapshot=20260721T145228Z-qqq-nas-modp0-v1\manifest.json`
with SHA-256
`f124f47187ee5c3f2d1d840cd56de47a79ca4a8577026c5afbccef2c07b05c10`.
Its raw-aware control record reached `completed` / `complete` and records
`raw_market_data_retained: true`. This is an actual retention fact, not a
one-shot restriction; historical metadata-only markers remain `false` only
because those old runs stored no raw rows.

The next data job may continue this cache through paced, resumable chunks under
the standing KIS Paper authority. Keep the cache private and local, preserve
manifest/hash/provenance facts, and do not infer a general archive entitlement,
model result, or order-transport support from this first snapshot.

## Resumable KIS Private Daily Backfill v1

Run one bounded chunk with:

```powershell
uv run python scripts\backfill_kis_paper_private_daily.py --execute
```

The worker is a concrete data job, not a daemon. It reattests its external
index, recovers a matching orphan snapshot before reading credentials or making
a new KIS call, then selects one ready symbol/date cursor. A chunk obtains one
paper token, requests at most two `dailyprice` pages, verifies a two-second
inter-page delay, stores an immutable raw snapshot/manifest on `D:`, verifies
the raw hash, and atomically advances only that symbol's logical date cursor.
Exact overlaps are retained as dedupe facts; differing overlapping values defer
the affected symbol without cursor advancement.

The index is at
`D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json`.
Its first data-bearing routes are `QQQ/NAS`, `SPY/AMS`, and `IWM/AMS`; each
initial chunk retained 199 unique rows from 200 inputs. The persistent index,
not this document, records each current logical cursor. Earlier NYS attempts
are retained as venue-attempt evidence only:
the SPY token call rejected before a daily response and IWM returned an accepted
empty page. They are not data-bearing mappings.

After a KIS token rejection or a completed network chunk, respect the index's
shared retry timestamp before another worker invocation. The current two-minute
spacing is a source-adaptive transport measure based on observed token behavior,
not a capital, approval, or model-quality gate. Do not bypass it by running a
second copy of the script. The worker never reads `KIS_LIVE_*`, calls live,
stores raw data in Git, prints raw rows, or publishes KIS-originated data.

## KIS Paper Authority

KIS Paper is standing operator-approved development authority for this private
project. Codex may read `KIS_PAPER_*`, query market/account/order facts, submit,
modify, and cancel virtual-paper orders, choose routine paper sizing, and run
goal-owned schedules without an additional capital-envelope, profitability,
report, dashboard, or canary-approval gate.

The only live boundary is absolute: never read `KIS_LIVE_*`, call a live route,
or enable real-money behavior. The web process remains credential-free.

For every paper side effect, persist an idempotent intent first and reconcile an
unknown broker outcome before sending a replacement. This is a technical
recovery rule, not an operator-approval gate. Schedulers may run ordinary paper
work when they preserve the same paper-only route and reconciliation behavior.

## Recovery

At task start, after interruption, and before relying on a checkpoint:

1. Inspect nonterminal role jobs and real process/container identity.
2. Verify input, dataset, code/runtime, checkpoint, and committed output hashes.
3. Classify each active run as `resume`, `restart`, `reconcile`, `complete`,
   `unrecoverable`, or `operator`.
4. Reconcile every Execution `outcome_unknown` before another submission.
5. Persist changed classifications and actions in the shared ledger when that
   substrate exists.
6. Tell the operator only about anomalies, unresolved exposure, lost evidence,
   or a decision they actually own.

Do not produce recovery packets or success reports.

## Emergency Actions

`stop new orders` prevents new entries and persists across restart. Exits and
cancellations remain available.

`cancel open orders` enumerates confirmed open broker orders, requests
cancellation, records each outcome, and reconciles again. Never cancel or
flatten from stale local state.

Resume requires clean reconciliation and an understood bounded failure. Claude
challenges recovery after an unexplained broker, data, holdout, or risk incident;
the operator retains final authority for unresolved exposure or live behavior.

## Daily Operator Review

When 08:00 KST automation is enabled, generate one concise human-facing summary:

- company objective and outcomes,
- active mode and execution/recovery anomalies,
- after-cost research or paper metrics,
- data coverage and exact operator data requests,
- running Data/Research/Execution work,
- the canonical `NEXT_CODEX_GOAL.md` link,
- every prioritized decision that only the operator can make, with duplicate or
  dependent questions consolidated but no arbitrary count limit.

Machine-readable metrics may stay in the shared external evidence substrate.
Do not create a daily copy of the next goal.

## Verification

Before committing and pushing completed work:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Run additional focused tests for changed behavior. Report anything that could
not be run.
