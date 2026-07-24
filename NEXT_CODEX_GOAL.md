# Next Codex Goal

## Objective

Qualify the existing local Norgate US Stocks trial snapshot for one bounded,
development-only broad daily feature contract. The outcome is either an
evidence-backed development input or a scoped rejection; it is not a model,
paper-trading, or historical-universe promotion.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/orchestration.md`
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/review.md`

3. Ask Claude for a short falsification-first drift-check before accepting or
   widening any Norgate-derived contract. Do not send raw rows, personal data,
   credentials, or trial keys.

## Hard Boundaries

- Use only already retained local Norgate trial data under `D:\market_data`.
  Do not download, refresh, buy, enroll, or accept a new license.
- Do not read `.env`, credentials, secret-like files, or `KIS_LIVE_*`.
- Do not call Tiingo, KIS, a broker, or any network endpoint.
- Do not train, score, tune, select, ensemble, or run GPU work.
- Do not call the snapshot a point-in-time universe, listing/delisting source,
  corporate-action truth, executable price source, Paper input, or live input.
- Keep raw data and generated artifacts outside Git. Write only one small,
  sanitized external receipt when it improves the data/research loop.
- Do not create a new report, gate, or agent stateboard unless it removes a
  concrete engine-loop ambiguity.

## Role-Owned Work

### Data Agent

1. Inspect the useful local Norgate snapshot and existing loader/manifest code
   without an expensive full-drive scan. Re-attest its immutable file and
   manifest identities, field coverage, symbol/session geometry, and known
   trial limitations.
2. Prefer extending an existing narrow development-universe contract over
   adding another loader. Preserve static-universe, survivorship, adjustment,
   rights, and point-in-time limitations as machine-readable scope.
3. Write one sanitized external qualification or rejection receipt with hashes,
   counts, scope, and reversal facts only. Never persist raw rows or prices.

### Engine Research Agent

1. If and only if Data qualifies the local input for development preparation,
   define one fixed causal daily feature-window and outcome-timing interface.
   It must be explicitly development-only and cannot enter a campaign, model,
   paper intent, or GPU queue yet.
2. If the input is rejected, record the exact missing fact and leave the
   prospective KIS intraday contract as the next model-ready path. Do not
   invent a repair, derived universe, or substitute source.

### Validation Agent

Independently try to break the proposed scope: static-universe leakage,
future-row access, session misalignment, raw-field persistence, and accidental
model/Paper routing. It evaluates the contract without tuning it.

## Completion Evidence

- Local-only source identity and geometry are re-attested before a consumer sees
  candidate feature rows.
- The outcome explicitly states `qualified_for_development_only` or
  `unqualified`, with the evidence that would reverse it.
- Tests prove offline/credential-free behavior, source-drift rejection,
  static-universe/PIT limitations, future-data isolation, no raw artifact
  persistence, and no model/GPU/KIS/Paper route.
- Claude's concise verdict is recorded only if it changes the durable decision.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Qualify Norgate development input`
