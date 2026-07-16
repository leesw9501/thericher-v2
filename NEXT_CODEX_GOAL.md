# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add broker adapter boundary contracts and local-only execution fuses.

This advances paper trading preparation and live-risk control by defining the
smallest broker boundary before any KIS integration exists. The goal is to make
future broker work explicit and disabled by default while keeping the local
paper simulator separate.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Keep simulated fills labeled with `source: local_paper`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, or dashboard
  expansion.
- Do not call any threshold, candidate, or model best, recommended, passed,
  promoted, or production ready.

## Required First Reads

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
   - `agents/README.md`
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before architecture-changing edits.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Reuse the existing local paper simulator and source-filter evidence helpers;
   do not add a new replay/report family.
3. Add minimal broker adapter contracts for:
   - account mode/capabilities,
   - order submit intent/result,
   - cancel intent/result,
   - order status lookup.
4. Add a disabled-by-default broker factory or KIS adapter skeleton that returns
   explicit unavailable results or errors without reading credentials or using
   the network.
5. Add local-only execution fuses so broker submit paths cannot be reached
   unless a future explicit goal enables them.
6. Add focused tests proving:
   - no network, KIS API, or credential access is needed,
   - broker submit/cancel/status are unavailable by default,
   - local paper execution behavior remains unchanged and separate,
   - disabled broker results cannot be confused with `source: local_paper`
     fills,
   - the implementation stays descriptive and non-promotional.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- This goal should not require new market data.
- Start from existing local-paper event/replay artifacts only if they are useful
  for boundary tests.
- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active boundary loop.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact symbols, markets, date ranges,
  formats, and blocker reasons in `agents/data.md` and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Report any focused broker-boundary or local-paper smoke command used.

## Suggested Commit Message

`Add broker adapter boundary fuses`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- what was intentionally not built,
- next recommended goal.
