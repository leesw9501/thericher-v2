# Next Codex Goal

## Objective

Add one pure offline projection from the existing `OrderIntent` to the existing
`BrokerOrderRequest` for an explicitly supplied **limit order only**.

This closes the structural gap between deterministic target-position intent and
the broker-neutral risk/request contract. It must reject a missing limit price
rather than read a quote, infer a price, or turn a market intent into a KIS
order.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and
   `agents/execution.md`.
3. Read `src/thericher_v2/contracts.py`,
   `src/thericher_v2/execution/broker.py`,
   `src/thericher_v2/execution/target_position.py`, and their focused tests.

## Work Packages

### Execution Agent

- Add one pure helper in the existing broker-contract ownership boundary. Reuse
  `OrderIntent` and `BrokerOrderRequest`; do not create a new request dataclass
  or KIS-specific object.
- The helper may project only an intent that already contains a positive limit
  price. It must preserve client ID, symbol, market, side, quantity, decision
  ID, creation time, and schema version exactly.
- It must reject a missing limit price, malformed/corrupted input, and any
  value the existing `BrokerOrderRequest` contract rejects. It must not fetch,
  infer, round, clamp, or alter a price or quantity.
- It must not persist, submit, risk-approve, reconcile, call a broker, enable
  `create_kis_broker_adapter()`, or connect to the KIS body mappers. Risk and
  position validation remain separate later callers.

### Validation

- Prove projection is pure and import-safe: no credential, environment, file,
  network, transport, artifact, or broker side effect is needed.
- Prove a target-position market intent (`limit_price=None`) stays
  non-projectable, while an explicit limit intent round-trips every contract
  field unchanged.
- Confirm the existing KIS adapter remains disabled and unavailable after the
  new helper is invoked.

## Hard Boundaries

- No `.env`, credential, account-state, runtime-snapshot, market-data, quote,
  or KIS API read.
- No KIS order/header/TR-ID work, Docker profile, external artifact, public
  service, model, GPU, data acquisition, capability promotion, or dashboard
  work.
- Do not alter the terminal KIS evidence or existing buy/sell body mapper
  behavior.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Project limit intents into broker requests`
