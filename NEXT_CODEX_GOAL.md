# Next Codex Goal

## Objective

Build one bounded, source-attested historical intraday-data expansion for
`SPY`, `QQQ`, and `IWM`.

This advances data collection for later feature/model research. It must either
produce one useful, replayable external snapshot with a Data-owned loader or
close the unavailable-source path cleanly with an exact operator request. It is
not model training, a campaign, a ranking result, or a profitability claim.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Before accepting a new source or
data-lineage contract, ask Claude for a short bias/drift check; if the CLI is
unavailable, record that fact and use the Review checkpoint without treating it
as approval.

## Boundaries

- Start from existing `D:\market_data` evidence. Do not download market data
  into Git or overwrite an existing snapshot.
- Only `TIINGO_API_TOKEN` may be read if an already approved Tiingo endpoint
  genuinely needs it. Never print, log, commit, artifact, or send it to Claude.
- Do not call KIS, read other credentials, submit or simulate orders, use GPU,
  train a model, create a candidate/campaign, or claim performance.
- Use only no-cost, no-auth, license-compatible sources or the already approved
  Tiingo entitlement. Do not pay, log in, accept manual terms, bypass access
  controls, or add a placeholder provider.
- Warn before projected D-drive free space falls below 20%; stop acquisition
  before the 15% floor. Stop a source after two bounded automated failures or
  when its marginal coverage no longer helps this objective.

## Required Work

1. Make a bounded metadata inventory of current SPY/QQQ/IWM intraday coverage,
   exact gap, and D-drive capacity; avoid a broad recursive scan.
2. Assess at most two eligible acquisition paths, including the approved Tiingo
   entitlement where useful. Confirm endpoint scope, rights, retention, and
   expected coverage before retrieval; do not infer paid entitlement.
3. If one path meets the boundary, acquire exactly one deduplicated fixed-symbol
   snapshot under `D:\market_data`, with a concise manifest and Data-owned
   hash-attesting loader. Preserve source/coverage limitations and keep it out
   of campaign/paper/model APIs.
4. If no path is eligible or sufficient, stop cleanly. Record the concrete gap
   and, only when a paid source would materially solve it, prepare one concise
   operator request with product, price, coverage, rights, size, and steps.
5. Add focused tests for loader attestation, offline replay, source limitation,
   storage boundary, and no credential/network dependency after acquisition.
6. Update the Data and Engine Research stateboards, `HANDOFF.md`, and this next
   goal before ending the task.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add bounded intraday data evidence`
