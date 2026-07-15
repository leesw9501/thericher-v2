# Review Agent

## Engine Loop

- backtest and walk-forward validation
- paper trading
- live-risk control

## Owns

- Simplicity review and v1-sprawl detection.
- Checks for unnecessary docs, gates, reports, scripts, and workflows.
- Boundary review for credentials, broker calls, live mode, and dashboard
  exposure.

## Must Not

- Own implementation.
- Add review artifacts unless they directly reduce engine risk.
- Block research iteration for warnings that are not execution hard stops.

## Held Resources

- None.

## Active Queue

1. Review threshold robustness replay for data/query sprawl.
2. Keep agent stateboards short and retire stale ones.

## Running Jobs

- None.

## Done Recently

- Drift checks kept market-data and handoff changes small.
- Validation target stayed broker-free, credential-free, and artifact-light.
- Experiment queue stayed a single runner and concise metrics artifact, with no
  promotion gate or dashboard expansion.
- Walk-forward stayed capped and artifact-only, with no promotion gate.
- GPU candidate smoke stayed metadata-only and did not add a promotion gate.
- GPU runtime smoke stayed `nvidia-smi`-only and outside Git.
- GPU compute smoke stayed research-profile-only, did not add heavy base
  dependencies, and produced one concise external artifact.
- GPU training smoke scaffold added one CLI and one focused test file without
  adding a framework dependency or a promotion gate.
- PyTorch CUDA was confined to the Docker `research` stage, with tests checking
  that base/runtime stages and `pyproject.toml` remain torch-free.
- Research job runner stayed single-kind and artifact-only; it did not create a
  broad agent platform or new stateboard files.
- Candidate training extended the job runner with one explicit second kind,
  stayed bounded by caps, wrote artifacts outside Git, and did not add a
  promotion gate, dashboard, broker call, or new report family.
- Candidate evaluation extended the job runner with one explicit third kind,
  stayed artifact-only, kept PyTorch lazy/research-only, and deferred
  local-paper conversion instead of creating a promotion gate.
- Candidate replay extended the job runner with one explicit fourth kind,
  stayed broker-free/local-paper-only, kept fills labeled `source:
  local_paper`, and did not add a promotion gate or dashboard surface.
- Candidate replay comparison extended the job runner with one explicit fifth
  kind, stayed artifact-only and local-paper-only, consumed existing replay
  evidence when available, and did not add a promotion gate, dashboard, or
  scheduler.
- Candidate threshold sweep extended the job runner with one explicit sixth
  kind, reused the candidate replay execution path, kept PyTorch lazy/research
  only, and did not add a promotion gate, dashboard, or scheduler.

## Next Handoff

- Challenge any new document or workflow that does not improve a named engine
  loop.
