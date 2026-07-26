# Next Codex Goal

## Objective

Build the first bounded KIS-native daily sequence-model breadth screen.

Use the already qualified QQQ/SPY KIS-private-daily history to screen compact,
materially different sequence families through offline local-paper replay. This
advances model research while prospective intraday collection continues on its
own schedule; it is not a model promotion, ensemble selection, broker order,
or live behavior change.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, DECISIONS.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest the existing KIS daily catalog without a KIS call. Locate and use
   the smallest existing offline loader/attestation path; do not scan raw files
   ad hoc or make a network request. The expected starting point is
   `load_kis_paper_private_daily_catalog`, not the intraday coverage inspector.

## Required Work

1. Ask Claude CLI for a concise falsification-first review of the campaign
   contract before interpreting any result. State the dataset scope, target,
   chronological split, leakage/survivorship checks, naive baseline, GPU
   budget, kill case, and the fact that would rule out a candidate. An expired
   CLI session is scoped tooling evidence, not a hold on this private
   development-only screen.
2. Freeze one QQQ/SPY-only KIS-native daily contract from the already qualified
   common history. It must name source identities, causal completed-bar feature
   windows, next-open execution timing, chronological development/validation
   split, purge, cost model, local-paper replay contract, fixed compute budget,
   and stop rule. Do not use IWM or another provider to fill gaps.
3. Implement the smallest reusable offline runner for a deterministic CPU smoke
   and one bounded Docker CUDA screen of compact LSTM, causal TCN, and compact
   attention-style candidates, or document a code-backed reason an existing
   architecture cannot support the daily contract. Reuse approved PyTorch CUDA;
   do not download weights or change the major runtime.
4. Keep all checkpoints, work state, and safe summaries under
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`. The runner
   must remain offline after the cache load and never read credentials, call
   KIS, submit an order, use a broker account route, or emit raw rows/prices.
5. Add focused tests for causal feature/label timing, Data provenance, CPU
   smoke determinism, CUDA artifact location/mocking, local-paper-only fills,
   chronological validation, and no model/ensemble/promotion claim. Keep the
   validation role independent of tuning.
6. Run the CPU smoke first. If CUDA is available and the contract passes,
   execute one bounded Docker GPU screen and record only source-safe external
   evidence. A failed/no-CUDA result is a scoped recoverable fact; it does not
   block Data collection or Paper execution preparation.

## Hard Boundaries

- Keep raw market data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- Do not read credentials, call KIS, enable live behavior, or call account,
  position, order, cancel, or modify endpoints in this goal.
- Do not print, log, commit, or send secrets, account identifiers, raw broker
  payloads, raw prices, or sealed holdout labels to Claude.
- Do not open a sealed holdout, tune against validation results, select a model,
  create an ensemble, make a profitability/Paper-order claim, or treat GPU
  utilization as the goal.

## Claude Check

The 2026-07-26 KST worker and profile-review attempts found the local Claude
CLI OAuth session expired; no private material was sent. Retry for the campaign
contract before interpreting results. A repeat OAuth failure is scoped tooling
evidence, not an approval gate for this private non-live work.

## Completion Evidence

- Test-backed, source-separated QQQ/SPY daily campaign contract and offline
  runner with no credentials, network, broker, or repository artifacts.
- A deterministic CPU smoke and, when CUDA is operational, one bounded Docker
  GPU architecture screen with checkpoints and summaries outside Git.
- Development-only local-paper validation evidence with no selection,
  ensemble, promotion, holdout, or Paper-order claim.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Data-local schedule wait, GPU fault, or failed
candidate does not stop another ready lane.
