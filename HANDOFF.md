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

`kis-paper-canary-lifecycle-closure-v1` will reattach one eligible lifecycle
from the existing `thericher-kis-paper-quote-session` task. It is execution
readiness evidence only: the durable result may be no intent, intent-only,
submitted/cancelled, or scoped unknown/recovery. It does not select a model,
claim PnL, or authorize live behavior.

The completed Tiingo IEX r1 source-isolated integration reattested the pinned
M5 snapshot in both host and Docker runtime. A gzip encoder difference was
resolved by preserving the pinned compressed hash and comparing exact canonical
payloads rebuilt from attested raw sources. Its CPU and single CUDA matrices
completed with categorical finite-run and memory-cleanup evidence; no weights,
loss values, predictions, returns, holdout, selection, KIS input, or Paper
input were created. Receipts remain external under
`D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1`.

The separately owned QQQ/SPY intraday causal chain remains
`input_unavailable/session_coverage_incomplete`; its optional causal attestation
is `not_recorded`. It is a scoped Data limitation, never a hold on the Paper
canary or another ready lane.

## Current Cross-Lane Facts

| Lane | Current fact | Next valid action |
| --- | --- | --- |
| Data | QQQ/SPY current causal chain is `input_unavailable`; the optional causal-attestation binding is `not_recorded`, and historical M1 cursor data has 21 shared complete sessions. | Installed task creates the next evidence chain; reattach it offline after the 06:20 terminal. |
| Data | The host-only Norgate loopback endpoint responds, but its own readiness status is false (`local_api_not_ready`); the reader stops before catalog, metadata, or price reads, and D: file freshness is not an active NDU registration, vendor-access, or rights proof. The NDU process is responsive and predates the 2026-08-09T18:34:14Z `UPDATE DONOTSHOW` request; a later hidden start only joined the existing instance, and readiness remained unavailable. A new immutable Tiingo SPY/QQQ/IWM raw-D1 continuation through 2026-08-07 reattested offline, but Tiingo/Norgate and broad-D1 sources remain non-promoting. | Do not launch another trigger or repeat the hidden start. The next daily operating review may recheck through the source-safe readiness reader. If it remains unavailable, the one operator-visible diagnostic is the already-running NDU `Update > Check for Updates` outcome, then minimize rather than close the app; this does not assert a cause or block the Paper canary. If NDU becomes ready, verify active US subscription and Database Location; only then, if the catalog exposes `US Equities`, run one bounded Norgate probe. Tiingo can support only retrospective controls without a new selection look or KIS/Paper join. |
| Engine Research | The Tiingo IEX r1 source-isolated CPU/CUDA runtime matrix is closed with no retained weights or predictive interpretation. Fixed QQQ local-paper EMA and Donchian baselines remain negative and closed for selection. | A later predictive campaign needs a distinct qualified input and frozen contract; it is not part of the Paper lifecycle objective. |
| Research Steward | RTX 4090 is free after the completed Tiingo IEX r1 source-isolated appointment; no sealed evaluation was spent. | Allocate only a fresh frozen eligible campaign; never manufacture training to fill GPU time. |
| Execution | Loopback-only Paper dashboard and read-only observer are complete; no live route exists. On 2026-08-10 the existing receipt bridge/local simulator revalidated as broker-free with deterministic `local_paper` replay, and the quote-session task, local image, receipt reader, and categorical dashboard health reattested offline; no new lifecycle receipt exists after 2026-08-07. The task remains the sole owner of the current KIS lifecycle proof. | Reattach its next eligible receipt without duplicating task, container, or submission. Treat any non-submission or unknown state as exact-run scoped. |
| Shared worktree | Alternate IWM collector WIP is untracked/modified and rejected from this objective. | Do not touch, stage, invoke, or reconcile it without a separate assignment. |

## Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| QQQ/SPY intraday causal evidence | Data | Installed `thericher-kis-paper-intraday-head` task owns the next sequence. Its source-local availability receipt and any pair attempt must bind the same contract, receipt, precommit, and summary hashes. |
| SPY D1 stability | Data | Existing observer owns the next 2026-08-10 23:15 KST observation. Its status is observational only, never provider finality. |
| Virtual-Paper lifecycle canary | Execution | Existing task owns the next eligible opportunity. Its result monitor reattaches only source-safe lifecycle evidence for the current objective. The latest exact canary is `intent_recorded/not_submitted/unresolved` with closed pre-submit disposition `reconciliation_unavailable`; five of its eight most-recent source-safe peers completed `submitted -> cancelled/clean`, so that anomaly is not a global route hold. It is not a submit, fill, PnL, or model result. |
| QQQ provisional runtime observation | Execution | Embedded in the existing intraday-head task. Its v5 validator recomputes the cache/window and exact non-promoting grade; do not manually invoke or duplicate it. |
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
- Tiingo raw-D1 source-safe receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\tiingo-etf-d1\4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2.json`.
- Tiingo IEX r1 source-isolated CUDA receipt:
  `D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1\r1-cuda-20260810-r1\summary.json`.

## Verification And Git

The Tiingo IEX source-isolated package passed 19 focused data/research tests,
the 2,919-pass authority parallel suite with 17 skips, Ruff, both Compose
configuration parses, and `git diff --check`. The CPU and CUDA Docker commands
were networkless and wrote only external source-safe summaries. The suite also
repaired three pre-existing test-contract mismatches exposed by the local Torch
runtime; no KIS, credential, broker, or scheduler call occurred in verification.
The 2026-08-10 quote-session route reattestation added one no-public-port
contract and passed 123 focused execution tests, Ruff, and both Compose parses;
it did not call KIS, start a task/container, or read a private receipt body.
Use Git history for immutable commit checkpoints rather than copying a
self-staling latest hash here.

## Resume Procedure

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `NEXT_CODEX_GOAL.md`, this handoff, `AGENTS.md`, `RUNBOOK.md`, and the
   active stateboards.
3. Run a compact Throughput Review, then dispatch only a ready,
   non-conflicting package.
4. Reattach the next eligible existing quote-session receipt only after its
   owned task writes it. Preserve a scoped unavailable or unknown result; never
   infer an outcome or issue a duplicate Paper submission.
