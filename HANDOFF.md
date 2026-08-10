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

`kis-intraday-coverage-contract-diagnosis-v1` will determine whether the
existing QQQ/SPY current-session coverage result has a narrow deterministic
aggregation or retention defect that is repairable offline. It advances data
collection without manually invoking KIS, Docker, a task, or a scheduler, and
does not select a model, claim PnL, or authorize Paper or live execution.

The completed Tiingo IEX r1 source-isolated integration reattested the pinned
M5 snapshot in both host and Docker runtime. A gzip encoder difference was
resolved by preserving the pinned compressed hash and comparing exact canonical
payloads rebuilt from attested raw sources. Its CPU and single CUDA matrices
completed with categorical finite-run and memory-cleanup evidence; no weights,
loss values, predictions, returns, holdout, selection, KIS input, or Paper
input were created. Receipts remain external under
`D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1`.

The task-owned 2026-08-11 06:20 KST terminal differed from the prior terminal
and reattached offline at 2026-08-10T21:20:07Z as `complete`, with verified
same-run capture and availability bindings. Its cumulative current-session
coverage is `incomplete`, the optional pair binding is `legacy_unbound`, and
the exact causal input remains `input_unavailable/session_coverage_incomplete`.
Decision-time availability and provider finality remain `not_observed`; this is
a scoped Data limitation, never a hold on the Paper canary or another ready
lane.

## Current Cross-Lane Facts

| Lane | Current fact | Next valid action |
| --- | --- | --- |
| Data | The fresh terminal has verified capture/availability bindings but `incomplete` current-session coverage, `legacy_unbound` optional pair evidence, and `input_unavailable/session_coverage_incomplete`. | Diagnose only the offline aggregation/retention contract; preserve the source limitation if no deterministic defect is proved. |
| Data | The host-only Norgate loopback endpoint responds, but its own readiness status is false; its source-safe status-only response was HTTP `402`, so the installed client narrows it to `subscription_or_update_unavailable` without proving expiry versus update state. The reader stops before catalog, metadata, or price reads, and D: file freshness is not an active NDU registration, vendor-access, or rights proof. The NDU process is responsive and predates the 2026-08-09T18:34:14Z `UPDATE DONOTSHOW` request; a later hidden start only joined the existing instance. A new immutable Tiingo SPY/QQQ/IWM raw-D1 continuation through 2026-08-07 reattested offline, but Tiingo/Norgate and broad-D1 sources remain non-promoting. | Do not launch another trigger or repeat the hidden start. The next daily operating review may recheck through the source-safe readiness reader. If it remains unavailable, the one operator-visible diagnostic is the already-running NDU `Update > Check for Updates` plus database/subscription-state outcome, then minimize rather than close the app; this does not assert a cause or block the Paper canary. If NDU becomes ready, verify active US subscription and Database Location; only then, if the catalog exposes `US Equities`, run one bounded Norgate probe. Tiingo can support only retrospective controls without a new selection look or KIS/Paper join. |
| Engine Research | The Tiingo IEX r1 source-isolated CPU/CUDA runtime matrix is closed with no retained weights or predictive interpretation. The fresh QQQ/SPY terminal is not a qualified consumer input. | No candidate, training, GPU appointment, or Paper input follows; a later predictive campaign needs a distinct qualified input and frozen contract. |
| Research Steward | RTX 4090 is free after the completed Tiingo IEX r1 source-isolated appointment; no sealed evaluation was spent. | Allocate only a fresh frozen eligible campaign; never manufacture training to fill GPU time. |
| Execution | The existing 2026-08-10 quote-session receipt reattached offline as `canary_completed -> cancelled / clean`, with `paper_only` scope and attribution `not_eligible`. Scheduler result was `0`; the route/image and credential-free loopback health remained virtual-only/no-broker-call. | Lifecycle closure is complete. The existing task alone owns future canaries; do not infer a fill, PnL, alpha, or model result from this exact run. |
| Shared worktree | Alternate IWM collector WIP is untracked/modified and rejected from this objective. | Do not touch, stage, invoke, or reconcile it without a separate assignment. |

## Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| QQQ/SPY intraday coverage diagnosis | Data | Credential-free inspection of the existing current-head aggregation/retention contract is ready. It must use only source-safe receipts and metadata, never raw M1 rows or a duplicate collector. |
| SPY D1 stability | Data | Existing observer owns its next eligible weekday observation. Its status is observational only, never provider finality. |
| Virtual-Paper lifecycle canary | Execution | Closure evidence is complete: the 2026-08-10 owned task produced `canary_completed -> cancelled / clean`, `paper_only`, and attribution `not_eligible`. It is not a fill, PnL, or model result; future canaries remain task-owned. |
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
The 2026-08-11 intraday terminal closure used only the existing offline reader
and source-safe task facts. It passed 85 focused receipt/capture/schedule tests,
the 2,931-pass authority parallel suite with 17 skips, Ruff, both Compose
configuration parses, and `git diff --check`.
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
