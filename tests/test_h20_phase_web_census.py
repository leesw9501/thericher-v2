import json
from functools import partial
from hashlib import sha256
from types import SimpleNamespace

import pytest

from thericher_v2.ops import h20_phase_web_census as census


@pytest.fixture
def prepared():
    if not census._ADOPTION.is_file():
        pytest.skip("pinned H20 monitor metadata release not retained on this host")
    base = json.loads((census._MONITOR / "h20/reader/BINDING.json").read_bytes())
    headroom = json.loads((census._MONITOR / "h20/reader/HEADROOM-SOURCE.json").read_bytes())
    claims = json.loads((census._MONITOR / "H20-READER-CLAIMS.json").read_bytes())
    descriptor = json.loads((census._MONITOR / "WEB-DESCRIPTOR.json").read_bytes())

    def hash_path(p):
        return sha256(str(p).replace("\\", "/").casefold().rstrip("/").encode()).hexdigest()

    headroom["financial_entry_hashes"] = {
        hash_path(p) for p in (*base["financial_entry_paths"], census._WRITER)
    }
    result = []
    namespace = dict(
        SOURCE=headroom,
        SCOPED=SimpleNamespace(financial_entry_hash=hash_path),
        CLAIMS=claims,
        ADMISSION=SimpleNamespace(decide=lambda facts, *_: result.append(facts) or True),
        PROJECTOR=SimpleNamespace(template=lambda *_: '{"base":true}'),
        call=lambda *_: pytest.fail("source binding is inert"),
    )
    return base, SimpleNamespace(namespace=namespace, fresh=lambda **_: True), result, descriptor


def test_retained_wrappers_preserve_non_web_behavior(prepared):
    binding, configured, result, _ = prepared
    census.bind_h20_web_census(configured, binding)
    ns = configured.namespace
    original = {"containers": [{"Image": "different"}]}
    assert ns["ADMISSION"].decide(original, {}, set()) is True
    assert result == [original]
    assert configured.fresh(phase="before_start") is True
    assert "ExactWebBootstrap" in ns["PROJECTOR"].template([])
    assert "KIS_" not in ns["PROJECTOR"].template([])


@pytest.mark.parametrize("fault", [None, "mount", "bootstrap", "alias"])
def test_monitor_checks_use_bounded_metadata_callback(tmp_path, prepared, fault):
    binding, configured, result, desc = prepared
    census.bind_h20_web_census(configured, binding)
    ns = configured.namespace
    admission = ns["ADMISSION"]
    admission.physical = partial(admission.physical, public=tmp_path)
    observed = []
    volumes = ("thericher-v2_thericher-v2-runtime", "thericher-v2_thericher-v2-web-emergency")
    rows = [
        dict(
            Name=name,
            Driver="local",
            Scope="local",
            OptionsEmpty=fault != "alias",
            Mountpoint=f"/var/lib/docker/volumes/{name}/_data",
        )
        for name in volumes
    ]

    def metadata(argv, timeout):
        observed.append((argv, timeout))
        return b"\n".join(json.dumps(row).encode() for row in rows)

    ns["call"] = metadata
    facts = {
        "containers": [
            {
                "Image": desc["image"],
                "ExactWebBootstrap": fault != "bootstrap",
                "Mounts": [
                    dict(
                        Destination="/app/runtime",
                        Type="volume",
                        Name=volumes[0],
                        RW=fault == "mount",
                    ),
                    dict(Destination="/app/emergency", Type="volume", Name=volumes[1], RW=True),
                    dict(
                        Destination="/app/operations", Type="bind", Source=str(tmp_path), RW=False
                    ),
                ],
            }
        ]
    }
    if fault:
        with pytest.raises(ValueError):
            admission.decide(facts, {}, set())
        assert not result
    else:
        assert admission.decide(facts, {}, set()) is True
        assert result == [facts] and len(observed) == 2
    assert all(timeout == 8 and argv[-2:] == list(volumes) for argv, timeout in observed)


@pytest.mark.parametrize("fault", ["claim", "writer"])
def test_wrong_claims_or_missing_repaired_writer_refuses(prepared, fault):
    binding, configured, _, _ = prepared
    source = configured.namespace["SOURCE"]
    if fault == "claim":
        source["claims_sha256"] = "a" * 64
    else:
        source["financial_entry_hashes"].remove(census._WRITER_PATH_PIN)
    with pytest.raises(ValueError):
        census.bind_h20_web_census(configured, binding)


def test_fresh_census_withholds_if_overlay_bytes_change_mid_sample(monkeypatch, prepared):
    binding, configured, _, _ = prepared
    source_read = census._read
    changed = False

    def read(path):
        raw, stamp = source_read(path)
        if changed and path == census._ADOPTION:
            raw += b"changed"
        return raw, stamp

    def sample(**kwargs):
        nonlocal changed
        assert kwargs["phase"] == "after_read"
        changed = True
        return True

    monkeypatch.setattr(census, "_read", read)
    configured.fresh = sample
    census.bind_h20_web_census(configured, binding)
    with pytest.raises(ValueError):
        configured.fresh(phase="after_read")
