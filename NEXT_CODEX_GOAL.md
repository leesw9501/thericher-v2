# Next Codex Goal

## Objective

Use one newly authorized, deliberately bounded KIS virtual-paper read-only
snapshot to establish the native currency and whether the account is empty,
then obtain one operator decision for the first paper-capital ceiling. Turn the
fresh snapshot plus that decision into a transient, non-submitting candidate
envelope. This advances paper-trading readiness without starting an order
canary.

## First Bounded Read

- Run the isolated `kis-readonly` bridge once. It may use the approved
  `KIS_PAPER_*` read-only account, position, reference-orderability, and
  open-order calls; it must not retry automatically.
- Record only the sanitized status, native currency, position/open-order
  presence, and expiry outcome. Do not expose or persist account values,
  identifiers, credentials, or raw broker payloads.
- If the read is unavailable, report that result and keep the capital proposal
  abstained. Do not infer an empty account or retry it in this objective.

## Required Operator Decision After A Usable Read

- If the fresh snapshot's native currency is USD, approve or change Codex's
  recommended initial ceiling of `USD 500`.
- If it is another currency, provide a maximum directly in that currency.
- This is only a ceiling decision. It does not approve an external order,
  cancellation, `KIS_LIVE_*`, a mode change, or an order canary.

## Boundaries

- Keep `THERICHER_MODE=off`. Use only the approved isolated `KIS_PAPER_*`
  read-only bridge; do not read `KIS_LIVE_*` or call a live endpoint.
- No submit, modify, cancel, broker adapter, scheduler, daemon, public service,
  or approval persistence.
- Use snapshot schema v2 only. Its `orderable_foreign_funds` value is the exact
  source `ord_psbl_frcr_amt`, not settled cash, account equity, margin capacity,
  or general buying power.
- The separate reference-orderability value is a compatibility check only and
  must never size the candidate or be converted to another currency.
- The proposal must abstain unless the snapshot is fresh (`now < expires_at`),
  native-currency matched, positive, and empty of positions and open orders.
- Do not retain account values, identifiers, credentials, raw broker bodies, or
  derived candidate amounts in Git or external evidence.

## Work After The Decision

1. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and
   `agents/execution.md`.
2. Ask Claude for a short falsification-first check of the exact ceiling and
   freshness boundary without sharing raw account data.
3. Run the no-network `paper-capital-proposal` profile with the approved
   same-currency ceiling and present its transient candidate or abstention.
4. Ask the operator to approve or change that exact candidate. Do not start a
   canary until the approval is explicit.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report focused proposal tests and any one bounded KIS read without raw account
data or secrets.
