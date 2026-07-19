# Next Codex Goal

## Objective

Qualify or reject one **in-memory** KIS paper raw-`1m` runtime input during a
bounded US market-session probe. The outcome is either a precisely qualified
90-bar input contract or an explicit observed limitation; both are valid.

This is not KIS order submission, account mutation, capital deployment, raw
market-data persistence, GPU training, or a profitability claim.

## Completed Foundation

- `data.kis_capability` contains the dated `declared` / `observed` /
  `qualified` / `unavailable` record and an in-memory completed-bar cache.
- `execution.kis_market_data` permits only KIS paper token issuance and the
  raw overseas `1m` endpoint. It has fake-transport coverage for a KIS-shaped
  page and explicit continuation; it never creates a `Bar` from unqualified
  timestamps.
- `research.kis_paper_baseline` consumes exactly 90 completed `1m` bars and
  deterministic local 18-`5m` / 9-`10m` resamples, then emits a target-exposure
  proposal or abstains. Execution alone can map a ready proposal to local paper;
  tests prove replayable `source: local_paper` fills with no network or
  credential access.
- The earlier sanitized probe observed successful raw `QQQ` `1m` first and
  continuation pages at
  `D:\thericher-v2\model-artifacts\execution\kis-paper-market-data-probe\20260719T054216611479Z\summary.json`.
  The first client version incorrectly required market `rt_cd` on the OAuth
  response. Its corrected HTTP/token-only handling passed fake coverage and one
  bounded real `QQQ`/`NAS` read: 120 raw rows in descending exchange-time order
  from `19:59` to `18:00`, with `next` present and `more=0`. It retained no raw
  market data. Its sanitized result is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-raw-minute-client-probe\20260719T060205390Z\summary.json`
  (`sha256:81e80a4c7a55e90cfde73e1349e83aa504f5f86589c3c5ac8e0122e4128c6f72`).
  Do not infer time conversion or completed-bar semantics from that one page or
  retry in a loop.

## Required First Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
   `RUNBOOK.md`, `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
3. Ask Claude for a short falsification-first drift check before changing the
   raw-`1m` capability from `observed` to `qualified`.

## Work Packages

### Data

1. Define the predeclared qualification facts for this one raw-`1m` capability:
   exchange/Korea-to-UTC interpretation, strict one-minute ordering, one known
   overlap/deduplication rule, completed-bar exclusion, freshness budget, and
   in-memory-only rights status.
2. Do not store KIS market bytes. Persistent cache/data writes under
   `D:\market_data` remain prohibited until storage rights are confirmed.
3. Promote only this exact capability to `qualified` if every predeclared fact
   has fresh sanitized evidence. Otherwise retain `observed` with the smallest
   unresolved fact; do not create a proxy source or a report family.

### Execution

1. During the next regular US session, make at most one fresh `KIS_PAPER_*`
   token attempt for this objective. If it fails, record only sanitized status
   and stop KIS network work for this objective.
2. If token issuance succeeds, issue one `QQQ`/`NAS` raw-`1m` first page and at
   most one documented continuation. Capture only response shape, row count,
   timestamp bounds, overlap, continuation facts, and local clock; never raw
   prices, token, account identifier, or account endpoint data.
3. Keep imports, tests, local paper, and web processes credential- and
   network-free. Do not call KIS order, cancel, modify, live, or account-mutate
   endpoints, and do not change `THERICHER_MODE`.

### Engine Research

1. Keep the fixed 90-`1m` / 18-`5m` / 9-`10m` baseline unchanged. Use it only with
   in-memory completed bars after Data qualifies the capability; otherwise it
   must abstain.
2. Do not introduce GPU work, learned models, ensembles, `1h`, `3h`, adjusted
   prices, corporate actions, news, order book, external universe inputs, or
   KIS paper submission.

## Boundaries

- Do not read `KIS_LIVE_*`, output/log/commit credentials or account data, buy
  data, enable live behavior, create a daemon/scheduler/report family, or write
  KIS raw bytes to Git or `D:`.
- No capital envelope or paper order approval is implied. Local-paper-only
  replay remains permitted and fills must retain `source: local_paper`.
- Do not claim a market-session fact from old weekend evidence, a page cap, an
  error response, or documentation alone.

## Completion

Refresh stateboards, `HANDOFF.md`, `DECISIONS.md`, and this goal. Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Commit, push, and report the capability verdict, exact sanitized KIS calls,
local-paper status, remaining account/data gaps, and next objective.
