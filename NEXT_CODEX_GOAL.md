# Next Codex Goal

## Objective

Build and run one bounded CPU-only source-local falsification:
`kis-spy-intraday-regime-micro-consensus-v1`. It connects one verified local
`SPY/AMS` 1m cache to deterministic `1m`, `5m`, `10m`, `1h`, and `3h` decision
inputs. It is not model selection, a profitability claim, a Paper order, or a
live route.

## Start

1. Run `scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and the Data,
   Engine Research, Research Steward, Execution, and orchestration stateboards.
3. A concise Claude falsification check was attempted twice before this
   contract: the first reached its turn limit and the second produced no
   verdict before its bounded timeout. Record this only as
   `review_unavailable`; it is neither agreement nor a hold on this private,
   offline package.

## Fixed Source And Boundaries

- Read only the existing verified local `SPY/AMS` catalog through
  `D:\market_data\us_equities\kis_paper_private\intraday` and its existing
  offline loader. The loader's exact source is
  `kis.paper.private.intraday.spy.ams.m1.v1`, dataset hash
  `sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6`,
  and 21 complete regular sessions from 2026-06-22 through 2026-07-21.
- Split the fixed complete sessions chronologically into 10 development
  sessions, one entire purge session, and 10 validation sessions. Development
  target returns remain unread.
- The target-free structural preflight found 32 active validation decisions for
  the frozen rule below. The implementation must recalculate the 30-decision
  preflight before accessing a validation target field; fewer than 30 closes as
  `input_unavailable` with no performance result.
- Do not call KIS, read `.env` or credentials, mutate the cache, access an
  account, construct an intent/order/fill, invoke local paper, use a network,
  allocate GPU, train a model, select an ensemble, or enable live behavior.
- Write only source-safe aggregate evidence under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`. Keep raw bars,
  individual returns, scores, and timestamps out of Git and artifacts.

## Frozen Campaign Contract

- Decision times are every 10 minutes from 12:30 through 15:30 ET, inclusive.
  At each time `t`, use only complete bars ending no later than `t` inside the
  same regular session.
- The macro regime gate requires the latest completed `3h` and `1h` bars to
  each close above their own open.
- The micro score is the count of: latest completed `10m` close above open,
  latest completed `5m` close above open, and latest completed `1m` close above
  the close 30 minutes earlier. The `1m` condition requires 31 completed bars.
  A long candidate requires macro readiness and a micro score of at least one.
- An active decision enters at the opening price of the first `1m` bar beginning
  at `t` and exits at the opening price of the `1m` bar beginning at `t + 10m`.
  Targets stay inside the session and do not overlap.
- Apply all-in round-trip `5`, `10`, and `20` bp costs to every active decision.
  Use `10` bp as the primary view and `20` bp for the flat-or-worse kill test.
  Comparators are always-flat, macro-regime-only SPY at every macro-ready
  timestamp, and schedule-wide always-long SPY. Each has the same target and
  costs. Compare candidate and macro-regime-only evidence by net bps per active
  decision so their different activity counts do not masquerade as signal value.
- Falsify the family if validation net total is flat-or-worse at `20` bp, or
  its net bps per active decision is no better than macro-regime-only across all
  cost scenarios. Schedule-wide always-long is descriptive only. Do not tune a
  window, schedule, condition, split, cost, or comparator after any target
  result is visible.

## Work

1. **Engine Research:** implement the deterministic offline campaign and CLI
   runner with a source-safe external precommit and aggregate summary.
2. **Validation:** add focused causal timing, session/purge, target-preflight,
   multi-timeframe, costs, comparator, falsification, artifact, and redaction
   tests.
3. **Execution:** add an isolation test proving no credential, KIS, account,
   intent, order, fill, local-paper, broker, network, or live surface exists.
4. **Research Steward:** record that this is CPU-only and receives no GPU or
   sealed-evaluation allocation.

## Completion

- One external immutable precommit and either a source-safe aggregate result or
  a truthful `input_unavailable` result exist.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. The independent prospective SPY capture runner remains owned by
  Data and must not make this Engine objective wait for market time.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```
