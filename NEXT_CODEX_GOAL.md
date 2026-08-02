# Next Codex Goal

Read `HANDOFF.md`, `AGENTS.md`, `agents/engine-research.md`,
`agents/research-steward.md`, `agents/execution.md`, and
`agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run one bounded CPU-only source-local falsification:
`spy-first30-final30-momentum-v1`.

It tests the distinct Gao et al. market-intraday-momentum premise using the
existing verified local `SPY/AMS` 1m cache. It is not model selection, a
profitability claim, Paper input, order, or live route.

## Frozen Source And Contract

- Source: `kis.paper.private.intraday.spy.ams.m1.v1`, hash
  `sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6`.
- Research source: Gao, Han, Li, and Zhou, *Market intraday momentum*,
  Journal of Financial Economics 129(2), 2018, DOI
  `10.1016/j.jfineco.2018.05.009`. Its stated SPY sample is 1993-2013; the
  current 21-session cache is a small non-promoting replication only.
- Require exactly 21 complete regular sessions, ordered as `10 development /
  1 purge / 10 validation`. The first session may be structurally unavailable
  because it has no prior in-cache close.
- At completed 10:00 ET, compute the sign of current 09:30-10:00 return from
  the prior completed session's 16:00 close. Freeze it with no later input.
- One eligible signed long/short decision per session enters at 15:30 ET and
  exits at the completed 16:00 ET close. The target is evaluated only after
  target-free preflight.
- Require at least eight eligible validation decisions before target access.
- Use all-in round-trip costs of `5`, `10`, and `20` bps. The hard kill is a
  non-positive signed validation total at `20` bps. The direction-inverted,
  same-timestamp counterpart is the comparative reference; it is not a
  selection or ensemble input.
- No parameter/window/filter tuning after any target access.

## Boundaries

- Do not call KIS, read `.env` or credentials, submit orders, access accounts,
  use local-paper, network, GPU, training, model weights, or live behavior.
- Use only the verified offline loader and existing local cache.
- Do not store raw bars, timestamps, prices, returns, credentials, or model
  artifacts in Git. Write source-safe aggregate receipts only below
  `D:\thericher-v2\model-artifacts`.
- A result remains non-promoting: no model selection, PnL/profitability claim,
  Paper candidate, or GPU appointment.

## Required Work

1. Implement the frozen causal preparation/evaluation/run path and a small
   runner with pinned source identity.
2. Run target-free preflight before accessing target values; report only
   source-safe aggregate counts.
3. Run one real CPU falsification from the local cache with an external,
   idempotent run label.
4. Add focused tests for causal prior-close/first-30m inputs, target isolation,
   complete-session handling, cost/anti-signal comparison, external artifact
   redaction, and absence of network, credential, broker, account, order,
   local-paper, GPU, and live surfaces.
5. Treat Claude's failed bounded check as `review_unavailable`, not agreement
   or a hold. Record it only if it materially affects the result context.

## Verification

Run:

```powershell
uv run --extra dev pytest -q <focused changed tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose --profile research config --quiet
```

## Completion

Report the frozen source and contract, source-safe CPU result, external
artifact location, tests, commit hash, intentional omissions, and the next
recommended objective. Replace this file with exactly one next objective only
after completion evidence is committed and pushed.
