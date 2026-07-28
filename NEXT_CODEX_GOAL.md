# Next Codex Goal

## Objective

Build one bounded, candidate-only NAS D1 volatility-conditioned trend breadth
campaign. It must be a new causal hypothesis, not a parameter retune or a
selection derived from the completed sealed NAS r4 results. The campaign should
test whether completed-bar trend evidence conditioned by recent realized range
can improve a fixed long-versus-flat, after-cost local-paper decision relative
to fixed naive comparators.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattest the current source-local NAS panel
   `sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`
   before building any feature rows.
3. Ask Claude for a concise falsification-first drift check before freezing the
   candidate contract. If local OAuth remains expired, record
   `review_unavailable` and continue this private, non-promoting package.

## Contract

- Use only `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA` from the existing
  source-local NAS D1 panel. Do not construct a point-in-time universe or rank
  the current listing.
- Freeze a new chronological development/purge/validation split, fully causal
  completed-bar feature timestamps, target timing, costs, model specifications,
  naive comparators, compute budget, and strongest kill test before fitting.
- The distinct hypothesis must use a predeclared volatility/range-conditioned
  trend representation derived only from completed D1 OHLC bars. Preserve the
  existing unadjusted/corporate-action limitations instead of repairing them.
- Keep development labels and validation targets isolated. Never tune a
  threshold, feature, seed, or architecture from validation outcomes.
- Use deterministic CPU baselines first. If their contract and focused tests
  pass, run one bounded network-disabled Docker CUDA breadth package with the
  exclusive GPU. Generated checkpoints and receipts belong only under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.

## Work

1. **Data:** add a narrow reattested feature-input adapter for the causal
   volatility-conditioned D1 windows. It must reject source, symbol, phase,
   incomplete-bar, and feature-timestamp drift.
2. **Engine Research:** precommit the one hypothesis and its fixed falsification
   rule, then run CPU baseline(s) and the eligible bounded CUDA breadth package.
   Keep candidate families independent; do not create an ensemble.
3. **Validation:** verify chronological isolation, target-free validation
   forwards, safe checkpoint loading, Docker artifact placement, and replayable
   `local_paper` attribution if the campaign opens a fixed evaluation path.
4. **Execution:** remain independent. Do not create an intent, call KIS, or use
   the campaign as a Paper input.

## Boundaries

- No KIS call, `.env` or credential read, provider download, paid asset, public
  service, account/quote/order route, broker submission, or live behavior.
- Do not inspect, rank, select, ensemble, promote, or tune from the sealed NAS
  r4 aggregate outcome.
- Do not write raw bars, feature rows, labels, prediction vectors, event rows,
  secrets, or model artifacts into Git.
- A failed candidate closes only its own hypothesis. It cannot block Data,
  Execution, scheduled collection, or another ready research package.

## Completion

- An immutable source-safe precommit names the new causal feature contract,
  split, cost model, comparators, model specifications, compute limit, and kill
  test.
- CPU baseline evidence is complete, or a bounded failure receipt identifies the
  exact input/implementation fault without opening a broader hold.
- If eligible, the CUDA breadth receipt is complete with external checkpoints
  and target-free validation forwards.
- Refresh stateboards and replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add NAS volatility trend breadth campaign`
