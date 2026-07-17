# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add one bounded Infra artifact-root and Docker `research` mount sanity check.

This advances feature/model research, paper trading, and reproducibility by
proving that generated GPU/model and local-paper artifacts stay outside Git and
that Docker `research` still maps the expected external paths before more long
GPU or replay work runs.

Codex should auto-select this lane by rotation. Do not stop for an ordinary
operator lane choice; stop only for a true approval or ambiguity listed below.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, dashboard, or auto-commit worker.
- Do not run model training, ablation, trace compute, trace recompute,
  threshold search, replay rerun, exit-policy simulation, broker execution,
  data acquisition, or broad recursive `D:\market_data` scans.
- Do not change model promotion rules or thresholds.
- Do not add PyTorch/CUDA or heavy research dependencies to local/base `engine`
  or `web` paths.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` and Docker `/app/model_artifacts`.

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
   - `agents/infra.md`
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/review.md`
   - `D:\thericher-v2\model-artifacts\execution-paper\local-paper-fill-source-parity-audit-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before architecture-changing edits,
   Docker/dependency changes, agent governance changes, durable worker policy
   changes, or artifact contract changes. A focused test/inspection that only
   verifies existing mounts and artifact-root policy does not require Claude.

## Required Work

1. Inspect the existing Docker Compose, Dockerfile/research target, artifact
   root configuration, and tests that enforce PyTorch/research isolation.
2. Add the smallest useful sanity check proving:
   - generated model/GPU artifacts are expected outside the Git workspace,
   - Docker `research` maps `/app/model_artifacts` to the external artifact
     root,
   - Docker `research` maps `/app/market_data` read-only when local market data
     is available,
   - base/local environments stay torch-free unless explicitly approved.
3. Prefer focused tests or one compact smoke artifact over a new framework,
   report family, gate, daemon, or dashboard.
4. If Docker is available, run only a tiny non-training container/config smoke.
   Do not start a long GPU job.
5. If useful, write one compact external artifact under
   `D:\thericher-v2\model-artifacts\infra`.
6. Update `HANDOFF.md`, `agents/infra.md`, and other stateboards only if
   needed.
7. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Report any focused test, Docker config, or tiny container smoke used.

## Suggested Commit Message

`Add artifact mount sanity check`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data acquisition, Docker/GPU training, or broker behavior was touched,
- produced artifacts,
- mount/artifact invariant added,
- what was intentionally not built,
- next recommended goal.
