# Codex Orchestration Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is a cross-lane projection, not a role lane, queue ledger, or second goal.

## Current Cross-Lane View

- Data has implemented and smoke-tested the KIS Paper single-client,
  concurrency-one session-capture worker. Its capture-scoped QQQ coverage is
  zero of 390 regular-session minutes because the measured terminal page is
  extended-session evidence; that is correctly excluded from Research. The
  existing intraday-head collector remains a source-local current sampler, not
  a company-wide dependency.
- Engine Research completed its frozen daily CPU baseline and one intraday CUDA
  replication. Neither selected a model; its next campaign depends on newly
  qualified Data coverage rather than a GPU occupancy target.
- Execution completed the deterministic target-weight-to-local-paper-intent
  binding without changing local/KIS/live route isolation.
- The only shared resources are KIS Paper market-data throughput and one GPU.
  Data owns the first; Research owns the second. There is no current storage
  conflict.

## Current Bottleneck

The material unknown is continuous, source-qualified KIS 1m session coverage.
The capture worker now proves a recoverable current-head attempt and detects
non-regular-session evidence, but it does not prove historical pagination or a
complete regular session.

## Current Operating Improvement

Integrate the tested capture mode into the existing head task without creating
a new scheduler or widening its KIS route. Keep prospective readiness local to
its consumer; a worker owns its own backoff and recovery, and Codex does not
sleep while another lane is ready.

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

Integrate the tested Data capture worker with the existing head task. Record
only an actual shared resource conflict, new external wait, bottleneck, or
reversible operating improvement here.
