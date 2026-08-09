# TheRicher v2 Handoff

## Product Direction

TheRicher v2 is a private, reproducible U.S.-equity research and KIS Paper
engine. Its product loop is causal market data -> frozen research contract ->
backtest/walk-forward evidence -> local-paper replay -> KIS Paper execution
evidence -> PnL attribution. KIS Paper is early execution evidence, not a
reward for a profitable model. `KIS_LIVE_*` is unavailable.

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the one active company
objective. The stateboards are concise current projections only; Git and
immutable external artifacts retain history.

## Active Company Objective

`task-owned-kis-intraday-causal-evidence-refresh-v1` will classify one later
caller-selected `thericher-kis-paper-intraday-head` completed-session result
for the QQQ/NAS and SPY/AMS M1 causal input.

The latest terminal, `intraday-head-20260807T2120007624227Z`, reattached
offline as `complete`, but its exact capture binding has cumulative coverage
`incomplete`; decision-time availability and provider finality are both
`not_observed`. Its exact input is therefore
`input_unavailable/session_coverage_incomplete`. This is neither a KIS fault
claim nor a model, Paper, fill, PnL, or alpha result.

The offline terminal reader can now consume an optional, separately
hash-bound causal-condition attestation. It is default-deny: no current task
emits that binding, so the reader exposes `not_recorded` and cannot promote the
current or next task result by itself. A future bound attestation must retain
the named clock, `America/New_York` DST/session rule, completed-bar geometry,
non-overlapping boundary, decision-time availability, and provider-finality
categories. This is still marker-present local provenance under an assumed
honest host, not cryptographic proof of provider origin.

Only the installed intraday-head task may produce the next candidate. Its next
owned sequence begins at 2026-08-11 00:29 KST, with runs at 00:29, 02:28,
04:24, and 06:20. Only the 06:20 post-close terminal is an eligible
completed-session candidate. Do not manually invoke the task, Docker profile,
KIS client, or a replacement collector.

## Current Cross-Lane Facts

| Lane | Current fact | Next valid action |
| --- | --- | --- |
| Data | QQQ/SPY current causal chain is `input_unavailable`; the optional causal-attestation binding is `not_recorded`, and historical M1 cursor data has 21 shared complete sessions. | Installed task creates the next evidence chain; reattach it offline after the 06:20 terminal. |
| Data | The 2026-08-09 host-only Norgate tail probe is `unavailable/local_source_unavailable`; D: file freshness is not a vendor-access or rights proof. Tiingo/Norgate and broad-D1 sources remain non-promoting. | Do not retry Norgate until Norgate Data Updater shows an active US subscription and configured database location, then run one bounded probe. |
| Engine Research | No frozen, input-qualified predictive campaign exists. Fixed QQQ local-paper EMA and Donchian baselines are negative and closed for selection. | If and only if a later qualified input arrives, freeze one existing 30/60/90-minute candidate matrix; do not train in the current objective. |
| Research Steward | RTX 4090 is healthy but unallocated. | Allocate only a frozen, eligible campaign; never manufacture training to fill GPU time. |
| Execution | Loopback-only Paper dashboard and read-only observer are complete; no live route exists. A source-safe audit of the latest eight quote-session lifecycle receipts confirms five `cancelled/clean` submissions, two scoped `outcome_unknown` results, and the latest `not_submitted/unresolved` result. Its closed pre-submit disposition is `reconciliation_unavailable`. | Treat the latest non-submission as its exact run's reconciliation limitation, not a global route hold. Keep scheduled execution evidence owned by its task and consume no intraday data result without a later qualified objective. |
| Shared worktree | Alternate IWM collector WIP is untracked/modified and rejected from this objective. | Do not touch, stage, invoke, or reconcile it without a separate assignment. |

## Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| QQQ/SPY intraday causal evidence | Data | Installed `thericher-kis-paper-intraday-head` task owns the next sequence. Its source-local availability receipt and any pair attempt must bind the same contract, receipt, precommit, and summary hashes. |
| SPY D1 stability | Data | Existing observer owns the next 2026-08-10 23:15 KST observation. Its status is observational only, never provider finality. |
| Virtual-Paper lifecycle canary | Execution | Existing task owns the next 2026-08-10 23:35 KST opportunity. The latest exact canary is `intent_recorded/not_submitted/unresolved` with closed pre-submit disposition `reconciliation_unavailable`; five of its eight most-recent source-safe peers completed `submitted -> cancelled/clean`, so that anomaly is not a global route hold. It is not a submit, fill, PnL, or model result. |
| Read-only Paper account observer | Execution | Existing four-minute task is the sole owner. Its validated provenance is marker-present under an assumed-honest host, not cryptographic Scheduler-origin proof. |
| Public-source research | Engine Research | Qlib and PatchTST are source-only architecture references, with no code, package, data, weight, campaign, GPU, or Paper consequence. |

External quota and session waits belong to their named task. Codex does not
foreground-sleep or add a duplicate scheduler while an independent package is
ready.

## Current Guardrails

- Never read or route `KIS_LIVE_*`.
- Keep raw market data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts`; neither belongs in Git.
- A qualified research input must retain exact provenance, completed-bar
  geometry, chronological split, decision-time availability, and finality
  facts. A missing condition narrows that input only; it is never a global
  approval hold.
- These are necessary/default-deny local reconstruction conditions, not
  cryptographic provider-origin proof. A future `qualified` designation must
  name its clock authority, timezone/DST session rule, and non-overlapping
  chronological boundary; otherwise it remains a scoped unavailable input.
- The causal-attestation reader is offline-only and has no writer or scheduler
  change in the current objective. A synthetic fixture proves its default-deny
  branch only; it is not a provider evidence claim.
- Model output remains untrusted until deterministic Execution validation.
  Local replay fills retain `source: local_paper`.

## Evidence Index

- Current intraday terminal reader:
  `scripts\project_kis_paper_intraday_head_schedule_receipt.py`.
- QQQ M1/M5/M10/H1/H3 mechanics:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-resampling-mechanics-v1\20260807-qqq-mtf-r1\summary.json`.
- Fixed local-paper EMA attribution:
  `D:\thericher-v2\model-artifacts\research\source-local-ema-local-paper-pnl-attribution-v1\20260807-ema-pnl-attribution-r1\summary.json`.
- Fixed local-paper Donchian attribution:
  `D:\thericher-v2\model-artifacts\research\source-local-qqq-donchian-local-paper-pnl-attribution-v1\20260807-donchian-pnl-r1\summary.json`.
- Qlib source-only receipt:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\qlib-architecture-source-20260809-r1\source-retrieval.json`.
- PatchTST source-only receipt:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\patchtst-source-20260809-r1\source-retrieval.json`.

## Verification And Git

The causal-attestation reader package passed 59 focused offline receipt tests,
Ruff, and `git diff --check`; it makes no KIS, Docker, network, credential,
order, or scheduler call. Use Git history for immutable commit checkpoints
rather than copying a self-staling latest hash here.

## Resume Procedure

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `NEXT_CODEX_GOAL.md`, this handoff, `AGENTS.md`, `RUNBOOK.md`, and the
   active stateboards.
3. Run a compact Throughput Review, then dispatch only a ready,
   non-conflicting package.
4. After the next task-owned terminal, use only offline source-safe readers to
   classify its exact evidence; preserve a scoped unavailable result or freeze
   the next candidate only when every stated condition is evidenced.
