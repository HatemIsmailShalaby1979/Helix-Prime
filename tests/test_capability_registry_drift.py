"""Drift detection for capability registry mirrors — C1a preflight correction.

Canonical: organization/capability-registry.yaml
Mirrors must be generated/validated, not hand-edited independently:
  - contracts/capabilities.yaml
  - organization/capabilities.json
"""
import json
import pathlib

import yaml
import pytest

from organization.capability_registry import validate_mirror_drift


def test_canonical_is_organization_capability_registry_yaml():
    p = pathlib.Path("organization/capability-registry.yaml")
    assert p.exists(), "canonical must exist"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1.0"
    assert "engine_capabilities" in data
    assert data.get("canonical_source") == "organization/capability-registry.yaml" or "canonical_source" in data


def test_mirrors_match_canonical():
    # This is the core drift detection — mirrors must have identical engine_capabilities
    validate_mirror_drift()  # should not raise


def test_yaml_mirror_engine_capabilities_equal_canonical():
    canonical = yaml.safe_load(pathlib.Path("organization/capability-registry.yaml").read_text(encoding="utf-8"))
    yaml_mirror = yaml.safe_load(pathlib.Path("contracts/capabilities.yaml").read_text(encoding="utf-8"))
    assert yaml_mirror["engine_capabilities"] == canonical["engine_capabilities"]


def test_json_mirror_engine_capabilities_equal_canonical():
    canonical = yaml.safe_load(pathlib.Path("organization/capability-registry.yaml").read_text(encoding="utf-8"))
    json_mirror = json.loads(pathlib.Path("organization/capabilities.json").read_text(encoding="utf-8"))
    assert json_mirror["engine_capabilities"] == canonical["engine_capabilities"]


def test_mirrors_share_schema_version():
    canonical = yaml.safe_load(pathlib.Path("organization/capability-registry.yaml").read_text(encoding="utf-8"))
    yaml_mirror = yaml.safe_load(pathlib.Path("contracts/capabilities.yaml").read_text(encoding="utf-8"))
    json_mirror = json.loads(pathlib.Path("organization/capabilities.json").read_text(encoding="utf-8"))
    assert yaml_mirror["schema_version"] == canonical["schema_version"] == "1.0"
    assert json_mirror["schema_version"] == "1.0"
