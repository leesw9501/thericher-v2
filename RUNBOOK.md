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
unknown outcome is retried.

Market data stays private, local, and unserved. Stop only the affected cache if
applicable source terms prohibit retention or if disk policy would be crossed.
Warn before projected free space falls below 20%; do not begin new large work
that would cross the 15% floor.

## KIS Daily Backfill

The active raw daily cache is at:

```text
D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json
```

Run one bounded worker chunk:

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
never a permission switch.

Historical one-shot artifacts are non-authoritative. Their completion or
retention value must never reserve, disable, or require approval for a later
correctly scoped KIS Paper collection, account, order, or scheduler run.

If a page is repeatedly structurally invalid, diagnose only safe structure
(counts, field names, validation class, and session metadata), preserve the
failure evidence, and stop that target when the source-quality limit is clear.
Do not brute-force the same page or silently accept its remaining rows. This is
data correctness, not an approval condition for other KIS Paper or research
work.

## KIS Account Snapshot

The credential-bearing account bridge is intentionally separate from the web
process. Invoke it when current paper account facts are useful:

```powershell
docker compose --profile kis-readonly run --rm --no-deps kis-readonly
```

It writes a sanitized local runtime snapshot. Do not pass `.env` values on a
command line or emit credentials, account numbers, raw response bodies, or
tokens in logs/artifacts.

## KIS Paper Order Work

Paper order submission is authorized as soon as the Execution adapter exists.
Before sending a paper order, the implementation must prove through tests that
it cannot build a live host/route, persist an idempotent intent, and reconcile
an unknown outcome. These are code correctness requirements, not an operator
approval sequence. The dashboard remains credential-free and cannot submit an
order by itself.

## KIS Virtual-Paper Canary

The bounded execution-learning command is a virtual-paper US buy-limit canary
with one whole share, a fixed explicit limit, reconciliation, and cancellation
after an accepted submission:

```powershell
docker compose --profile kis-paper-canary run --rm --no-deps kis-paper-canary
```

It receives only `KIS_PAPER_*`, stores private recovery state in its dedicated
Docker volume, writes sanitized runtime state to the shared local dashboard,
and writes external evidence under `/app/model_artifacts`. Re-running an
existing run ID reconciles its persisted intent before any replacement submit.
Do not pass secrets or account values on the command line.

The first token attempt on 2026-07-21 returned `auth_rejected` before a
submission. This is not an approval gate. When it recurs, verify or regenerate
the **virtual-paper** application key and secret in the KIS developer account,
update only local `.env`, and rerun the command. Do not substitute live
credentials or inspect/print the secret values.

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
