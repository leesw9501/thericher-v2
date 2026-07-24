# Next Codex Goal

## Objective

Build and run the first bounded `QQQ/SPY` D1 naive price-return validation from
the qualified offline event-boundary audit. This is a CPU-only retrospective
plumbing check, not a model experiment or a trading claim.

Before a consumer materializes any bar, re-attest these immutable inputs:

- KIS panel: 4,756 common sessions, 2007-08-21 through 2026-07-17, dataset
  `sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718`.
- Tiingo event-only sidecar:
  `D:\market_data\us_equities\kis_paper_private\daily-corporate-actions\snapshot=2026-07-24-qqq-spy-tiingo-events-v1`,
  dataset
  `sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3`,
  manifest
  `sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46c171d`.
- Qualified audit:
  `D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json`,
  content hash
  `sha256:3d97b26b5e8e422cb2b4bcf262fbd1be887e44d7e43afdd9e2b5d689f805a46c`,
  mask identity
  `sha256:921c61b8abf822b0aee71b66b43c37875cb581e95bf7a1563b053880c087d429`,
  partition identity
  `sha256:b82ed4022237929febde187651cb31e74740b311faa85c850967c617ac8dcfdb`.

Claude's verdict is `supported-with-limits`: this source remains unadjusted,
retrospective, event-calendar-conditioned, and not a total-return or
point-in-time input. Preserve those limitations in every output.

## Hard Boundaries

- Do not read `.env`, credentials, or secret-like files.
- Do not call Tiingo, KIS, account, position, order, or live endpoints.
- Do not submit, modify, or cancel broker orders.
- Do not use a GPU, train or score a learned model, tune, select, ensemble, or
  alter the frozen three-ETF work.
- Reject scoped use on any audit/source/mask/partition/tail mismatch. Do not
  recompute or weaken the qualified mask.
- Do not materialize bars, calculate returns, or emit metrics for the
  950-session untouched tail. Do not use purge or embargo sessions as a
  decision/return pair.
- Use only fixed `flat`, `always_long`, and previous-session-direction controls
  with a declared non-lookahead D1 horizon and the existing local simulator.
  Every simulated fill remains `source: local_paper`.
- Write only aggregate, sanitized validation evidence under
  `D:\thericher-v2\model-artifacts`; never Git. Do not persist raw prices,
  per-bar returns, Tiingo responses, quote values, or broker data.
- Treat results as retrospective price-return plumbing only, never total return,
  point-in-time availability, alpha, profitability, or live/Paper evidence.

## Role-Owned Work

### Data Agent

1. Add or extend a narrow offline audit loader that checks content hash,
   schema/kind, status, source lineage, mask, partition, and tail geometry.
2. Materialize only the permitted development/validation source prefix through
   the verified KIS catalog path. Source-byte re-attestation is allowed, but do
   not construct tail `Bar` objects or expose raw rows to artifacts.
3. Preserve exact audited exclusion pairs and boundaries for every comparator.
   Do not join another provider or repair source history.

### Engine Research Agent

1. Pre-register exactly `flat`, `always_long`, and previous-session-direction.
   Use identical audited eligibility, fixed chronological boundaries, and
   existing cost/local-paper semantics. Do not tune a threshold, horizon, or
   symbol treatment.
2. Run on CPU and write one aggregate sanitized artifact containing input
   identities, pair/fill counts, fixed controls, aggregate metrics, limitations,
   and `source: local_paper` provenance. It contains no raw prices, per-bar
   returns, scores, or predictions.
3. Do not promote, compare against a model, use the tail, select an
   architecture, or open a GPU campaign. Ask Claude only for an unexpectedly
   strong result or a proposed interpretation beyond this scope.

### Execution Agent

Keep KIS Paper routes, schedules, and reconciliation unchanged. The local
simulator is the only execution surface; the baseline is not a KIS price,
sizing, intent, fill, or PnL input.

## Completion Evidence

- A hash-attested loader rejects any audit/source/mask/partition/tail mismatch
  before a consumer receives eligible bars.
- One CPU-only aggregate validation artifact proves identical audited eligibility
  across all fixed controls and replayable `source: local_paper` fills.
- Tests prove offline operation, no credential/network/broker access, no raw
  price or per-bar-return persistence, source/audit drift rejection, tail
  non-consumption, deterministic pair geometry, and no model/Paper path.
- Output carries Claude's `supported-with-limits` boundaries and does not widen
  the daily source into a model or trading result.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Run masked daily naive validation`
