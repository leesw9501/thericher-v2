# Next Codex Goal

## Objective

Complete `firstrate-source-semantics-retrieval-v1`: make one bounded,
source-safe retrieval of official FirstRate documentation needed to interpret
the already hash-bound free SPY/QQQ M1 archives. The target facts are timestamp
timezone/meaning, zero-volume or omitted-bar policy, sample coverage, and
private-use licensing. A claim not stated by a primary official source remains
`not_disclosed`; this objective never upgrades the data to a predictive, KIS,
Paper, or live input.

## Hard Boundaries

- Do not call KIS, read credentials, invoke a broker, submit or alter an order,
  invoke Task Scheduler, start Docker services, acquire new market data, train
  a model, or allocate GPU.
- Retrieve only public, no-auth, official FirstRate pages or files. Do not use
  search-result snippets, unofficial mirrors, archived copies, or a claim from
  memory as evidence. Never print raw market rows or write market data or
  generated artifacts into Git.
- Record only page URL, retrieval time, content hash, verbatim license text,
  the exact official statement or `not_disclosed`, and the narrow resulting
  interpretation. Do not extrapolate a timestamp statement into session
  completeness, KIS parity, decision-time availability, provider finality, or
  a trading property.
- Do not change a canonical CSV, normalization/mechanics/preflight receipt, a
  model, a Paper path, or an existing scheduler. A missing, inaccessible, or
  contradictory source ends this objective as `source_unverified` rather than
  triggering retries, a new provider, or an approval wait.

## Required Work

1. Retrieve and re-retrieve each candidate official FirstRate source. Write one
   immutable external source receipt with exact URLs, hashes, statements, and
   `confirmed`, `not_disclosed`, `contradictory`, or `source_unverified`
   classifications only.
2. Ask Claude for a concise falsification-first review before relying on any
   source statement that would narrow FirstRate timestamp or omission limits.
   Claude may challenge the interpretation but cannot create a promotion.
3. Refresh Data, Engine Research, and orchestration stateboards, `HANDOFF.md`,
   and `RUNBOOK.md`. Preserve the completed target-free window preflight,
   Research Steward GPU custody, and Execution as non-promoting.

## Verification

Run focused source-retrieval/receipt tests, the goal-boundary authority test
group, Ruff, credential-free Compose configurations, and `git diff --check`.
Report only source-safe facts and the external evidence pointer.
