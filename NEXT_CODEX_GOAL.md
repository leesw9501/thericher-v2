# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-ragged-sequence-runtime-v1`: turn the existing frozen
`short` QQQ/SPY `1m/5m/10m/1h/3h` causal controls into one explicit, target-free
ragged sequence input contract for three candidate architecture families:
per-timeframe recurrent, causal temporal-convolution, and masked
cross-timeframe attention runtime paths.

This is runtime and representation plumbing only. It must advance the eventual
model engine without claiming a trained predictor, model selection, return,
PnL, or Paper decision from the current 42-control inventory.

## Boundaries

- Ask Claude for one concise falsification-first drift check before defining
  cross-timeframe alignment/masking or dispatching CUDA work.
- Reuse `ProfiledMtfFlattenedControl`, its causal sequence/projection contracts,
  and the existing local QQQ/SPY runtime inventory. Do not add a provider,
  source format, KIS call, scheduler, historical evaluation dataset, or generic
  model platform.
- Preserve each timeframe's native ordered sequence. Do not silently align
  rows by index across timeframes or pad missing data without an explicit mask
  and availability meaning.
- Run a deterministic CPU-first structural smoke. If its contract and CPU
  receipt are complete and Docker CUDA is available, run one bounded CUDA
  structural smoke for the three fixed families. Artifacts and any temporary
  weights belong only under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`, never Git.
- Do not read `.env` or credentials; call KIS; use a broker/account/order route;
  create a Paper action; enable live behavior; expose a service; calculate a
  target/return/PnL; or load untrusted public weights.
- Treat unavailable CUDA, absent source controls, or a failed family as a
  categorical non-promoting result for that exact runtime attempt. Do not wait
  or invent a substitute training campaign.

## Required Work

1. Engine Research: freeze the smallest canonical ragged-layout contract for
   `short`: per-timeframe sequence order/lengths, feature width, timestamps or
   time deltas needed by a mask, pair/leg order, source-control identities, and
   exact availability rules. Make mismatched, incomplete, future, forged, or
   post-cutoff controls fail closed before a runtime family can consume them.
2. Implement three narrow target-free consumers over exactly the same frozen
   controls: per-timeframe recurrent, causal TCN, and masked attention. Their
   outputs may be shape/digest/runtime facts only; do not persist predictions,
   scores, weights, raw features, labels, or values.
3. Run CPU structural smoke first. Then let Research Steward allocate at most
   one bounded Docker CUDA appointment only if the CPU receipt matches the
   exact contract. Record source-safe family/phase/status/count/shape/receipt
   identities and an explicit no-predictive-claim scope.
4. Data Agent: reattest only the existing source-safe runtime inventory and
   report its exact input status. Do not collect, mutate, or reinterpret cache
   data. Execution has no work in this objective.
5. Add focused tests for causal/ragged layout, mask semantics, family parity,
   CPU-before-CUDA, unavailable-CUDA containment, external artifact isolation,
   and no credential/network/execution import route. Update Engine Research,
   Research Steward, Data, and orchestration stateboards.

## Completion Evidence

- one tested target-free ragged sequence contract over the existing five
  timeframe controls;
- CPU receipt and, when available, one bounded Docker CUDA receipt for the
  same contract;
- source-safe external artifacts only, with no model/predictive/PnL/Paper claim;
- commit and push, then replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
