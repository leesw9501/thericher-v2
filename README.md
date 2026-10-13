# TheRicher v2

TheRicher v2 is an engine-first automated trading workstation for a single
Korea-based operator using the Korea Investment Securities API.

The goal is not to rebuild the v1 report and gate system. The goal is to
research chart-driven short-term strategies, validate them with realistic
backtests and paper trading, then promote only proven engines to tightly capped
live trading.

## Product Goal

Build a local workstation that can:

- collect and cache intraday bars for US and Korean stocks,
- generate features across multiple timeframes,
- test rule, statistical, machine-learning, and deep-learning models,
- combine model outputs into auditable trading decisions,
- run KIS paper trading loops with clear position and order state,
- expose a small authenticated dashboard for monitoring and emergency actions,
- promote to live trading only after strict paper and risk criteria are met.

## Non-Goals

- No large readiness/report/gate sprawl.
- No LLM in the real-time order decision path.
- No public unauthenticated dashboard.
- No live trading enabled by default.
- No generated evidence artifacts unless they directly support engine iteration,
  daily review, or operator safety.

## First Operating Rule

Every new feature must answer one question:

> Does this make the strategy engine easier to test, improve, paper trade, or
> safely promote?

If the answer is no, it does not belong in v2.

## Development Commands

Preferred local workflow:

```powershell
uv run --no-env-file --extra dev pytest -q <changed test paths>
uv run --no-env-file --extra dev ruff check .
```

For faster repeat feedback on Windows, use the bounded parallel helper:

```powershell
.\scripts\run_parallel_tests.ps1
```

It uses up to eight workers with isolated short temp paths and no implicit
credential loading. Follow AGENTS.md for verification: focused feedback first;
changed tracked code/runtime needs changed-path serial plus clean-root full
parallel authority. Documentation/external-only work may reattach exact
unchanged passing authority with fresh checks of its actual changed surface.
Full serial pytest remains a weekly/material-recovery diagnostic.

Fallback when using an existing Python environment:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

The base runtime pins its market-calendar dependency. Heavy research libraries
belong behind the `research` extra and Docker Compose profile. KIS Paper uses
the approved shared initial10-percent virtual-cash allocation independently of
model profitability; live authority remains unavailable. Current roles and
their scopes are listed in agents/README.md.
