# Codex Orchestration Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is a cross-lane projection, not a role lane, queue ledger, or second goal.

## Current Cross-Lane View

- Data has implemented, smoke-tested, and integrated the KIS Paper
  single-client, concurrency-one session-capture worker with the one existing
  intraday-head task. Its capture-scoped QQQ coverage is zero of 390
  regular-session minutes because the measured terminal page is extended-session
  evidence; that is correctly excluded from Research. The scheduled task's
  future result is Data-local evidence, not a company-wide dependency.
- Engine Research completed its frozen daily CPU baseline and one intraday CUDA
  replication. Neither selected a model. Its next bounded campaign can use the
  qualified daily QQQ/SPY catalog without waiting for newly captured intraday
  coverage.
- Execution completed the deterministic target-weight-to-local-paper-intent
  binding without changing local/KIS/live route isolation.
- The only shared resources are KIS Paper market-data throughput and one GPU.
  Data owns the first; Research owns the second. There is no current storage
  conflict.

## Current Bottleneck

The material unknown is continuous, source-qualified KIS 1m session coverage,
while the next material model unknown is whether compact daily sequence families
falsify or improve on the already negative naive KIS-daily evidence. The
capture worker does not prove historical pagination or a complete regular
session.

## Current Operating Improvement

Use the qualified daily KIS catalog for a bounded Research screen while the
existing intraday task accumulates its own coverage. Keep prospective readiness
local to its consumer; a worker owns its own backoff and recovery, and Codex
does not sleep while another lane is ready. At task resume or an observed
unexplained foreground idle period, invoke one bounded Throughput Review from
the existing stateboards and active-job facts; retain only one measured,
reversible improvement here rather than creating a standing process lane.

## External Waits

- The scheduled intraday head has a due time, but it does not hold the capture
  worker implementation, historical evidence preservation, or Execution.
- Claude CLI OAuth is expired. Retry it at the next material decision boundary;
  do not block ordinary private work.

## Recovery

Current class: resume. Reattest an individual cache, campaign, or exact Paper
intent before relying on it. Scope failure to that item and continue independent
lanes.

## Next Handoff

Build the KIS-native daily sequence breadth screen. Record only an actual
shared resource conflict, new external wait, bottleneck, or reversible
operating improvement here.
