# Next Codex Goal

## Objective

Resolve or explicitly reject the virtual-paper KIS US limit-order route/header
contract using official public source material, before any KIS order transport
or adapter work is considered.

The existing pure body mappers are intentionally non-transmittable. Official
source evidence currently conflicts on the virtual US sell TR-ID, so no route,
header, account, or endpoint value may be guessed from a generic prefix rule.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and
   `agents/execution.md`.
3. Read `src/thericher_v2/execution/kis_paper_order_fields.py`,
   `src/thericher_v2/execution/broker.py`, and their focused tests.
4. Ask Claude CLI for a short falsification-first drift check before recording
   a source conclusion or adding any execution-facing contract.

## Work Packages

### Execution Agent

- Inspect only official KIS public documentation and the pinned official source
  revision already cited in the repository. Build a compact evidence comparison
  for virtual-paper US buy and sell limit routes, TR IDs, required headers, and
  the source location for each fact.
- Resolve the route/header contract only when the official evidence is direct,
  mutually consistent, and distinguishes virtual paper from live. Otherwise
  record the conclusion as `unsupported` with the exact conflict.
- If and only if the evidence is unambiguous, add the smallest pure,
  non-transmittable route/header contract needed for a later adapter. Reuse
  existing request types; do not add a transport, account loader, credential
  path, request sender, or enablement flag.

### Validation

- Independently check the source conclusion and any proposed pure contract for
  paper/live separation, unsupported inference, and no accidental external
  order path.

## Hard Boundaries

- No `.env`, credential, account-state, KIS API, order, cancellation, market
  data, balance, position, or live call.
- No paper capital envelope, `THERICHER_MODE` change, Docker profile, public
  service, generated artifact, or model/data work.
- Do not change the disabled broker adapter, the existing body mappers, the
  terminal KIS read-only evidence, or local-paper behavior.
- Do not treat a source conflict as permission to derive a virtual TR ID from a
  real TR ID. No order transport may be created under this goal.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Resolve KIS paper order route evidence`
