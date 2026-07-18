# Next Codex Goal

## Objective

Measure Tiingo standard-EOD coverage for one deterministic 12-symbol sample
drawn from the external Norgate `S&P 500 Current & Past` candidate union.

The probe decides only whether a later no-cost broad daily acquisition is worth
planning. It must not create a universe claim, a data snapshot, a campaign, or
a model/GPU job.

## Ownership

- **Data Agent:** owns deterministic sample selection, approved-token use,
  request budgeting, response coverage, and provenance limits.
- **Review/Claude:** is optional unless results would be used for a source,
  survivorship, temporal-availability, or model-promotion claim.
- **Engine Research Agent:** remains an observer and cannot consume the probe.

## Boundaries

- Read only `TIINGO_API_TOKEN` from `.env` using the existing approved narrow
  helper. Do not read, log, expose, or send any other `.env` value to Claude.
- Use exactly 12 deterministic symbols selected from the already external
  candidate union, with an algorithm/version/union hash recorded outside Git.
  Do not print or commit selected symbols, raw rows, prices, volumes, or token.
- Make at most 12 Tiingo standard-EOD requests over one fixed two-year daily
  window. Stop on `401`, `403`, `429`, malformed responses, or storage-policy
  violation; do not retry, change windows, or silently replace missing symbols.
- Record only aggregate availability, per-response row-count/date-range
  summaries, HTTP/error class, request count, package/source version, and
  external evidence path under `D:\thericher-v2\model-artifacts\data-agent`.
  Do not write Tiingo raw data to Git or create a data snapshot in this goal.
- Do not call Norgate, Docker, KIS, broker code, or a public service. Do not
  create a provider, catalog, campaign, strategy, model, GPU job, paper order,
  report family, dashboard, or source-selection rule.

## Required Work

1. Inspect the existing narrow Tiingo helper and external Norgate union
   manifest; define deterministic sample selection and a fixed date window
   before reading the token or making a request.
2. Add the smallest mock-tested probe helper/script. Tests must prove only the
   approved token is read, request count is capped, no raw data is persisted,
   selected symbols are absent from Git outputs, and an error stops cleanly.
3. Run once only after tests and fresh D: preflight pass. Report only aggregate
   coverage and external summary hash/path; preserve raw API responses nowhere.
4. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`, replace this
   goal, then continue while no real operator approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report aggregate availability, request count, token boundary result, external
summary path/hash, and any genuine operator data action required.

## Suggested Commit Message

`Probe Tiingo broad daily coverage`
