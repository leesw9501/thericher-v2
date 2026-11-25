"""Source-bound exception for the local monitor's non-financial controls."""

import json
import re
from dataclasses import dataclass

from thericher_v2.execution import paper_peer_visit as pv

CONTROL = "thericher-v2_thericher-v2-web-emergency"
RUNTIME = "thericher-v2_thericher-v2-runtime"
CONTROL_TARGET = "/app/emergency"
BANK_TARGET = "/app/private"
OPERATIONS = "D:/thericher-v2/model-artifacts/monitor/paper-operations"
RULE = "dec4-local-monitor-control-only-v1"
VOLUME_FORMAT = (
    '{"name":{{json .Name}},"local":'
    '{{if and (eq .Driver "local") (eq .Scope "local") (not .Options)}}true'
    '{{else}}false{{end}},"mountpoint":{{json .Mountpoint}},'
    '"created":{{json .CreatedAt}}}'
)
_ENV = {
    "PYTHONPATH",
    "THERICHER_DASHBOARD_TOKEN",
    "THERICHER_MODE",
    "THERICHER_OPERATIONS_ROOT",
    "PATH",
    "LANG",
    "GPG_KEY",
    "PYTHON_VERSION",
    "PYTHON_SHA256",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
}
_ARGS = (
    "-m",
    "thericher_v2.dashboard.server",
    "--host",
    "0.0.0.0",
    "--allow-container-bind",
    "--port",
    "8787",
    "--emergency-state",
    "/app/emergency/emergency_state.json",
    "--execution-control",
    "/app/emergency/paper_execution_control.json",
    "--paper-account-snapshot",
    "/app/runtime/state/paper_account_snapshot.json",
    "--paper-canary-runtime",
    "/app/runtime/state/kis_paper_canary.json",
    "--market-data-freshness",
    "/app/runtime/state/kis_paper_intraday_freshness.json",
    "--qqq-gross-receipt",
    "/app/receipts/qqq-gross-roundtrip.json",
    "--qqq-gross-receipt-sha256",
    "c2fbf15660751ae50c23a6e81b5c2d62f7a55b581504d9157c0c613112adf45f",
)
_BINDS = [f"{RUNTIME}:/app/runtime:ro", f"{CONTROL}:/app/emergency:rw"]
_HOST_MOUNT = {
    "Type": "bind",
    "Source": OPERATIONS,
    "Target": "/app/operations",
    "ReadOnly": True,
    "BindOptions": {},
}


