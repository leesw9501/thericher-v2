# Next Codex Goal

Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
`agents/data.md`, `agents/engine-research.md`, `agents/review.md`, and
`agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run one bounded offline source-value falsification:
`norgate-kis-d1-bar-conformance-v1`.

It compares the retained local Norgate D1 `SPY`/`QQQ` bars with the existing
KIS Paper private D1 `SPY`/`QQQ` history to answer only whether their
overlapping completed-bar relationships are distinguishable from an accidental
date shift or adjustment discontinuity. It is not a model, data-source
promotion, PIT proof, profitability/PnL claim, Paper input, order, account
operation, or live route.

## Frozen Contract

- Reattest the exact existing Norgate local D1 snapshot with dataset hash
  `sha256:efa1b14ff60c6a107688179617d428546de68ca1d1756c62292e1206e15c58e7`
  and manifest hash
  `sha256:7f30253d035f248889849b7a9a5933cdc41b2f2525b405690ef653ca69a33d45`.
  Read it only below `D:\market_data`; do not record its local path in Git or
  artifacts.
- Reattest only the existing private-catalog loader
  `load_kis_paper_private_daily_catalog` with target keys
  `QQQ/NAS/MODP=0` and `SPY/AMS/MODP=0`, expected index hash
  `sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660`,
  and expected full-dataset hash
  `sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718`.
  Do not substitute `kis_paper_daily_history_panel`, which is a different
  six-symbol source. `IWM` is outside this objective.
- Require completed `D1` bars, exact symbol/market identities, monotonically
  increasing session dates, and a nonempty common session set. Normalize only
  each source's completed D1 trading-date identity; do not invent a timezone
  conversion or join missing sessions.
- Before reading value-level results, freeze the comparison fields and
  tolerances: close-to-close return, open-to-close return, high/open ratio,
  low/open ratio, and volume ratio. A field agrees only when its absolute
  log-ratio difference is at most `0.0005` (5 bp) for price relationships or
  `0.05` (5 percent) for volume relationships. Zero/invalid denominators make
  that field nonconforming, never missing-pass.
- Define a `discontinuity-adjacent` stratum from either source when a completed
  D1 open-to-prior-close or close-to-prior-close raw move has absolute size at
  least `0.20`; include the triggering session plus one neighboring common
  session on each side. All remaining comparable sessions are `quiet`.
- A source/symbol relationship passes only if the aligned common-date agreement
  rate is at least `0.95` in both quiet and discontinuity-adjacent strata and
  is strictly greater than the corresponding one-session backward and
  forward-shift agreement rates. An empty stratum, an empty shift probe, or a
  tie fails closed as `input_unavailable` or `nonconforming`.
- The aggregate outcome is `conforming_with_limits` only when every required
  source/symbol/field result passes. Any mismatch, empty required stratum, or
  non-discriminating shift probe is `nonconforming` or `input_unavailable`.
  A pass remains non-promoting: it does not prove point-in-time availability,
  tradability, corporate-action correctness, or source interchangeability.

## Boundaries

- Do not call KIS, read `.env` or credentials, access accounts, submit/modify/
  cancel orders, use local-paper, or enable live behavior.
- Do not call the Norgate client, network, GPU, model weights, training code,
  or third-party market-data providers.
- Do not write raw bars, dates, prices, returns, volumes, per-row comparisons,
  paths, credentials, model artifacts, labels, predictions, costs, fills, or
  PnL to Git or artifacts. Write one aggregate-only immutable receipt below
  `D:\thericher-v2\model-artifacts`.
- Do not alter an existing historical source's adjustment metadata, cache,
  collection worker, scheduler, model contract, Paper route, or live boundary.
- Do not add a generic conformance framework. Keep one typed offline loader,
  one fixed comparison path, one runner, and focused tests.

## Required Work

1. Data: implement the pinned offline loader and fixed comparison, including
   aligned, backward-shift, forward-shift, quiet, and
   discontinuity-adjacent aggregate evidence.
2. Engine Research: consume only the categorical result to state the exact
   non-promotion consequence. It must not create a candidate, train a model,
   schedule GPU work, or modify a strategy.
3. Validation: prove source hash pinning, causal date joins, field tolerance,
   adjustment/discontinuity failure, shift-probe discrimination, aggregate-only
   receipt redaction, immutability/idempotence, and absence of KIS,
   credential, broker, account, local-paper, GPU, and live surfaces.
4. Run the real CPU-only comparison on the retained D: sources. Reattest source
   identity before reading rows, emit no value-level output, and update the
   stateboards, handoff, and decisions with source-safe aggregate facts only.

## Claude Context

Claude returned `supported-with-limits` for this exact next direction. It
identified the strongest risk as mistaking agreement between present-day
restated histories for point-in-time conformance. Codex accepts that limit:
the frozen event/discontinuity and shifted-date falsifiers can only reject or
narrow an offline relationship; they cannot promote a source, model, ensemble,
GPU campaign, Paper action, or live route.

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

Report the frozen field/tolerance contract, source-safe CPU outcome, external
receipt, tests, commit hash, intentional omissions, and the next recommended
objective. Replace this file with exactly one next objective only after
completion evidence is committed and pushed.
