# Next Codex Goal

## Objective

Build one bounded, local two-year Norgate broad daily development-panel source
from the already-retained S&P 500 current/past candidate union and membership
matrix. The result should be an externally stored, reproducible source contract
that can become the next honest path toward finite GPU breadth work, without
claiming point-in-time investability or strategy performance.

## Ownership

- **Data Agent:** owns the Windows-host-only read, panel contract, source
  availability facts, immutable external snapshot, and narrow readiness verdict.
- **Engine Research Agent:** states the minimum static-panel shape required for
  future development-only breadth work, but does not train, rank, ensemble, or
  reserve GPU in this goal.
- **Review/Claude:** gives one concise falsification-first review before this
  broader source contract is relied on.

## Boundaries

- Use only the already-installed local Norgate trial on Windows. Do not read
  `.env`, credentials, tokens, broker state, or secret-like files; do not call
  KIS, submit orders, use a network data API, query Norgate from Docker, change
  Norgate settings, renew, purchase, or delete either local Norgate copy.
- Use only the already retained 541-item candidate union and sparse membership
  matrix at
  `D:\market_data\us_equities\norgate_membership\canonical\sp500_current_past\snapshot=2026-07-18-norgate-sp500-membership-r1`.
  Fix the price window to 2024-07-18 through 2026-06-22. Do not enumerate a new
  universe, query historical membership again, widen dates, or substitute a
  symbol.
- Request query-local `NONE` adjustment and `NONE` padding only. Preserve raw
  OHLCV and returned-session facts; do not infer adjustment semantics, repair
  bars, fill gaps, transform prices, or use `Dividend`/`Capital Event` fields
  as action timestamps. Do not combine rows with Tiingo, Yahoo, or another
  source.
- A static development subset may include only symbols with an exact, strictly
  ordered 483-session response matching the fixed Norgate parent calendar. At
  least 100 such symbols are required before marking the panel
  `development_training_eligible`; otherwise retain only noneligible source
  evidence. This limited eligibility is never PIT, ranking, holdout, paper,
  source-preference, or profitability eligibility.
- Retain raw source bytes only under `D:\market_data`, with hashes and a
  Norgate deletion/rights marker. Store generated metadata only under
  `D:\thericher-v2\model-artifacts`; never write data or artifacts to Git.
  Check free space before work; warn below 20 percent and stop before 15 percent.
- No CPU/GPU model training, model loading, campaign, trade decision, paper
  activity, or profitability claim is allowed in this goal.

## Required Work

1. Ask Claude for a concise falsification-first review: state the static-panel
   claim, survivorship/membership-publication and adjustment risks, the
   strongest kill test, naive alternative of retaining only current narrow
   sources, blast radius, and the fact that closes the path. Do not send raw
   rows, candidate symbols, secrets, or account data.
2. Reuse existing Norgate and membership primitives. Add only the smallest
   mock-tested builder/verifier and CLI necessary to read the fixed candidate
   union, record returned/unavailable counts, retain one exact-session static
   raw-D1 subset, and verify its parent/membership/hash/rights lineage offline.
3. Run one bounded local build. Report aggregate candidate availability,
   selected static-panel count, common-session count, hashes, external paths,
   free-space result, and the narrow readiness verdict. If the local source
   requires manual action or cannot meet the contract, preserve safe recovery
   evidence, close this branch, and do not retry broadly.
4. Keep Engine Research explicit that GPU remains unavailable until the Data
   verdict establishes the limited development-training contract. Refresh
   `HANDOFF.md`, stateboards, `DECISIONS.md`, and this goal before continuing.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, source result, external paths/hashes, retained
rights/deletion evidence, genuine operator action if any, and GPU eligibility.

## Suggested Commit Message

`Add Norgate trial dividend exclusions`
