"""
Registry-level readiness contract for capability packs (H1.6, G20).

`production_readiness` is a governance claim, not a per-pack convention: a pack
that silently omits it would ship without a declared boundary. These tests
enumerate every registered pack through the registration mechanism (each
`capabilities/<pack>/register.py::REGISTRY`, populated on import) rather than
a hardcoded list, then assert the claim exists and carries an allowed value.

The audit-integrity half of H1.6 lives in release/gate.py: the release gate
verifies a shipped audit chain whenever one is declared via
HELIX_AUDIT_DB_PATH, and fails closed when the declared chain is broken or
missing (see test_c8_release_gate.py).
"""
from __future__ import annotations

import importlib.util
import pkgutil

import pytest

ALLOWED_PRODUCTION_READINESS = {"NOT_ESTABLISHED"}


def _registered_packs():
    packs = []
    import capabilities

    for mod_info in pkgutil.iter_modules(capabilities.__path__):
        if not mod_info.ispkg:
            continue
        module_name = f"capabilities.{mod_info.name}.register"
        if importlib.util.find_spec(module_name) is None:
            continue
        register = importlib.import_module(module_name)
        registry = getattr(register, "REGISTRY", None)
        if registry is None:
            raise ValueError(f"{module_name} exists but exposes no REGISTRY")
        for name, metadata in registry.items():
            packs.append((name, metadata))
    packs.sort(key=lambda item: item[0])
    return packs


def test_pack_discovery_finds_registered_packs():
    packs = _registered_packs()
    assert packs, "no capability packs registered — discovery is broken"
    names = [name for name, _metadata in packs]
    assert "restaurant_operations" in names
    assert "sports_academy_operations" in names


def test_every_registered_pack_declares_allowed_production_readiness():
    packs = _registered_packs()
    assert packs, "no capability packs registered — readiness contract cannot be checked"
    violations = []
    for name, metadata in packs:
        if not isinstance(metadata, dict) or "production_readiness" not in metadata:
            violations.append(f"{name}: production_readiness not declared")
        elif metadata["production_readiness"] not in ALLOWED_PRODUCTION_READINESS:
            violations.append(
                f"{name}: production_readiness {metadata['production_readiness']!r} "
                f"not in allowed set {sorted(ALLOWED_PRODUCTION_READINESS)}"
            )
    assert not violations, "readiness contract violations: " + "; ".join(violations)


@pytest.mark.parametrize(
    "pack_name,metadata",
    _registered_packs(),
    ids=[name for name, _metadata in _registered_packs()],
)
def test_registered_pack_metadata_declares_readiness(pack_name, metadata):
    assert isinstance(metadata, dict)
    assert "production_readiness" in metadata, (
        f"pack {pack_name!r} must declare production_readiness"
    )
    assert metadata["production_readiness"] in ALLOWED_PRODUCTION_READINESS, (
        f"pack {pack_name!r} production_readiness {metadata['production_readiness']!r} "
        f"not in allowed set {sorted(ALLOWED_PRODUCTION_READINESS)}"
    )
