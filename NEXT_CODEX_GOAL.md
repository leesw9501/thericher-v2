# Next Codex Goal

## Objective

Keep the automatic broad KIS Paper D1 collector independent while making the
Engine Research lane continuously useful: implement auditable campaign custody
and run the first source-isolated, target-free sequence-representation study on
the frozen Norgate D1 development panel.

This is model-plumbing and representation evidence only. It must not establish
profitability, a direction forecast, a point-in-time universe, ranking,
ensemble, Paper signal, or broker claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect the installed broad task and source-safe postrun/chronology roots.
   Do not start, stop, duplicate, or alter the collector.
3. Reattest the exact frozen Norgate panel identity before Research reads it.
   Do not reuse `norgate_broad_development_artifact` because its direction label
   and discontinuity filter inspect future indices.
4. Use the recorded Claude `supported-with-limits` review as the starting
   falsification check. Ask Claude again before any change to source eligibility,
   model promotion, comparative interpretation, Paper route, or public-model
   runtime/dependency.

## Authority And Boundaries

- The broad collector remains the sole owner of KIS Paper credentials, network,
  cursor, pacing, raw cache, and postprocess invocation. This goal makes no
  manual KIS call and reads no credentials.
- Research runs only in the Docker `research` service with network disabled,
  read-only source mounts, and artifacts under `/app/model_artifacts` mapped to
  `D:\thericher-v2\model-artifacts`.
- Keep the frozen Norgate panel's static, non-PIT, unverified-adjustment scope
  explicit. A target-free representation exercise does not change its
  `campaign_eligible`, `model_eligible`, `gpu_eligible`, or Paper eligibility
  fields.
- Do not create a forward label, inspect `t+1` or later data for any sample,
  load a public model/weight, use a public-model runtime, rank symbols, replay
  PnL, create a local-paper intent, or create an ensemble.
- Do not persist raw rows, source values, predictions, credentials, account
  facts, or broker bodies. Generated weights must use a safe non-pickle format
  and remain outside Git.
- Fixed architecture losses are diagnostics only. No early stopping,
  architecture winner, score leaderboard, threshold tuning, or model selection
  is allowed in this objective.

## Parallel Work Packages

1. **Data / temporary Validation:** When the automatic postrun receipt appears,
   reattach it through the existing offline path and preserve the candidate-bound,
   aggregate chronology observation or its scoped retry fact. A missing receipt
   is external timing evidence only and does not delay Research.
2. **Engine Research - campaign custody:** Implement a minimal append-only,
   source-safe external campaign registry keyed by frozen contract hash. Record
   dataset/split/cost/trial-family/trial-index/holdout-access identities and
   terminal non-promoting outcome references; reject Git-local artifact roots.
3. **Engine Research - sequence/DL track:** Build a separate Norgate observed-
   window dataset from only completed `t-window+1..t` returns. Freeze its
   geometry, masking objective, source identity, fixed architecture specs, and
   stop budget in an external contract. Run a Docker CPU smoke before one
   bounded GPU batch of GRU, LSTM, causal-TCN, and compact-attention masked-span
   reconstruction jobs. Persist only source-safe summaries, checksums, and safe
   external weights.
4. **Strategy Discovery:** Produce one compact external source-safe handoff for
   official public time-series model candidates. Include source identifier,
   retrieval time, verbatim license text, mechanism, and stated discovery/
   pretraining corpus period and instrument scope or `not_disclosed`. Do not
   add a dependency, download a weight, or turn it into a campaign.
5. **Validation:** Add focused tests proving the registry and representation
   contract need no network, broker, KIS, or credential access; reject future
   indices and Git-local artifacts; retain no raw data or score-based selection.

## Completion

- The campaign registry is append-only, external, idempotent by frozen contract
  identity, and covered by focused tests.
- The target-free contract independently reattests the frozen panel and cannot
  read a forward label or future-aware feature artifact.
- CPU smoke and the bounded Docker CUDA batch complete or preserve a scoped,
  source-safe failure/recovery artifact. Any weights are external safe files.
- Strategy Discovery has either a source-safe handoff or a scoped no-source
  result; it cannot block the other packages.
- A broad postrun receipt, when available, is handled only through its existing
  offline reattachment path.
- Refresh Data/Research/orchestration stateboards, replace this file with one
  next objective, verify, commit, push, and continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add target-free research pipeline`
