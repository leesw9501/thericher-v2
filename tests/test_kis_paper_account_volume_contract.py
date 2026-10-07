import re
from pathlib import Path

import pytest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
PRIVATE_VOLUME = "thericher-v2-paper-canary-private"
CURRENT_PRIVATE_NAME = "thericher-v2-paper-canary-private-acct-20261007-v1"
CONSUMERS = {
    "kis-paper-canary": False,
    "kis-paper-session": False,
    "kis-paper-daily-spy-session": False,
    "kis-paper-prospective-spy-cycle": False,
    "kis-paper-prospective-qqq-session": False,
    "kis-paper-receipt-observer": True,
    "kis-paper-terminal-field-probe": True,
}


def test_new_account_uses_one_explicit_physical_volume_without_old_adoption():
    source = COMPOSE.read_text(encoding="utf-8")
    declarations = source.split("\nvolumes:\n", maxsplit=1)[1]
    assert f"  {PRIVATE_VOLUME}:\n    name: {CURRENT_PRIVATE_NAME}\n" in declarations
    assert "thericher-v2_thericher-v2-paper-canary-private" not in declarations
    assert source.count(f"{PRIVATE_VOLUME}:/app/private") == len(CONSUMERS)


@pytest.mark.parametrize("service,read_only", CONSUMERS.items())
def test_all_existing_private_consumers_share_custody_and_preserve_mount_access(service, read_only):
    source = COMPOSE.read_text(encoding="utf-8")
    section = re.split(
        r"\n  [a-z][a-z0-9-]*:\n", source.split(f"\n  {service}:\n", maxsplit=1)[1], maxsplit=1
    )[0]
    mounts = [line.strip() for line in section.splitlines() if ":/app/private" in line]
    expected = f"- {PRIVATE_VOLUME}:/app/private" + (":ro" if read_only else "")
    assert mounts == [expected]
    assert CURRENT_PRIVATE_NAME not in section


@pytest.mark.parametrize("service", ["web", "kis-readonly"])
def test_dashboard_and_snapshot_bridge_do_not_receive_private_order_state(service):
    source = COMPOSE.read_text(encoding="utf-8")
    section = re.split(
        r"\n  [a-z][a-z0-9-]*:\n", source.split(f"\n  {service}:\n", maxsplit=1)[1], maxsplit=1
    )[0]
    assert ":/app/private" not in section
