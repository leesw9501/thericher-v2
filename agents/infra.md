# Infra Stateboard (Retired)

## Status

Retired as a durable lane on 2026-07-18. Infra is an invoked capability owned
through Codex orchestration when Docker, CUDA, dependencies, mounts, storage,
CI, or runtime reproducibility work is ready.

## Current Resources

- GPU research runs in Docker `research` with PyTorch CUDA.
- Model artifacts: `D:\thericher-v2\model-artifacts`.
- Docker artifacts: `/app/model_artifacts`.
- Market data: `D:\market_data`, read-only in research containers.
- Storage warning: projected free space below 20 percent.
- Storage hard floor: do not start new large work that crosses 15 percent.

## Durable Knowledge

- Base/local tests remain torch-free.
- GPU/model mounts belong only to the research profile unless runtime inference
  later needs an explicit contract.
- Infra changes do not select models or change execution-risk policy.
- No daemon, coordinator, dashboard expansion, notification loop, or auto-commit
  service is currently approved. Goal-owned schedules are allowed under the
  current `AGENTS.md` policy when an active engine objective needs one.

## Recovery

For an invoked task, record container/image identity, mount roots, dependency
lock hash, active process or stale-lock evidence, durable output, and the next
`resume` or `restart` action in the shared recovery view when available.

## History

Detailed prior history remains in Git at commit `8f416f8` and in external
artifacts, including:

`D:\thericher-v2\model-artifacts\infra\artifact-mount-sanity-20260717-r1\metrics.json`

Reactivate a durable stateboard only after recurring independent Infra work is
demonstrated across multiple Codex tasks.
