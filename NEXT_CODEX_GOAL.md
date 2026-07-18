# Next Codex Goal

## Objective

Build and run one deterministic 30-symbol Tiingo standard-EOD raw-daily
acquisition pilot from the external Norgate `S&P 500 Current & Past` candidate
union.

The pilot proves only whether a small, rate-bounded private-use raw-data
snapshot can be acquired and recovered correctly. It must not claim a
historical universe, point-in-time membership, source completeness, model
quality, or profitability.

## Ownership

- **Data Agent:** owns candidate selection, approved-token isolation, request
  pacing, raw-response provenance, canonical local validation, and storage.
- **Review/Claude:** must make one short falsification-first data-contract
  check before architecture-changing edits or the live acquisition run.
- **Engine Research Agent:** remains an observer. It cannot consume, model,
  rank, train, or schedule GPU work from this pilot.

## Boundaries

- Read only `TIINGO_API_TOKEN` through the existing approved narrow helper.
  Never read, log, expose, or send any other `.env` value to Claude.
- Use exactly 30 deterministic candidates selected from the external union.
  Preserve the selection algorithm, union hash, original candidate and request
  identifier only in external source evidence. Do not print or commit symbols,
  raw rows, prices, volumes, response bodies, or token.
- Do not substitute a missing, empty, malformed, or rejected candidate with a
  proxy, sibling ticker, guessed delisting, or a different candidate. Record it
  as a gap and stop on auth, rate, malformed, storage, or contract failure.
- Limit the live pass to 30 requests, no retries, and the observed 50-request
  hourly account limit. Use one fixed 2024-07-18 through 2026-07-17 daily
  window. Do not query another date range or start a second pass.
- Persist exact raw responses, a hash-attested canonical raw-field subset, and
  a manifest only under `D:\market_data`; use an external staging directory and
  atomic publication. Keep all output private and non-redistributable under
  Tiingo's current terms.
- The pilot must remain `pit=false`, `ranking=false`, `holdout=false`,
  `campaign=false`, `model=false`, `gpu=false`, and `paper=false`. Do not add a
  provider/catalog, feature, strategy, model, GPU job, Docker work, broker
  call, KIS use, dashboard, report family, scheduler, or public service.
- Check D: immediately before the live pass. Warn below 20 percent free and
  stop below 15 percent. Do not create data or model artifacts in Git.

## Required Work

1. Read the existing Tiingo narrow helper, coverage probe, and external union
   manifest. Ask Claude for a concise drift-check that challenges symbol
   semantics, raw/canonical policy, request pacing, recovery, and the non-PIT
   boundary. Do not send raw rows, candidate symbols, or secrets.
2. Implement the smallest mock-tested raw-daily pilot helper and CLI. Tests
   must prove: approved-token-only access; exactly 30 capped/no-retry requests;
   external-only atomic output; tamper detection; no symbol substitution;
   safe failure/recovery; no broker, Docker, or credential access beyond the
   approved token.
3. Run focused tests and a fresh D: preflight, then run the one live pass once.
   Report aggregate counts and external hashes/paths only. If it stops, retain
   the partial external evidence and do not rerun it.
4. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`, replace this
   goal, then continue while no real operator approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, aggregate result, storage result, external
snapshot/manifest hashes, and any genuine operator data action required.

## Suggested Commit Message

`Add Tiingo daily acquisition pilot`
