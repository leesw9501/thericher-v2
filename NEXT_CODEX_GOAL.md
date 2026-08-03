# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-broad-d1-geometry-audit-and-event-censored-candidate-v1`: explain
the first KIS broad-D1 candidate's fixed within-bar geometry failure with a
bounded, source-safe audit, then freeze and run at most one distinct causal
event-censoring CPU preflight if its explicit input contract is satisfied.

This is a source-local development objective, not a profitability or source
quality claim. A failed audit or insufficient censored input closes only the
new candidate as `input_unavailable`; it must not restart the completed broad
collector, substitute data, or create a foreground wait.

## Boundaries

- Ask Claude for one concise falsification-first challenge before changing the
  first candidate's range/event policy or opening the new CPU campaign.
- Reattach the existing broad-D1 panel/cache read-only. Do not call KIS,
  account, position, quote, or order endpoints; do not read credentials,
  submit/modify/cancel Paper orders, read `KIS_LIVE_*`, or enable live behavior.
- Preserve current-listing/non-PIT, unadjusted, corporate-action-unqualified,
  availability, and session-finality limitations. No audit/candidate result may
  become a ranking, selection, ensemble, PnL, Paper-input, or promotion claim.
- Do not silently relax the 2.0 range screen. The new candidate must state its
  distinct event definition, causal feature/target availability, target-adjacent
  censoring rule, temporal split/purge, naive baseline, strongest kill test,
  minimum coverage, artifact root, and stop rule before it opens a target.
- The Data audit may retain only aggregate counts/bins/hashes outside Git; raw
  rows, prices, symbols, targets, predictions, and weights remain on D: or in
  memory. Keep raw data under `D:\market_data` and artifacts under
  `D:\thericher-v2\model-artifacts`.
- CPU is first. CUDA is ineligible unless this new source has an actual CPU
  receipt and a separately frozen GPU contract.

## Required Work

1. Data: implement one bounded read-only geometry audit over the same selected
   panel lineage. Record source-safe ratio/event counts, affected target/session
   counts, common-session implications, and immutable input identities. Reject
   malformed/symlinked/mixed data and Docker artifact paths that are not real
   external mounts.
2. Engine Research: use that audit to freeze at most one event-censoring
   preflight. It may exclude only predeclared affected feature/target pairs;
   it must not choose symbols, windows, or thresholds after seeing model
   metrics. Preserve chronological split and availability semantics, include a
   zero baseline plus a causal/permutation falsifier, and run the actual-source
   CPU preflight when eligible.
3. Research Steward: keep GPU unallocated unless the separate CPU result
   completes and supports a new frozen CUDA request.
4. Add focused tests for aggregate-only audit output, causal censoring,
   no network/credential/broker path, external-only artifacts, and categorical
   input-unavailable containment. Refresh the Data, Engine Research, Research
   Steward, orchestration, and handoff stateboards with actual evidence.

## Completion Evidence

- one external aggregate-only geometry audit tied to the existing selected
  panel lineage;
- one separately frozen event-censoring candidate and either an actual CPU
  receipt or scoped `input_unavailable` result;
- focused tests, clean-root full parallel verification, Ruff, both Compose
  configurations, commit, and push.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
