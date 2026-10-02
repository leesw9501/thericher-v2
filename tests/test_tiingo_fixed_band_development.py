"""Synthetic fixed-band matrix, fee identities and no real data/runtime access."""

import copy
import runpy
import socket
import time
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow

S = runpy.run_path(str(Path(__file__).parents[1] / "scripts/run_tiingo_fixed_band_development.py"))


@pytest.fixture
def sample(monkeypatch):
    h = S["h"]

    def forbidden(*_args, **_kwargs):
        pytest.fail("real data, credentials or network forbidden")

    monkeypatch.setattr(h, "load_adjusted", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(
        h,
        "calibrate",
        lambda *_a, **_k: (Decimal(1), Decimal(".5"), {"calibration_sha256": "sha256:" + "1" * 64}),
    )
    monkeypatch.setattr(h, "gaps", lambda *_: (0, 0))
    monkeypatch.setattr(
        h, "targets", lambda _rows, _days, bounds, _ref: {i: Decimal(".5") for i in range(*bounds)}
    )
    days = [
        "2013-01-02",
        "2013-02-01",
        "2013-03-01",
        "2013-04-01",
        "2020-01-02",
        "2020-02-03",
        "2020-03-02",
        "2020-04-01",
    ]
    plan = {
        "days": days,
        "train": [0, 1],
        "periods": [
            {"period": h.PERIODS[0][0], "bounds": [0, 4]},
            {"period": h.PERIODS[1][0], "bounds": [4, 8]},
        ],
    }
    prices = ("1", "2", "4", "1") * 2
    rows = {
        s: tuple(
            AdjustedEtfRow(s, date.fromisoformat(d), *(Decimal(p),) * 4)
            for d, p in zip(days, prices, strict=True)
        )
        for s in h.SYMBOLS
    }
    return rows, plan


def evaluated(sample):
    return S["evaluate"](*sample, deadline=time.monotonic() + 30)


def test_matrix_continuous_carry_and_cash(sample):
    result = evaluated(sample)
    S["validate_cells"](result)
    assert len(result["cells"]) == 144 and len(result["calibrations"]) == 3
    band = [c for c in result["cells"] if c["policy"] == "vol_band"]
    assert all(c["trades"] == 4 for c in band)
    cash = [c for c in result["cells"] if c["policy"] == "cash"]
    assert all(c["final_nav"] == "1.000000000000" and c["trades"] == 0 for c in cash)


@pytest.mark.parametrize("mutation", ["fee", "matrix", "center", "nan", "cash"])
def test_result_mutations_rejected(sample, mutation):
    result = copy.deepcopy(evaluated(sample))
    if mutation == "fee":
        result["cells"][0]["fees_initial_nav"] = "1.000000000000"
    elif mutation == "matrix":
        result["cells"].reverse()
    elif mutation == "center":
        result["cells"][6]["center_sha256"] = "sha256:" + "2" * 64
    elif mutation == "nan":
        result["cells"][0]["final_nav"] = "NaN"
    else:
        result["cells"][5]["trades"] = 1
    with pytest.raises(ValueError):
        S["validate_cells"](result)


def test_paired_facts_do_not_select_a_model(sample):
    result = evaluated(sample)
    facts = S["paired_facts"](result)
    assert type(facts["kill_applied"]) is bool
    assert "selection" in facts["interpretation"]
    config = S["configuration"]()
    assert config["fits"] == 0 and not config["selection"] and not config["budget"]["gpu"]
    assert config["band"].startswith("fixed half-width0.1")


def test_pair_math_does_not_depend_on_ambient_decimal_precision(sample):
    result = evaluated(sample)
    expected = S["paired_facts"](result)
    with localcontext() as context:
        context.prec = 8
        S["validate_cells"](result)
        assert S["paired_facts"](result) == expected
        assert context.prec == 8


def test_deadline_and_missing_training_are_not_success(sample, monkeypatch):
    with pytest.raises(ValueError, match="hard_timeout"):
        S["evaluate"](*sample, deadline=0)
    monkeypatch.setattr(S["h"], "calibrate", lambda *_a, **_k: (None, None, {}))
    with pytest.raises(ValueError, match="TRAIN_input_unavailable"):
        evaluated(sample)


def test_repo_market_root_rejected_without_reading_data():
    with pytest.raises(ValueError, match="external_market_root"):
        S["check_market_root"](S["h"].REPO)


def test_fresh_freeze_creates_once_without_real_data(tmp_path, monkeypatch):
    h = S["h"]
    repo, market = tmp_path / "repo", tmp_path / "market"
    repo.mkdir()
    market.mkdir()
    (repo / "dummy.py").write_text("# synthetic metadata pin\n", encoding="ascii")
    monkeypatch.setattr(h, "REPO", repo)
    monkeypatch.setattr(h, "calendar_days", lambda: ["2001-01-02", "2013-01-02", "2020-01-02"])
    monkeypatch.setattr(h, "source_identity", lambda: {"source": "synthetic"})
    monkeypatch.setattr(h.base, "verify_metadata", lambda *_: None)
    registrations = []
    monkeypatch.setattr(h.base, "register_frozen_campaign", lambda **kw: registrations.append(kw))
    monkeypatch.setitem(S["freeze"].__globals__, "CODE", ("dummy.py",))
    artifacts = tmp_path / "artifacts"
    pin = S["freeze"](artifacts, market)
    root = S["output_root"](artifacts)
    assert pin == h.digest((root / "precommit.json").read_bytes())
    assert registrations[0]["holdout_access"] == "none"
    with pytest.raises(FileExistsError):
        S["freeze"](artifacts, market)


def test_verify_reports_the_same_bytes_it_validated(sample, monkeypatch, capsys, tmp_path):
    h = S["h"]
    result = evaluated(sample)
    result["contract_sha256"] = "sha256:" + "3" * 64
    result["paired"] = S["paired_facts"](result)
    raw = h.encode(result)
    pin = h.digest(raw)
    monkeypatch.setitem(S["main"].__globals__, "verify_contract", lambda *_: (tmp_path, {}))
    reads = []

    def read(_path):
        reads.append(_path)
        if len(reads) > 1:
            pytest.fail("verified bytes must not be replaced with a second read")
        return raw

    monkeypatch.setattr(h, "_read", read)
    assert (
        S["main"](
            [
                "verify",
                "--artifact-root",
                "D:/unused",
                "--market-data-root",
                "D:/unused",
                "--contract-hash",
                result["contract_sha256"],
                "--summary-hash",
                pin,
            ]
        )
        == 0
    )
    assert pin in capsys.readouterr().out and len(reads) == 1


def test_failure_output_masks_exception(monkeypatch, capsys):
    sentinel = "private-sentinel-not-for-output"

    def fail(*_args):
        raise ValueError(sentinel)

    monkeypatch.setitem(S["main"].__globals__, "freeze", fail)
    assert (
        S["main"](["freeze", "--artifact-root", "D:/unused", "--market-data-root", "D:/unused"])
        == 1
    )
    assert sentinel not in capsys.readouterr().out