def _q(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class Dec4MonitorMount:
    # The profile author must verify this local image's exact monitor source;
    # a Compose label, image tag, or image discovery is not that attestation.
    image: str
    bank_volume: str

    def __post_init__(self):
        if type(self.image) is not str or not re.fullmatch(r"sha256:[a-f0-9]{64}", self.image):
            raise ValueError("h3_monitor_image")
        if (
            type(self.bank_volume) is not str
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{1,254}", self.bank_volume)
            or self.bank_volume.casefold() in {CONTROL, RUNTIME}
        ):
            raise ValueError("h3_monitor_bank_alias")

    @property
    def sha256(self):
        return pv.digest({"schema": RULE, "image": self.image, "bank_volume": self.bank_volume})

    def rule(self):
        return {
            "rule_id": RULE,
            "image": self.image,
            "path": "python",
            "args": _ARGS,
            "network_name": "thericher-v2_default",
            "ports": {"8787/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8787"}]},
        }

    @staticmethod
    def constraint():
        # Compare values in Docker and project a boolean, not any environment values.
        bind_orders = [
            f"(eq (json .HostConfig.Binds) {_q(_q(order))})" for order in (_BINDS, _BINDS[::-1])
        ]
        host_mount = _q(_q([dict(sorted(_HOST_MOUNT.items()))]))
        return (
            '(eq (index .Config "WorkingDir") "/app") '
            '(not (index .Config "User")) (not (index .Config "Healthcheck")) '
            '(eq (index .HostConfig "IpcMode") "private") '
            '(not (index .HostConfig "Tmpfs")) '
            '(not (index .HostConfig "Links")) '
            f"(or {' '.join(bind_orders)}) "
            f'(eq (json (index .HostConfig "Mounts")) {host_mount}) '
            "(eq (len .NetworkSettings.Networks) 1) "
            '(index .NetworkSettings.Networks "thericher-v2_default") '
            "$monitorEnv"
        )

    def template(self, project, rules):
        if any(rule["rule_id"] == RULE for rule in rules):
            raise ValueError("h3_monitor_rule_collision")
        template = project.template([*rules, self.rule()])
        env = (
            "{{$mode := false}}{{$ops := false}}{{$python := false}}{{$path := false}}"
            "{{range .Config.Env}}"
            '{{if eq . "THERICHER_MODE=off"}}{{$mode = true}}{{end}}'
            '{{if eq . "THERICHER_OPERATIONS_ROOT=/app/operations"}}{{$ops = true}}{{end}}'
            '{{if eq . "PYTHONPATH=/app/src"}}{{$python = true}}{{end}}'
            '{{if eq . "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:'
            '/usr/sbin:/usr/bin:/sbin:/bin"}}'
            "{{$path = true}}{{end}}{{end}}{{$monitorEnv := and $mode $ops $python $path}}"
        )
        marker = "}}" + _q(RULE) + "{{else}}null{{end}}"
        if template.count(marker) != 1:
            raise ValueError("h3_monitor_projector")
        condition = project.rule_condition(self.rule())[1]
        exact = "{{if " + condition + marker
        if template.count(exact) != 1:
            raise ValueError("h3_monitor_projector")
        return template.replace(
            exact, env + "{{if and " + condition + " " + self.constraint() + marker
        )

    def row_matches(self, row, *, mapped_operations):
        config = row["HostConfig"]
        env = row["EnvNames"]
        mounts = {
            (m["Type"], m["Name"], m["Source"], m["Destination"], m["RW"]) for m in row["Mounts"]
        }
        return (
            row["Running"] is True
            and row["Image"] == self.image
            and RULE in row["RuleMatches"]
            and len(env) == len(_ENV)
            and set(env) == _ENV
            and len(mounts) == len(row["Mounts"]) == 3
            and mounts
            == {
                ("volume", CONTROL, "", "/app/emergency", True),
                ("volume", RUNTIME, "", "/app/runtime", False),
                ("bind", "", mapped_operations, "/app/operations", False),
            }
            and config["IpcPrivate"] is True
            and all(
                config[k] is False
                for k in ("Privileged", "VolumesFrom", "Devices", "PidMode", "SecurityOptExtra")
            )
            and not config["CapAdd"]
            and not config["DeviceRequests"]
        )


def validate_control_volume(row, name):
    if (
        type(row) is not dict
        or set(row) != {"name", "local", "mountpoint", "created"}
        or row["name"] != name
        or row["local"] is not True
        or row["mountpoint"] != f"/var/lib/docker/volumes/{name}/_data"
        or type(row["created"]) is not str
        or not row["created"]
    ):
        raise ValueError("h3_monitor_volume_unbound")
    return row


def validate_worker_control_mount(mounts, bank_volume):
    if bank_volume.casefold() in {CONTROL, RUNTIME}:
        raise ValueError("h3_monitor_bank_alias")
    for source, target in ((CONTROL, CONTROL_TARGET), (bank_volume, BANK_TARGET)):
        related = [
            row
            for row in mounts
            if row["source"].casefold() == source.casefold()
            or row["target"] == target
            or row["target"].startswith(target + "/")
            or target.startswith(row["target"].rstrip("/") + "/")
        ]
        if (
            related != [{"type": "volume", "source": source, "target": target, "rw": True}]
            or related[0]["rw"] is not True
        ):
            raise ValueError("h3_monitor_worker_control_mount")
