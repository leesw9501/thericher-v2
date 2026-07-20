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
These workers are not daemons, schedulers, or autonomous coordinators. Verify a
stale lock against the real process/container before changing it.

Execution has no executable worker yet. Use temporary role workers and fake
transports until a recurring KIS paper objective justifies one bounded
single-shot worker.

## Data Acquisition

Use `D:\market_data`. Never download market data into the repository.

Data may be acquired automatically when it is useful, no-cost, no-auth,
license-compatible for private use, bounded, and deduplicated. Paid, logged-in,
manual-agreement, private-API, or unclear-rights sources require operator
approval.

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

A one-shot response is always `observed` or `rejected`, never a promotion. Its
external attempt marker records `reserved -> network_started -> summary_written`;
if summary persistence fails, `network_started` remains and blocks retry. A
future, independently scoped Data objective may assess timestamp-label evidence
and ask Claude before any capability update.

## KIS Paper Authority

KIS paper should begin before model profitability when execution hard stops are
ready. Use a deterministic baseline for the first live-like evidence loop.

Authority sequence:

1. Operator authorizes read-only KIS paper credentials and account queries.
2. Execution validates the paper endpoint and masked account identity, then
   reconciles cash, orderable funds, positions, and open orders.
3. Codex proposes a paper capital envelope based on:

   ```text
   min(reconciled KIS paper funds, intended shadow live capital)
   ```

   KRW 5,000,000 is the current planning reference, not automatic authority.
4. Operator approves or changes the envelope once.
5. A one-symbol, one-share limit-order canary proves submit, status, fill or
   cancel, event persistence, restart reconciliation, and duplicate suppression.
6. Routine paper operation may continue inside the approved envelope and hard
   limits without repeated approval.

Never size upward merely because the virtual account has large buying power.
Margin, shorting, leverage, unsupported order types, and live endpoints remain
disabled until separately approved.

Unknown broker outcomes stop new entries. Persist intent before submission,
query KIS rather than retry blindly, and reconcile by broker/account facts.

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
