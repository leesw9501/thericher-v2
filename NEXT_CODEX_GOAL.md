# Next Codex Goal

## Objective

Add one source-attested, pure offline mapping from the existing
`BrokerOrderRequest` plus an explicit KIS US exchange to virtual-paper US
**sell-limit body fields** for a long-only reduction.

This completes the non-transmittable exit-side counterpart to the existing
buy-limit body mapper. It does not prove a position, enable shorting, create a
KIS request path, or authorize paper submission.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and
   `agents/execution.md`.
3. Read `src/thericher_v2/execution/broker.py`,
   `src/thericher_v2/execution/kis_paper_order_fields.py`, and their focused
   tests.
4. Obtain or reattest one public official KIS source for the virtual overseas
   US sell-limit sample. Do not call KIS, read `.env`, credentials, account
   state, or runtime snapshots.

## Work Packages

### Execution Agent

- Reuse `BrokerOrderRequest`; preserve the existing buy mapper unchanged and
  do not introduce a KIS transport, adapter, header builder, or new request
  dataclass.
- Add one deterministic sell-limit **body-fragment** mapper. It must require an
  explicit `NASD`, `NYSE`, or `AMEX` exchange; accept only `side="sell"` US
  whole-share positive limit orders; and map only official-source-attested
  fields.
- It must reject buys, market orders, unsupported market/exchange, malformed
  symbols, fractional or nonpositive quantity, and invalid limit price.
- The mapper cannot establish a holding or authorize a sale. Existing
  deterministic position/risk checks remain the sole long-only reduction
  authority.
- Preserve `create_kis_broker_adapter()` as disabled. Do not add a Docker
  profile, `.env` reader, endpoint, HTTP sender, TR-ID/header handling,
  scheduler, dashboard control, mode change, artifact, or order path.

### Data And Validation

- Data records only the public-source provenance needed to pin the sell fields
  and their limits. It does not create a market-data capability, provider, or
  account-data claim.
- Validation proves that importing and invoking the sell mapper requires no
  credential, file, network, or broker transport access, and that the existing
  runtime adapter remains disabled. Tests may use only pure mapping and the
  existing fake/local-paper components.

## Decision Boundary

- If official public KIS material cannot pin the virtual-paper US sell-limit
  body fields tightly enough for falsifiable offline tests, record the work as
  unsupported. Do not guess, widen the mapper, add a request path, or call KIS.
- This goal does not authorize a paper capital envelope, KIS order
  submission/cancellation, `KIS_LIVE_*`, or any live behavior.

## Hard Boundaries

- No `.env`, credential, account-state, or runtime-snapshot reads.
- No KIS API request, order action, Docker profile, external artifact, or
  public service.
- No model, GPU, data acquisition, capability promotion, or dashboard work.
- Do not alter terminal KIS probe/reconciliation evidence or the existing
  buy-limit mapper's behavior.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Add offline KIS paper sell field mapper`
