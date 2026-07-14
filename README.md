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
uv run --extra dev pytest -q
uv run --extra dev ruff check .
```

Fallback when using an existing Python environment:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

The base engine has no runtime third-party dependencies. Heavy research
libraries belong behind the `research` extra and Docker Compose profile.
