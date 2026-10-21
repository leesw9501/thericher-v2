# Agent Stateboards

AGENTS.md owns policy; NEXT_CODEX_GOAL.md owns ONE company objective.
Operator -> Codex Orchestrator -> role agents. A stateboard is durable memory,
not proof of a permanently running LLM. Codex dispatches bounded subagents or
workers, integrates their evidence and owns Git.

## Team Directory

Canonical English identifiers remain code/path keys; Korean names are display aliases.

| Korean name | Canonical role | Stateboard | Responsibility |
| --- | --- | --- | --- |
| 제품개발 총괄 / 총괄 | Codex Orchestrator | orchestration.md | Direction, parallel dispatch, integration, recovery and Git. |
| 시장데이터 담당 / 데이터 | Data Agent | data.md | Useful acquisition, canonical bars, availability and quality facts. |
| 전략·지표 연구 담당 / 전략 | Strategy Research Agent | strategy-research.md | Official-source mechanisms, causal features and executable proposals. |
| 매매 엔진 연구 담당 / 엔진 | Engine Research Agent | engine-research.md | Targets, models, training, replay, OOF fusion and interpretation. |
| 연구 자원·평가 관리자 / GPU·평가 | Research Steward Agent | research-steward.md | Coordinated GPU resources/concurrent ready jobs and existing trial/holdout custody. |
| 모의투자 실행 담당 / 실행 | Execution Agent | execution.md | Paper account/orders, deterministic risk, reconciliation and accounting. |

Independent Validation (독립 검증), Infra (기술 환경), Claude/Review (반증 검토)
and Throughput Review (진행 효율 점검) are invoked capabilities, not new permanent
queues. Strategy Discovery reports through Strategy Research. Cross-Track
Synthesis is an independent bounded review, not a prerequisite for exploratory
joint training. Historical infra.md/review.md stay retired.

## Parallel Work And Authority

Disjoint Data, Strategy, Engine and Execution packages run in parallel.
One owner per mutable write set; one GPU resource coordinator may co-run ready
frozen jobs with measured headroom; account/cursor gates remain shared.
Project GPU priority/concurrency is explicitly approved even during personal
GPU use. Steward is a resource owner, not a human approval. A package's research-
only restriction never disables another lane's standing KIS Paper authority.
Preserve the shared initial virtual-cash 10-percent basis and exact unknown
request recovery. Paper does not wait for a profitable model.

Codex checks ready/owned/due at resume, handoff, failure and long dispatch.
External cooldowns belong to the worker. Unavailable Claude is scoped evidence,
not company idle. Do not create per-agent next-goal files or an agent platform.

## Memory And Reports

Each board retains current owner/resource, ready/running work, useful knowledge,
exact evidence, recovery and next action. Replace superseded projections.
Git and immutable external artifacts retain searchable history and original
evidence; do not duplicate them as diaries or per-agent databases. The existing
shared ledger/custody is reused when applicable.

On "에이전트별 활동사항 보고해", report the requested period (default 72 hours):
evidenced progress, current difficulty, useful resolved cause/repair and next
action or owned wait. Distinguish source readiness, actual runs, accepted orders,
fills and measured net PnL. A chat is delivery, not the source of truth.

## Verification And Lifecycle

Focused isolated tests first. Fresh full authority is required for tracked
code/test/dependency/runtime or material execution-recovery changes. Docs and
external-only packages may reuse exact unchanged authority as AGENTS.md specifies.
Do not repeat the full suite for formatting or merely replacing a goal.

Activate a durable role for distinct recurring work/resource ownership; put
empty/duplicate roles on standby or retire them while preserving history.
Strategy Research is active because repeated operator requests and consumed
feature/source work justify a dedicated, small executable research intake.
No role gets its own approval chain, public endpoint or permanent LLM daemon.
