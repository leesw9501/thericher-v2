# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-qqq-spy-mtf-prospective-observation-v1`.

Create the smallest forward-only attempt path for new QQQ/SPY regular sessions
at the fixed 15:30 ET causal `1m/5m/10m/1h/3h` geometry. This turns the
completed local-cache availability proof into durable prospective engine
evidence while explicitly excluding its 21 historical sessions. It is not a
historical backtest, model campaign, or Paper-trading decision.

## Hard Boundaries

- KIS Paper market-data reads are allowed only through the existing owned
  collector/client path when a fresh source session is needed. Never log or
  expose credentials, tokens, headers, raw provider bodies, cache paths, or
  raw bars.
- Do not call KIS account, position, open-order, quote, submit, modify, cancel,
  reconciliation, or live endpoints. Do not read or route `KIS_LIVE_*`.
- Do not submit or simulate a Paper/broker order, including `local_paper`.
- Do not call Tiingo, Norgate, or another provider.
- Do not read `.env` except the existing owned KIS Paper collector process may
  receive its required Paper credentials through its existing private runtime
  boundary. The observation/validation processes themselves must remain
  credential-free.
- Do not train, tune, load weights, use CUDA, allocate the GPU, open a target
  or return, calculate PnL, choose a model, ensemble, or strategy action.
- Keep raw market data under `D:\market_data` and artifacts only under
  `D:\thericher-v2\model-artifacts`; never write either in Git.

## Frozen Contract

- Consume the availability receipt
  `D:\thericher-v2\model-artifacts\data\kis-intraday-mtf-availability-receipt-v1\local-cache-20260802-r2\summary.json`
  only as a geometry/exclusion contract. Its 21 aligned historical sessions are
  not observations and must never be reconstructed as new prospective records.
- One prospective attempt represents exactly one same-day weekday regular
  session and emits a sealed categorical record whether zero, one, or both
  legs are available. A successful pair needs both QQQ/NAS and SPY/AMS
  completed one-minute prefixes from 09:30 inclusive through 15:30 exclusive
  America/New_York. Both symbols must independently reconstruct completed
  `1m x 30`, `5m x 6`, `10m x 3`, `1h x 2`, and `3h x 2` tails ending at the
  fixed cutoff, with every tail contained in the prefix and anchored to the
  session open.
- The record carries only a versioned source/content commitment, receipt
  identities, session/cutoff/seal structural facts, and categorical availability.
  Its seal must be at or after the final source-bar close and strictly later
  than the previous record's seal. It retains no raw prices, OHLCV, source
  paths, account/broker facts, targets, predictions, returns, PnL, or model
  decision.
- A duplicate, prior-session, weekend/early-close, missing, conflicting,
  incomplete, future, stale, or source-identity-changing input closes only that
  attempt as `not_observed` or conflict. It cannot trigger an order, a new
  approval, a global hold, or a replacement collector.
- Persist attempts in one append-only sealed store and stop this exact
  accumulation contract after 30 immutable fresh session attempts, including
  availability failures. A later divergence from a sealed content commitment is
  a conflict record, never a rewritten attempt. A later Engine campaign must
  freeze its own target, split, costs, baseline, and kill test; it may not
  select from these records first.

## Required Work

1. Ask Claude for a concise falsification-first drift check before changing the
   observation/scheduler boundary. Record a timeout or malformed response as
   `review_unavailable`, never as agreement or a hold.
2. Add the smallest pure pair-observation receipt and offline validator. Reuse
   the established KIS local loader, causal session builder, content-commitment
   idiom, and external-artifact custody; do not create a generic agent, dataset,
   or scheduling framework.
3. Extend only the existing Data-owned intraday collector/schedule integration
   needed to invoke the credential-free pair materializer after an eligible
   fresh cache prefix. It must no-op outside its own eligible window and never
   make the foreground wait. Do not add a second scheduler platform.
4. Add focused tests for historical-exclusion binding, QQQ/SPY date alignment,
   all attempt categories including one-leg failure, exact five-timeframe tail
   containment, DST-safe cutoff, monotonic post-close seals, duplicate and
   later-divergence behavior, no-network/no-environment/no-account/no-order
   isolation, redacted external artifacts, and the terminal 30-attempt cap.
5. Run an offline injected-bar smoke first. If the next eligible fresh session
   exists, run one owned KIS Paper market-data observation attempt; otherwise
   install/verify its no-op owned path and continue the next independent goal
   without foreground waiting.
6. Update the Data, Engine Research, Execution, orchestration, handoff, and
   decision stateboards with the exact result. The observation contract cannot
   become a model/PnL/Paper/live claim.

## Verification

Run focused tests and the offline smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper remains blocked by known interrupted roots, preserve
that fact and run its fresh-root mode plus the remaining verification commands.

## Completion

Report the receipt/contract hashes and artifact location, whether a fresh KIS
market-data attempt ran, current forward-record count, tests, any Claude
verdict, and why no model/GPU/PnL/Paper/live claim was created. Commit and push
completion evidence before replacing this file with exactly one next objective
and continuing.
