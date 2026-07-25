# Engine Research Agent Stateboard

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current Research projection, not a campaign ledger. Historical
claims, results, and artifacts remain in Git and
`D:\thericher-v2\model-artifacts`.

## Ownership

Own hypotheses, features, model campaigns, analytical backtests, walk-forward
evaluation, and model-side PnL attribution. Never modify broker submission or
deterministic execution-risk behavior.

## Current Objective

Remain input-pending until Data supplies a verified prospective QQQ first-five
preparation pair. The current objective prohibits model/GPU jobs, candidate
selection, ensembles, Paper intents, and broker actions before that pair exists.

## Current Readiness

- The prospective head index has `0 / 5` exact regular sessions. Its preparation
  state is `pending_complete_sessions`; no real pair, candidate, or prospective
  observation receipt exists.
- The latest Data recovery hardening and data-scheduler missed-run recovery
  only improve collection availability; they do not create a pair or change
  Research eligibility.
- The credential-free offline consumer is implemented and synthetically
  verified. It validates the frozen pair's first-five QQQ dates and selected
  row fingerprints before and after local cache inputs, retaining the full
  head-index hash as preparation-time provenance, then emits only sanitized
  `source: local_paper` evidence.
- No GPU work is running. One GPU job may run only after a frozen campaign
  contract exists; utilization is not a reason to start an ineligible job.
- Earlier daily and short historical screens are closed plumbing evidence only.
  They created no selected model, ensemble, promotion, or Paper input. The
  Norgate trial remains development-only and cannot become a model/Paper lane.

## Frozen Prospective Contract

- Input: KIS-only QQQ data with completed `90 x 1m`, `18 x 5m`, and
  `9 x 10m` context from the same cache. Keep 1h and 3h inactive until their
  required contiguous coverage and timestamp semantics are qualified.
- Timing: decide at a completed 1m close, enter at the next 1m open, and exit at
  the following 1m open. No target may cross a declared session boundary.
- Validation: train only on the frozen development prefix, use the declared
  cost model and fixed local-paper controls, and keep any holdout sealed.
- Outputs: a learned node proposes target state and timestamped evidence, never
  a broker request. No result selects, retunes, promotes, or ensembles a model
  without a separate eligible campaign contract and its required review.

## Ready Queue

1. When Data supplies the first verified pair, run the existing credential-free
   offline prospective observation through its immutable input contract and
   inspect its categorical local-paper receipt.
2. Only after that receipt establishes a bounded claim, define a separate
   campaign contract before breadth, depth, ensemble, replication, or GPU work.
3. Consume only authoritative sanitized Execution lifecycle facts through opaque
   receipt identity. Until qualified completion evidence exists,
   `pnl_status: not_observed` and `performance_label = None` remain unchanged.

## Operator Help

None. Escalate only a paid or unclear-rights asset, a major runtime/framework
replacement, public exposure, or a live-money boundary.

## Durable Constraints

- Keep generated artifacts and checkpoints outside Git under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- A negative, unavailable, or abstaining result constrains only its claim. It
  cannot become a Data, Paper, scheduler, or operator permission latch.
- Preserve chronological session boundaries, source identity, leakage controls,
  and immutable campaign attempt identities. Do not reinterpret old metrics as
  a current signal.
- Reconstruct a prospective local-paper receipt only from canonical current
  schema events that exactly match its frozen decision/fill plan. Extra,
  malformed, unplanned, or non-local-paper events fail the receipt rather than
  being normalized into a result.

## Recovery

Current class: `resume`. A missing, changed, or tampered preparation pair is
`input_unavailable` or `restart`, never a partial model result. There is no
active campaign checkpoint to recover. A future interrupted campaign must use a
new immutable attempt path and never overwrite a completed receipt.

## Evidence

- `scripts\run_kis_intraday_prospective_observation.py` is the local-only
  consumer for a verified pair.
- The `research` Docker profile is network-disabled for that consumer and uses
  only the external market-data and artifact mounts.

## Next Handoff

Wait for the Data-owned pair without foreground polling. At readiness, verify
the pair's exact identity, run the existing offline consumer, and keep its
result separate from selection, promotion, execution, and Paper authority.
