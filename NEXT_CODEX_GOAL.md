# Next Codex Goal

## Objective

Measure and reduce the broad KIS Paper D1 collector's rate-limit restart gap
without changing its source scope or request rate.

The active current-listing `daily-nas-broad/v1` cache reached a source-safe
`rate_limited` stop after useful accepted-page progress. Its current 07:15-20:45
KST trigger window leaves a multi-hour restart gap after an off-window run. The
goal is one bounded same-client recovery experiment, not a request flood,
schedule platform, historical-universe claim, training campaign, or broker
feature.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach only source-safe aggregate broad-cache/index/receipt facts. Do not
   print raw symbols, rows, prices, volumes, tokens, account identifiers, or
   provider response bodies.
3. Ask Claude for a short falsification-first drift check before changing the
   collector's rate-limit recovery or its task trigger policy. Include the
   observed 148-attempt/288-page/one-rate-limit run, one-second gate,
   five-minute fresh-token guard, no-foreground-wait rule, and the strongest
   throughput/rejection kill test.

## Authority And Boundaries

- `KIS_PAPER_*` may be used only by the existing broad KIS Paper `dailyprice`
  client route. No account, position, quote, order, dashboard, KIS live, model,
  GPU, or execution route belongs to this objective.
- Keep one collector per broad cache and preserve the existing shared gate,
  one-second request-start pace, source allowlist, D: storage policy, and
  `IgnoreNew` duplicate protection.
- Never write a token, credential, raw response, account fact, or broker body
  to Git, a stateboard, a log, or a derived artifact.
- A rate wait belongs only to the Docker collector; Codex must not foreground
  sleep while another Data, Research, or Execution package is ready.
- Do not widen trigger density until the bounded recovery experiment has
  source-safe evidence that accepted-page progress resumes without a worse
  rate-limit-per-accepted-page result. Keep any unchanged schedule fact visible.

## Work

1. **Data:** add one explicitly bounded same-client rate-recovery path: after a
   `rate_limited` result, retain the in-memory client for at most one measured
   gate-due retry within that worker's existing runtime budget. A second
   rate-limit, another shared stop, expired runtime, invalid cache, or storage
   floor yields to the owner scheduler with truthful recovery state.
2. **Validation:** add focused deterministic tests proving one client/token is
   reused, the wait is bounded and never occurs in Codex, no retry loop becomes
   unbounded, source-safe receipts disclose recovery counts/outcomes only, and
   account/order/live routes remain absent.
3. **Data:** rebuild the Docker image and run one bounded real continuation
   after deployment. Record only aggregate attempts, accepted pages,
   categorical reasons, rate-recovery count, task result, and D: free-space
   bucket. Do not interpret a single run as a provider limit.
4. **Orchestration:** compare the run with the existing 148-attempt/288-page
   receipt. If the probe resumes accepted progress and does not worsen
   rate-limited-per-accepted-page evidence, propose the smallest trigger-window
   change needed; otherwise retain the existing schedule and record the
   reversal fact.
5. Refresh affected stateboards, replace this file with exactly one next
   objective, then continue.

## Completion

- One bounded same-client rate-recovery implementation and source-safe real or
  deterministic probe receipt exist outside Git.
- The broad collector remains one-client, dailyprice-only, cache-owned, and
  recoverable; no additional broker surface exists.
- Trigger-policy evidence is explicit rather than inferred from a local
  backoff constant.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Recover broad KIS D1 rate limits`
