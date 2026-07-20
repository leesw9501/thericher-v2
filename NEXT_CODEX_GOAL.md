# Next Codex Goal

## Objective

Falsify, entirely offline, whether the current `QQQ` / `NAS` raw-`1m`
continuation-request contract could plausibly explain the terminal
2026-07-20 `minute_response_rejected` observation. This is a narrow execution
reliability objective: improve the request contract before considering any
separately scoped future market-data observation. It must not claim what KIS
received or returned.

## Required Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `ARCHITECTURE.md`, `agents/data.md`, and `agents/execution.md`.
3. Read the raw-minute client, its fake-transport tests, the terminal v4
   sanitized summary, and its reservation marker as metadata only.
4. Ask Claude for one short falsification-first review before concluding that
   an offline request-shape change is warranted. Do not share credentials,
   account identifiers, raw response data, or row-level prices.

## Work Packages

### Execution Agent: Offline Continuation Contract

- Trace the exact first-page and continuation request construction through the
  allowlisted transport, including host, path, TR ID, headers, `PINC`, `NEXT`,
  and `KEYB` handling.
- Compare it with the locally recorded official KIS sample/documentation. A
  public documentation refresh is allowed only when it sends no KIS API request
  and no credential. Record whether each difference is `supported`,
  `unsupported`, or `unresolved` from source and code alone.
- Add only focused fake-transport tests or a small contract helper if they
  materially falsify a request-shape hypothesis. Do not add a scheduler,
  generic KIS client, diagnostic report family, or retry facility.

### Data And Validation: Boundaries

- Data keeps the raw-minute capability and trusted registry unchanged. State
  exactly why no offline request test can qualify `1m`, `5m`, `10m`, `1h`, or
  `3h` input.
- Validation independently checks that the result does not claim an on-wire
  cause, retain raw data, broaden endpoint access, or reopen the terminal v4
  attempt.

## Hard Boundaries

- Do not read `.env` or any KIS credential.
- Do not call KIS, Tiingo, Norgate, a broker, or any account/order/live endpoint.
- Do not submit, modify, or cancel any order; keep `THERICHER_MODE=off`.
- Do not run GPU/model training, create a dataset/cache, promote a capability,
  propose paper capital, or change paper/live authority.
- Do not alter the v4 external artifact, reservation marker, or ledger.
- Do not persist raw market data in Git or under `D:\market_data`.

## Completion Evidence

- A concise source/code comparison with every conclusion marked supported,
  unsupported, or unresolved.
- Focused tests proving any contract correction is offline and remains within
  the one-token/two-page client bounds.
- Updated Execution and Data stateboards, `HANDOFF.md`, and this next goal.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Falsify KIS continuation contract offline`
