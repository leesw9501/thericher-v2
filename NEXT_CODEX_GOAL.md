# Next Codex Goal

## Objective

Build one bounded, offline source-separated research-contract preflight for a
future development-only model batch. It must either freeze a small,
hash-attested contract that can later open one CPU baseline plus finite PyTorch
CUDA breadth batch, or reject that path with specific evidence. It does not
train a model in this objective.

The purpose is to turn existing data into an honest next experiment, not to
increase GPU utilization by running arbitrary parameter sweeps.

## Ownership

- **Data Agent:** reattests the completed Tiingo/Norgate cohort and supplies
  only source-separated lineage, session, rank, and conservative mask facts.
- **Engine Research Agent:** owns one frozen development-only contract with
  target timing, temporal split, costs, candidate family, compute budget, and
  stop rules. It must not launch training yet.
- **Validation Agent:** independently checks leakage, survivorship scope,
  source separation, holdout status, and whether the proposed batch is honestly
  bounded.
- **Review/Claude:** gives a concise falsification-first verdict before the
  contract can authorize a later GPU goal.

## Fixed Inputs And Boundaries

- Reuse only the completed external cohort at
  `D:\thericher-v2\model-artifacts\tiingo-norgate-cross-source-cohort\tiingo-norgate-cross-source-cohort-r1`.
  Its manifest SHA-256 is
  `sha256:dbc2b25ca514262355c9e4e2bf834889f16358058315b21eb24556b2ccdb1213`.
- Its fixed parents remain Tiingo r2 data/manifest
  `sha256:6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1` /
  `sha256:76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`
  and Norgate broad-panel data/manifest
  `sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d` /
  `sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
- Preserve the cohort's 29 linked ranks, 483 overlap sessions, 18 forward-only
  sessions, 153 returned markers, and 3,316 conservative `t-20..t+2`
  exclusions. Marker dates are returned-session markers, not event timestamps.
- Do not mix Tiingo and Norgate price fields, repair rows, infer event timing,
  call network providers, read `.env` or credentials, call KIS, submit orders,
  compute PnL, or expose a service.
- Do not reopen the completed static Norgate MLP/TCN batch, retry its TCN,
  select a model, rank candidates, open a sealed holdout, create an ensemble,
  or start CPU/GPU training in this objective.
- Keep all generated evidence under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`, not Git.

## Required Work

1. Ask Claude for a short falsification-first review before changing the
   research contract boundary. State the candidate claim, strongest kill test,
   leakage/survivorship risks, naive baseline, source-separation rule, and the
   fact that would reject the future breadth batch. Do not send rows, tokens,
   account data, or sealed labels.
2. Data reattests the existing cohort and exposes only the smallest metadata
   needed to formulate a candidate slice: parent hashes, rank linkage, session
   geometry, mask geometry, and explicit source roles. Do not loosen the
   metadata-only Engine intake or create a raw-bar export.
3. Engine writes or extends one compact immutable external research-contract
   artifact. It must predeclare one Norgate-only development source, Tiingo's
   falsification-only role, feature/target time geometry, a temporal split with
   purge/embargo, source-specific cost assumptions, naive and regularized
   baselines, a compact MLP breadth candidate, CUDA wall-clock/VRAM budget, and
   stop conditions. It must explicitly say that the result cannot rank,
   promote, paper trade, or claim profit.
4. Validation independently reattests the contract and its parents. It must
   reject any future leakage, source-price mixing, use of forward-only sessions
   as a performance holdout, action-window omission, or unexplained candidate
   selection.
5. If the contract is supported-with-limits and all checks pass, refresh the
   next goal to run exactly the predeclared finite CPU baseline and CUDA breadth
   batch. If it is unsupported or uncertain, preserve the evidence and refresh
   the next goal toward the smallest data or contract repair instead.
6. Refresh `HANDOFF.md`, Data/Engine stateboards, `DECISIONS.md`, and this goal
   before continuing. Keep the static-panel CUDA history as two completed MLP
   observations and two compute-rejected, untested TCN jobs.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the external contract path/hash or rejection evidence, Claude and
Validation verdicts, data still needed from the operator, and why GPU was or
was not opened.

## Suggested Commit Message

`Add source-separated research contract preflight`
