from __future__ import annotations

from pathlib import Path


def test_cross_sectional_momentum_cpu_service_is_credential_free_and_network_isolated() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    start = compose.index("  kis-broad-d1-cross-sectional-momentum:")
    end = compose.index("\n  chronos-t5-tiny-acquisition:", start)
    service = compose[start:end]

    assert 'profiles: ["kis-broad-d1-cross-sectional-momentum"]' in service
    assert "target: base" in service
    assert "network_mode: none" in service
    assert "read_only: true" in service
    assert "gpus:" not in service
    assert "KIS_PAPER_" not in service
    assert "KIS_LIVE_" not in service
    assert "THERICHER_MODE: off" in service
    assert "scripts/run_kis_broad_d1_cross_sectional_momentum.py" in service
    assert "--cache-root" in service
    assert "/app/market_data/us_equities/kis_paper_private/daily-nas-broad/v1" in service
    assert "--panel-root" in service
    assert "/app/market_data/us_equities/kis_paper_private/daily-nas-broad-panel/v1" in service
    assert "--artifact-root" in service
    assert "/app/model_artifacts" in service
    assert "/app/market_data:ro" in service
    assert "/app/model_artifacts" in service
