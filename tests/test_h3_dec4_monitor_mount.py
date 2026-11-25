import copy
from types import SimpleNamespace

import pytest

from thericher_v2.ops import h3_dec4_monitor_mount as monitor
from thericher_v2.ops import h3_dec4_paper_launcher as launcher
from thericher_v2.ops import h3_dec4_writer_census as census


@pytest.fixture
def role():
    return monitor.Dec4MonitorMount("sha256:" + "a" * 64, "private-bank")


@pytest.fixture
def web(role):
    return {
        "Id": "a" * 64,
        "Running": True,
        "Image": role.image,
        "RuleMatches": [monitor.RULE],
        "EnvNames": sorted(monitor._ENV),
        "HostConfig": {
            "IpcPrivate": True,
            "Privileged": False,
            "VolumesFrom": False,
            "Devices": False,
            "PidMode": False,
            "SecurityOptExtra": False,
            "CapAdd": None,
            "DeviceRequests": [],
        },
        "Mounts": [
            dict(Type=k, Name=n, Source=s, Destination=d, RW=w)
            for k, n, s, d, w in (
                ("volume", monitor.CONTROL, "", "/app/emergency", True),
                ("volume", monitor.RUNTIME, "", "/app/runtime", False),
                ("bind", "", monitor.OPERATIONS, "/app/operations", False),
            )
        ],
    }


def test_only_exact_single_dashboard_excluded_from_financial_classifier(monkeypatch, role, web):
    profile = SimpleNamespace(monitor=role)
    other = copy.deepcopy(web)
    other.update(Id="b" * 64, RuleMatches=[])
    facts = {"actors": ["retained"], "containers": [web, other]}
    monkeypatch.setattr(census, "_monitor_backing", lambda *_: ("backing",))
    scoped, backing = census._monitor_scope(facts, profile, None, None, ())
    # In particular, a different writer sharing the volume still faces old rules.
    assert scoped == {"actors": ["retained"], "containers": [other]}
    assert facts["containers"] == [web, other]
    assert backing == ("backing",)
    with pytest.raises(ValueError, match="monitor_owner"):
        census._monitor_scope(facts, profile, web["Id"], None, ())
    other["RuleMatches"] = [monitor.RULE]
    with pytest.raises(ValueError, match="monitor_owner"):
        census._monitor_scope(facts, profile, None, None, ())


@pytest.mark.parametrize("fault", ["broker_env", "same_bank", "runtime_rw", "ops_alias", "device"])
def test_monitor_with_different_authority_is_not_excluded(role, web, fault):
    if fault == "broker_env":
        web["EnvNames"].append("KIS_PAPER_APP_KEY")
    if fault == "same_bank":
        web["Mounts"][0]["Name"] = role.bank_volume
    if fault == "runtime_rw":
        web["Mounts"][1]["RW"] = True
    if fault == "ops_alias":
        web["Mounts"][2]["Source"] += "-other"
    if fault == "device":
        web["HostConfig"]["Devices"] = True
    with pytest.raises(ValueError, match="monitor_scope"):
        census._monitor_scope({"containers": [web]}, SimpleNamespace(monitor=role), None, None, ())


@pytest.mark.parametrize("fault", ["options", "driver_path", "birth", "different_name"])
def test_volume_requires_dedicated_default_local_storage(fault):
    name = monitor.CONTROL
    row = dict(
        name=name, local=True, mountpoint=f"/var/lib/docker/volumes/{name}/_data", created="utc"
    )
    assert monitor.validate_control_volume(row, name) is row
    key, value = {
        "options": ("local", False),
        "driver_path": ("mountpoint", "/private"),
        "birth": ("created", ""),
        "different_name": ("name", monitor.RUNTIME),
    }[fault]
    row[key] = value
    with pytest.raises(ValueError, match="monitor_volume_unbound"):
        monitor.validate_control_volume(row, name)


def test_launch_only_permits_exact_extra_control_volume_with_typed_profile(role):
    bank = {"volume": role.bank_volume}
    private = dict(type="volume", source=role.bank_volume, target="/app/private", rw=True)
    control = dict(type="volume", source=monitor.CONTROL, target="/app/emergency", rw=True)
    assert launcher._mounts([private, control], bank, monitor_control=True) == [private, control]
    with pytest.raises(ValueError, match="launcher_bank_volume"):
        launcher._mounts([private, control], bank)
    for invalid in (
        [control],
        [private, control | {"target": "/app/emergency/child"}],
        [private, control | {"rw": False}],
        [private | {"target": "/app"}, control],
        [private | {"target": "/app/runtime"}, control],
        [private, control, control | {"type": "bind", "target": "/app/private/canary"}],
        [private, control, control | {"target": "/tmp/elsewhere"}],
    ):
        with pytest.raises(ValueError):
            launcher._mounts(invalid, bank, monitor_control=True)
