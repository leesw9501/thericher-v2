# Next Codex Goal

## Objective

Add one source-attested, pure offline mapping from the existing
`BrokerOrderRequest` to KIS virtual-paper US **long-only limit-order** fields.
It prepares a later separately authorized paper canary without creating a
network path, credential path, order-submission capability, or second broker
request contract.

## Required Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and
   `agents/execution.md`.
3. Read `src/thericher_v2/execution/broker.py`, its boundary tests, and the
   current read-only KIS clients only to preserve their separation.
4. Obtain and record one current public official KIS source for the virtual
   overseas-stock paper order request shape. Do not call the KIS API, read
   credentials, or inspect account snapshots.

## Work Packages

### Execution Agent

- Reuse `BrokerOrderRequest`; do not introduce another order-request dataclass
  or a KIS transport/adapter.
- Implement one pure, deterministic field mapper for the documented virtual
  paper US buy limit-order shape. It must reject every sell, market order,
  unsupported market, malformed symbol, nonpositive quantity, and invalid
  limit price.
- Preserve `create_kis_broker_adapter()` as disabled and structurally unable to
  submit, cancel, or query status. Do not create a `kis-order` Docker profile,
  environment loader, request sender, scheduler, dashboard control, or mode
  change.

### Data And Validation

- Data records only public-source provenance needed to pin the field names and
  enumerations; it does not create a provider, market-data claim, or data
  capability.
- Validation independently proves the new mapper has no credentials, network,
  or broker transport dependency, and that the existing runtime adapter remains
  disabled. Tests may exercise only pure mapping and existing fake/local paper
  components.

## Decision Boundary

- If an official public KIS source cannot establish the exact virtual-paper
  request fields well enough for falsifiable offline tests, record the mapping
  as unsupported and do not guess, add a transport, or call KIS.
- This goal does not authorize paper capital, KIS submission/cancellation,
  `KIS_LIVE_*`, or any live behavior.

## Hard Boundaries

- No `.env`, credential, account-state, or runtime-snapshot reads.
- No KIS API request, order action, Docker profile, external artifact, or
  public service.
- No model, GPU, data-acquisition, capability-promotion, or dashboard work.
- Do not alter terminal KIS probe or reconciliation evidence.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Add offline KIS paper order field mapper`
