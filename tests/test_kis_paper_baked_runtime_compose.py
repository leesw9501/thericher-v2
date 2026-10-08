import hashlib
import re
from pathlib import Path

import pytest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
IMAGE = "sha256:ae2c68f8ae0ea37290b18b17b9b814e130f2b1b9b1aed506be39942b82f64505"
PRIVATE_MOUNT = "thericher-v2-paper-canary-private:/app/private"

# Goal 19 pre-edit settings, excluding only the three-line base build stanza.
CONSUMERS = {
    "kis-paper-canary": (
        "kis-paper-canary",
        False,
        "846678d6bc0154bfbdc8fea6de53d255991eab73888d5f2a4562cafb4f342286",
    ),
    "kis-paper-session": (
        "kis-paper-session",
        False,
        "12204f4dc72af72b1d4271c7a64fe296437f7cb85bb116efc81ff113ad7a9a76",
    ),
    "kis-paper-daily-spy-session": (
        "kis-paper-daily-spy-session",
        False,
        "d06a4253db6f3a2aec92c1ca13a196408350aebb4a8ee1154280ad1323d8f24c",
    ),
    "kis-paper-prospective-spy-cycle": (
        "kis-paper-intraday-head",
        False,
        "15706e5bd60cbaf56a73483f2b51c39b011c25f7e006dd63f1150c7bdb3082c1",
    ),
    "kis-paper-prospective-qqq-session": (
        "kis-paper-intraday-head",
        False,
        "76756e13da9668ea407e56c3fcef9722f6792fa571cb42baea093879830e4dc7",
    ),
    "kis-paper-receipt-observer": (
        "kis-paper-receipt-observer",
        True,
        "a41de251d4d0a50174db86a0862c630b94144fc53569510f1e98d627d8448bd1",
    ),
    "kis-paper-terminal-field-probe": (
        "kis-paper-terminal-field-probe",
        True,
        "f4beb05bbf1855163612336206a615394e18437350d428f387d890d10f7aed56",
    ),
}
ENVIRONMENT = """    environment:
      THERICHER_MODE: kis_paper
      THERICHER_MODEL_ARTIFACT_ROOT: /app/model_artifacts
      KIS_PAPER_APP_KEY: ${KIS_PAPER_APP_KEY:-}
      KIS_PAPER_APP_SECRET: ${KIS_PAPER_APP_SECRET:-}
      KIS_PAPER_ACCOUNT_NO: ${KIS_PAPER_ACCOUNT_NO:-}
      KIS_PAPER_ACCOUNT_PRODUCT_CODE: ${KIS_PAPER_ACCOUNT_PRODUCT_CODE:-}
"""


def _service_blocks(source: str) -> dict[str, str]:
    services = source.split("\nvolumes:\n", maxsplit=1)[0]
    return dict(
        re.findall(
            r"(?ms)^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
            services,
        )
    )


@pytest.mark.parametrize("service", CONSUMERS)
def test_private_consumer_pins_baked_code_and_preserves_entire_operational_contract(service):
    block = _service_blocks(COMPOSE.read_text(encoding="utf-8"))[service]
    profile, read_only, baseline_sha256 = CONSUMERS[service]
    assert re.findall(r"(?m)^    image: (.+)$", block) == [IMAGE]
    assert re.findall(r"(?m)^    pull_policy: (.+)$", block) == ["never"]
    assert not re.search(r"(?m)^    build:", block)
    assert f'    profiles: ["{profile}"]\n' in block
    assert ENVIRONMENT in block
    mounts = [line.strip() for line in block.splitlines() if ":/app/private" in line]
    assert mounts == [f"- {PRIVATE_MOUNT}" + (":ro" if read_only else "")]

    operational = re.sub(r"(?m)^    (?:image|pull_policy):[^\n]*\n", "", block)
    operational = operational.rstrip("\n") + "\n"
    assert hashlib.sha256(operational.encode("utf-8")).hexdigest() == baseline_sha256


def test_only_the_seven_private_consumers_select_the_baked_image():
    source = COMPOSE.read_text(encoding="utf-8")
    blocks = _service_blocks(source)
    private_consumers = {service for service, block in blocks.items() if PRIVATE_MOUNT in block}
    baked_consumers = {service for service, block in blocks.items() if f"image: {IMAGE}" in block}
    assert private_consumers == baked_consumers == set(CONSUMERS)
    assert sum(block.count(f"- {PRIVATE_MOUNT}\n") for block in blocks.values()) == 5
    assert sum(block.count(f"- {PRIVATE_MOUNT}:ro\n") for block in blocks.values()) == 2
    declarations = source.split("\nvolumes:\n", maxsplit=1)[1]
    assert (
        "  thericher-v2-paper-canary-private:\n"
        "    name: thericher-v2-paper-canary-private-acct-20261007-v1\n"
    ) in declarations
