# Next Codex Goal

## Objective

Run one finite, offline source-separated engineering batch using only the
verified r4 contract. Complete a CPU baseline first, then exactly two bounded
PyTorch CUDA MLP jobs. This opens CUDA as a measured research resource, not an
open-ended parameter sweep or an investability claim.

## Fixed Contract

- Contract:
  `D:\thericher-v2\model-artifacts\norgate-tii-source-separated-contract\norgate-tii-source-separated-contract-r4\contract.json`
  with SHA-256
  `ddba0d578bf5ddaefe10c0c72b63ad8873a27c2243787e504d3c4e8fac0bf76e`.
- Parents: the completed Tiingo/Norgate cohort and Norgate broad feature
  artifact reattested by that contract. Do not reopen the static 523-symbol
  MLP/TCN batch or use its runner as this batch's runner.
- Norgate is the sole price, feature, and label source. Tiingo may provide only
  contract-attested rank/session/marker lineage. The 18 Tiingo forward-only
  sessions are forbidden.
- Use the exact `(rank, symbol)` roster and retained source rows in the
  contract. Fit only decision indices `20..319`; use `320..321` neither for fit
  nor evaluation; evaluate `322..480` once with no tuning or candidate choice.
- The Norgate raw-discontinuity filter uses `t-20..t+2`; it is static offline
  conditioning, not point-in-time safe and not a corporate-action assertion.

## Required Batch

1. Reattest the r4 contract and parents on host before any model array is made.
   Prove the batch loader selects Norgate rows only, preserves the contract mask
   and exact split, and does not expose Tiingo prices/labels or forward sessions.
2. Implement the smallest dedicated batch harness. It must write only compact
   run evidence and safe model/checkpoint artifacts under
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never Git.
3. Run the fixed CPU baseline first: `naive_always_long` and one
   regularized-linear classifier. Record deterministic development and one-time
   validation metrics, but do not compare them to select a winner.
4. If the CPU baseline and CUDA availability are sound, use the Docker
   `research` profile with network disabled to run, exactly once each:
   - `mlp-hidden-32-seed-71`, 12 epochs, batch size 1024;
   - `mlp-hidden-64-seed-113`, 12 epochs, batch size 1024.
   Run one GPU job at a time. Enforce a 180-second wall-clock and 4,096-MiB
   per-job cap. Preserve bounded failure evidence and do not retry automatically.
5. Keep `agents/engine-research.md` explicit: this is the breadth queue's sole
   active finite batch; depth and ensemble queues remain blocked. Data has no
   new download task while this batch runs.
6. Ask Claude for a concise falsification-first review before interpreting an
   unexpectedly strong result or changing the batch. Use temporary independent
   Validation after the run; it must not tune a candidate.
7. Refresh stateboards, `HANDOFF.md`, `DECISIONS.md`, and this next goal after
   the batch. Continue with the smallest evidence-led objective; do not wait for
   routine operator scheduling.

## Hard Boundaries

- Do not call network providers, KIS, brokers, or local-paper execution.
- Do not read `.env`, credentials, account data, or secret-like files.
- Do not create PnL, paper, ranking, promotion, ensemble, sealed-holdout, or
  profitability claims.
- Do not add a tree, TCN, extra seed, extra parameter sweep, depth candidate,
  or automatic retry.
- Do not use GPU utilization by itself as a success metric.

## Tests And Verification

Add focused tests for contract-only loading, development-only fitting,
purge/validation isolation, no network/credential/broker access, bounded CUDA
configuration, external-only artifact placement, and replayable artifact
metadata. Then run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the CPU/CUDA commands, GPU availability and observed resource caps,
external artifact paths/hashes, failures if any, Claude/Validation verdicts,
and why no broader model search was opened.

## Suggested Commit Message

`Run finite source-separated research batch`
