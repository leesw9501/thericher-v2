# Next Codex Goal

## Objective

Produce one operator decision-ready KIS virtual-paper capital-envelope proposal
from the completed read-only reconciliation. This improves the paper-trading
loop by making the first allowed capital boundary explicit before any external
order capability exists.

## Authority And Boundaries

- `KIS_PAPER_*` read-only development access is authorized. Keep
  `THERICHER_MODE=off`; do not read `KIS_LIVE_*` or call a live endpoint.
- Do not submit, modify, or cancel an external order. Do not implement an order
  canary, broker adapter, daemon, scheduler, or public service.
- The operator alone approves or changes a nonzero paper-capital envelope.
- Use only the generic sanitized reconciliation snapshot in the credential-free
  web process. Do not persist account values, account identifiers, credentials,
  raw broker data, or response-derived error text in Git or external evidence.
- Reference orderability is for one explicit reference request, not general
  buying power. Do not silently equate it to cash, margin capacity, or a
  currency-converted planning reference.
- If the prior snapshot is stale, one deliberately scoped fresh read is allowed
  under the existing paper read-only authority. It must be a named bounded
  refresh, not an automatic retry loop.

## Required Work

1. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
   `RUNBOOK.md`, and `agents/execution.md`; inspect the snapshot bridge, risk
   contract, and local console before editing.
2. Ask Claude for a short falsification-first review before selecting the
   proposal policy. Do not send credentials, account identifiers, raw values,
   or raw broker responses.
3. Define a small deterministic, non-submitting proposal contract that makes
   its currency, available-cash basis, reference-orderability limitation,
   ceiling, expiry, and operator-approval status explicit. Keep it transient or
   local-only unless a safe aggregate artifact is necessary.
4. Expose the proposal only through the loopback local console or a bounded
   operator-facing command; no public endpoint and no write to KIS.
5. Add focused tests for stale/missing snapshot abstention, no broker/network or
   credential requirement, no reference-orderability overclaim, and no order
   path. Use one fresh bounded read only if needed to form the operator-facing
   proposal.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Also report the focused proposal tests and any deliberate KIS read separately,
without raw account data or secrets.

## Completion

Present the proposed capital envelope and its limits to the operator for an
approve/change decision. Do not start an order canary until that decision is
explicit. Refresh the stateboards and this file, commit, push, and continue
only through work that does not need the approval.
