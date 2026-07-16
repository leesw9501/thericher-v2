# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add broker-safe local-paper source-filtered attribution views.

This advances paper trading preparation, PnL attribution, and live-risk control
by making local-paper evidence queryable by fill source before any broker fills
exist. The feature-branch replay now produces local-paper fills; the next step
is to make sure future mixed execution data cannot be mistaken for local-paper
research evidence.

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
2. Inventory only the current useful external artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-candidate-feature-branch-replay-mini-smoke\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-feature-branch-replay-mini-smoke-robustness\metrics.json`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-feature-branch-replay-mini-smoke.json`
   - referenced local-paper `events.jsonl` artifacts under the replay lineage.
3. Add a small source-filtered local-paper attribution/query helper that:
   - reads replay/robustness artifacts or event logs without credentials,
   - counts fills by `source`,
   - can return local-paper-only fills and reject or mark non-local sources,
   - records PnL/fill-count evidence only when `source: local_paper` is proven,
   - treats missing zero-fill event files as empty evidence but does not ignore
     unreadable nonzero-fill artifacts,
   - writes no market data or model artifacts into Git.
4. Integrate the helper where existing replay attribution currently verifies
   local-paper fills, without broad rewrites or a new report family.
5. Add focused tests proving:
   - local-paper-only evidence is accepted,
   - mixed or unknown fill sources are detected,
   - missing zero-fill event artifacts are tolerated,
   - unreadable nonzero-fill event artifacts are not silently accepted,
   - no broker/network/credential access is needed,
   - output stays descriptive and non-promotional.
6. Run a CPU/local smoke using generated unit artifacts. Docker GPU work is not
   required unless code paths touch research inference.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from existing external model artifacts and local-paper event artifacts.
- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active attribution loop.
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

Report any focused local-paper source-filtering or attribution smoke command
used.

## Suggested Commit Message

`Add local paper source filtered attribution`

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
