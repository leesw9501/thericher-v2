# Next Codex Goal

## Objective

Build the first bounded, broad-panel development validation loop from the
completed Norgate trial panel. The loop must reattest external data lineage,
freeze one no-holdout chronological research contract, run CPU baselines, and,
only when that preparation is sound, run one finite serial PyTorch CUDA breadth
batch. This is engineering research only, not a strategy-selection, paper, or
profitability result.

## Ownership

- **Data Agent:** owns the smallest offline, hash-reattesting loader or feature
  materializer for the exact external panel and its parent lineage.
- **Engine Research Agent:** owns the target, temporal split, costs, baselines,
  finite CUDA candidates, external artifacts, and stop rules.
- **Validation Agent:** independently checks the frozen contract and completed
  artifacts without tuning a candidate. It does not open a sealed holdout.
- **Review/Claude:** gives a concise falsification-first review before the
  static-panel contract is relied on or CUDA work begins.

## Fixed Inputs And Boundaries

- Use only
  `D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`
  with data hash
  `sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`
  and manifest hash
  `sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
  Reattest its membership and fixed-ETF calendar parents before each consumer.
- Keep the 523 selected static candidates, 18 recorded session mismatches, and
  483 returned sessions from 2024-07-18 through 2026-06-22 fixed. Do not use
  membership rows to choose samples, infer point-in-time membership, fill gaps,
  repair bars, merge sources, or broaden the panel.
- Requested `NONE` adjustment semantics, corporate-action timing, historical
  coverage, and point-in-time universe truth remain unproven. Every artifact and
  result must retain those limitations and remain development-only.
- Do not call KIS, read `.env`, credentials, tokens, broker state, or secret-like
  files. Keep `THERICHER_MODE=off`; submit no order and make no broker/network
  data call. Existing local-paper fills, if a unit test reaches them, keep
  `source: local_paper`.
- Do not query Norgate from Docker. Raw panel bytes remain under `D:\market_data`.
  Derived features, contracts, metrics, checkpoints, and recovery metadata stay
  under `D:\thericher-v2\model-artifacts` and use `/app/model_artifacts` in
  Docker. Retain an external Norgate deletion/rights linkage for every derived
  artifact; never store data, model, or generated artifact bytes in Git.
- Check free space before external writes; warn below 20 percent and stop new
  acquisition or training before the 15 percent hard floor. Do not add a
  scheduler, daemon, queue framework, dashboard, report family, model-serving
  path, or public endpoint.
- A sealed holdout, model promotion, model ranking, ensemble, KIS paper, live
  behavior, and profitability claim are out of scope regardless of metrics.

## Required Work

1. Ask Claude for a concise falsification-first review of the proposed
   development-only target, feature timestamps, static-panel survivorship and
   corporate-action risks, chronological split, naive baseline, strongest kill
   test, and the fact that stops CUDA. Do not send rows, symbols, raw labels,
   secrets, or account information.
2. Reuse existing Data and campaign contracts where they fit. Add only the
   smallest offline verifier/loader and feature-target materializer needed to
   expose the exact panel to Research while reattesting its full parent lineage.
   Freeze one completed-close decision target with an explicit future outcome,
   a time-ordered development/validation split, costs, purge/embargo, fixed
   feature lookback, deterministic seeds, and no sealed holdout.
3. Run CPU smoke baselines first: at minimum flat/naive direction and one
   deterministic linear baseline. Record feature/label counts, split boundaries,
   no-lookahead proof, class/return distribution, and all lineage hashes in an
   external immutable run directory. CUDA is eligible only if these checks pass;
   a baseline need not be profitable or beat another baseline.
4. If CUDA is available in the existing PyTorch research container and the CPU
   contract passes, run exactly four serial development-only GPU jobs: compact
   MLP and compact temporal-convolution candidates, each with two fixed seeds.
   Record device, CUDA peak memory, input/contract hashes, per-job metrics,
   checkpoints using safe loading, and stop reason. Do not tune after observing
   validation metrics, auto-refill the queue, or select an ensemble.
5. Have Validation independently reattest the frozen inputs and completed run
   artifacts, check that no broker/network/credential access occurred, and label
   the outcome engineering-only. Unexpectedly strong output, leakage evidence,
   or a material baseline claim requires a new Claude review before any later
   promotion decision.
6. Refresh `HANDOFF.md`, the Data and Engine stateboards, `DECISIONS.md`, and
   this goal before continuing. Keep the short and long research queues visible:
   the completed finite breadth batch becomes input to a later depth decision,
   never an automatic queue refill.

## Stop Rules

- Stop before CUDA if parent hashes, session ordering, feature/label timestamps,
  temporal split, CPU baseline, artifact root, or rights/deletion linkage fails.
- If CUDA or the research image is unavailable, preserve the CPU evidence and
  prepared immutable contract, record `prepared_not_run`, and continue safe
  independent work rather than retrying blindly.
- Stop and seek a new bounded goal on a source-rights ambiguity, storage-floor
  breach, corrupt external artifact, or any condition that would require
  credentials, broker access, data acquisition, or a model/paper/live decision.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Also report the focused CPU baseline command and, if run, the Docker CUDA
command, CUDA device/memory result, external artifact paths, Claude verdict,
and every stop condition triggered.

## Suggested Commit Message

`Add broad development validation loop`
