# Next Codex Goal

Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
`agents/data.md`, `agents/engine-research.md`, `agents/research-steward.md`,
and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run one fixed CPU-only source-local rule diagnostic:
`norgate-d1-trio-momentum-falsification-v1`.

It uses the hash-attested fixed `SPY/QQQ/IWM` local Norgate D1 snapshot to
falsify a simple cross-ETF momentum rule. It is not a trained model, source
promotion, profitability/PnL claim, Paper input, order, account operation, or
live route.

## Frozen Contract

- Consume only the existing local D1 source whose dataset hash is
  `sha256:efa1b14ff60c6a107688179617d428546de68ca1d1756c62292e1206e15c58e7`
  and whose manifest hash is
  `sha256:7f30253d035f248889849b7a9a5933cdc41b2f2525b405690ef653ca69a33d45`.
  Resolve it only below `D:\market_data`; do not record its local path in Git
  or artifacts.
- Require exactly 511 common completed D1 sessions for `SPY`, `QQQ`, and
  `IWM`. The requested source setting was `NONE`, but adjustment,
  corporate-action, availability-time, and point-in-time semantics remain
  unverified and must stay visible in the receipt.
- Split the common-session sequence chronologically into `350 development /
  21 purge / 140 validation` sessions. Do not tune on any development or
  validation target.
- At each eligible completed session `t`, form only target-free features from
  the 20 completed prior sessions through `t`: each ETF's raw close-to-close
  20-session return. The fixed rule is `SPY long` only when all three returns
  are strictly positive; otherwise `flat`.
- A decision at completed `t` is evaluated only against the sign of raw SPY
  `open[t+2] / open[t+1] - 1`, so the earliest entry is the next completed
  session's open. A strictly positive target is a hit; zero or negative is not.
  Build all validation decisions before reading validation target signs.
- The rule's hit rate uses its long decisions only. The frozen naive comparator
  is always-long SPY across every structurally eligible validation slot, so it
  tests whether the rule's selection changes directional frequency. This is a
  directional diagnostic only: do not calculate costs, fills, cash, strategy
  PnL, aggregate trading returns, or profitability.
- Reject the exact rule if it has fewer than 30 validation long decisions or
  its validation directional hit rate is not strictly greater than the
  always-long comparator. A non-rejection is only
  `inconclusive_non_promoting`, never a candidate, survivor, ensemble member,
  GPU appointment, or reason to reuse this validation slice for tuning.

## Boundaries

- Do not call KIS, read `.env` or credentials, access accounts, submit/modify/
  cancel orders, use local-paper, or enable live behavior.
- Do not call the Norgate client, network, GPU, model weights, or training
  code. Reattest and consume the retained snapshot offline only.
- Do not write raw bars, dates, prices, labels, per-row decisions, paths,
  model artifacts, or credentials to Git or artifacts. Write an aggregate-only
  receipt under `D:\thericher-v2\model-artifacts`.
- Do not add a generic research platform, scheduler, provider, or dashboard.
  Keep the implementation to one loader/diagnostic/runner path and focused
  tests.

## Required Work

1. Implement the frozen offline loading, target-free decision construction,
   chronological split, directional comparator, rejection semantics, and
   idempotent aggregate-only receipt path.
2. Run the one real CPU diagnostic against the retained D: snapshot using an
   external run label. Reattest the source hash before reading rows.
3. Add focused tests for source hash/manifest pinning, common-session/split
   requirements, completed-bar causality, validation-target isolation,
   no-tuning rejection semantics, receipt redaction/idempotence, and absence
   of KIS, credential, broker, account, local-paper, GPU, and live surfaces.
4. Keep the result non-promoting regardless of outcome. Update Engine Research,
   Research Steward, Data, orchestration, handoff, and decisions state only
   with source-safe aggregate facts.

## Claude Context

Claude returned `supported-with-limits` for this exact falsification-only
scope. Codex accepts the split, completed-bar, comparator, and no-reuse limits,
but does not treat the requested `NONE` adjustment setting as proof that the
historical bars are point-in-time tradable. Claude did not grant a promotion,
Paper, GPU, or model-training boundary.

## Verification

```powershell
uv run --extra dev pytest -q <focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

## Completion

Report the frozen rule/contract, source-safe CPU outcome, external receipt,
tests, commit hash, intentional omissions, and the next recommended objective.
Replace this file with exactly one next objective only after completion evidence
is committed and pushed.
