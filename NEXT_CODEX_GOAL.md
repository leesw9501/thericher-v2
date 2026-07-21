# Next Codex Goal

## Objective

Build the first executable KIS **virtual-paper-only** US buy canary path and
connect its sanitized runtime state to the existing local dashboard.

The purpose is execution learning, not a profitability ceremony. The operator
has standing-authorized all private `KIS_PAPER_*` work, including account and
market reads, submit/modify/cancel, sizing, reconciliation, data retention, and
goal-owned schedules. Do not ask for paper capital, a trade count, a dashboard
review, a profitability result, or a per-call confirmation. `KIS_LIVE_*`, live
hosts, and real-money behavior remain unavailable.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and
   `agents/execution.md` first; then read `agents/data.md` and
   `agents/engine-research.md` for current data/model context.
3. Ask Claude for a concise falsification-first review before relying on a new
   paper submit/reconciliation route. Do not send credentials, account values,
   raw broker payloads, or source data.

## Work Packages

### Execution Agent

1. Close the current injected-transport allowlist gap: validate host, method,
   path, query, and allowable headers in the KIS paper client before every
   transport invocation, not only inside the urllib implementation.
2. Build one narrow KIS paper adapter for US **buy limit** orders only. It must
   pin the KIS virtual-paper host, use only documented virtual-paper TR IDs,
   reject every live host/credential/route, and leave US sells out of scope
   until their official TR-ID contradiction is resolved.
3. Persist an idempotent intent before KIS submission; reconcile account,
   positions, open orders, and `inquire-ccnl` before replacing an unknown
   result. A recovery anomaly is a technical reconciliation task, not an
   operator approval gate.
4. Provide a goal-owned Docker command for a bounded paper canary. Its default
   execution may use the actual KIS virtual account when configured. It must
   write only sanitized runtime/event evidence outside Git and must never print
   tokens, account identifiers, or raw broker bodies.
5. Project the resulting sanitized account/order/emergency status to the
   credential-free local dashboard. The web process must not receive KIS
   credentials or call KIS itself.

### Data Agent

- Keep KIS market-data cache and paper execution evidence separate. A canary
  may use the existing KIS-native daily/intraday inputs but must not duplicate
  raw broker payloads into `D:\market_data` or Git.
- Keep the 694-session unadjusted daily panel and its `burned_precontract`
  comparative interpretation visible; neither blocks a paper canary.

### Engine Research Agent

- Supply only deterministic, explicit buy intent inputs for the first canary;
  do not couple paper submission to an unvalidated learned model.
- Continue breadth/depth queue preparation on CPU while execution work runs.
  CUDA starts only for a distinct falsifiable candidate, never as a substitute
  for a paper transport test.

### Validation

- Independently verify that test adapters cannot route live, all intended KIS
  requests are allowlisted before transport, intent persistence precedes side
  effects, unknown outcomes reconcile without duplicate submission, and web
  code remains credential-free.
- Check a real virtual-paper canary only for bounded execution facts
  (acknowledgement/reconciliation/sanitized state), not a return claim.

## Operating Boundaries

- `KIS_PAPER_*` access and virtual orders are standing-authorized. A historical
  one-shot marker, a factual raw-retention field, weak research evidence, or a
  missing profitability report cannot disable the work.
- Keep all generated artifacts under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`; raw market data stays under `D:\market_data`; neither
  belongs in Git.
- Do not read `KIS_LIVE_*`, construct a live route, buy data/services, expose a
  public service, or print/persist secrets or account identifiers.
- Technical correctness remains mandatory: paper-only routing, explicit limit
  price/whole-share validation, intent-before-side-effect, idempotence, and
  reconciliation before replacing an unknown broker result.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add KIS paper buy canary adapter`
