# Next Codex Goal

## Objective

Audit the newly qualified `QQQ/SPY` KIS daily corporate-action mapping against
the retained unadjusted KIS series, then freeze or reject a **conservative
event-boundary return-label contract**.

The immutable source inputs already exist and must be re-attested offline:

- KIS QQQ/SPY common daily panel: 4,756 sessions from 2007-08-21 through
  2026-07-17, dataset
  `sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718`.
- Tiingo event-only sidecar:
  `D:\market_data\us_equities\kis_paper_private\daily-corporate-actions\snapshot=2026-07-24-qqq-spy-tiingo-events-v1`,
  dataset
  `sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3`,
  manifest
  `sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d`.

This goal is a data/research integrity step only. It must not create a model,
baseline result, GPU run, ensemble, Paper order, or new provider acquisition.

## Hard Boundaries

- Do not read `.env`, credentials, or secret-like files.
- Do not call Tiingo, KIS, account, position, order, or live endpoints.
- Do not submit, modify, or cancel broker orders.
- Do not download or persist raw Tiingo responses, quote values, or KIS prices
  outside the existing raw KIS cache.
- Do not use a GPU, train, score, select, tune, ensemble, replay a strategy,
  or alter the frozen three-ETF work.
- Write any new audit/contract artifact only under
  `D:\thericher-v2\model-artifacts`; never Git.
- Treat the result as retrospective price-return plumbing only, never total
  return, point-in-time availability, alpha, or live/Paper evidence.

## Role-Owned Work

### Data Agent

1. Re-attest the pinned QQQ/SPY KIS catalog and event-only sidecar entirely
   offline. Fail closed on either hash, session, mapping, or lineage drift.
2. For every mapped event, inspect the retained KIS close-to-close geometry in
   memory only. Record categorical counts, fixed thresholds, and mapping
   results; never emit a price, return, raw row, or source response.
3. Build a deterministic candidate mask that excludes every daily `t -> t+1`
   pair whose endpoint is the event session or either adjacent KIS session.
   It must prove all event dates map to common sessions and preserve exact
   cross-split boundaries.
4. If any event lacks its required neighboring session or any fixed residual
   check fails, record a precise `unqualified` result. Do not guess, shift,
   repair, or refetch data.

### Engine Research Agent

1. Define a frozen, offline-only contract receipt that binds both source
   hashes, the buffered pair set, pre-registered residual threshold, and a
   chronological availability statement.
2. Assert that every future comparator would receive the same mask identity
   and split boundaries. The receipt must state `price_return`, not total
   return; `retrospective`, not point-in-time; and no model/Paper eligibility.
3. Do not calculate a baseline or materialize returns in an artifact during
   this objective.

### Execution Agent

Keep KIS Paper routes, schedules, and reconciliation unchanged. The audit is
not a price, sizing, intent, fill, or PnL input.

## Completion Evidence

- A hash-attested external audit/contract either proves the strict buffered
  event-boundary rules for this exact input or records its scoped rejection.
- Tests prove offline operation, no credential/network/broker access, no raw
  price persistence, source-hash drift rejection, deterministic `+-1` mask
  geometry, and no model/Paper path.
- The next objective is chosen only after reviewing this result and Claude's
  `supported-with-limits` challenge: no naive baseline may silently weaken the
  buffered contract.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Audit daily event-boundary contract`
