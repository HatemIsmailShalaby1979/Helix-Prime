"""Fail-closed authentication for POST /api/v1/cockpit/approve.

The approve route is the human-in-the-loop authority action. These tests prove it
refuses when no key is configured (unless the local-dev override is set), refuses on a
missing or wrong key, and accepts a matching X-Cockpit-Key header. They also confirm the
audit note records the manager id as asserted, not verified.

The env vars are read per request, so each test sets exactly the variables it needs and
builds a fresh app, keeping the cases isolated.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ingest_engine import (
    CockpitStateEngine,
    IngestPayload,
    QueueMetrics,
    SimulationState,
    create_app,
)

APPROVE_URL = "/api/v1/cockpit/approve"
KEY = "test-approve-key-value"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(CockpitStateEngine()))


def _post_approve(client: TestClient, *, key: str | None = None) -> object:
    headers = {"X-Cockpit-Key": key} if key is not None else {}
    return client.post(
        APPROVE_URL,
        json={"intervention_id": "does-not-exist", "decision": "approve", "manager_id": "MGR-01"},
        headers=headers,
    )


def test_approve_refuses_when_no_key_configured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """No HELIX_COCKPIT_APPROVE_KEY and no override -> 503, never a 404/200."""
    monkeypatch.delenv("HELIX_COCKPIT_APPROVE_KEY", raising=False)
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client)
    assert response.status_code == 503
    assert "HELIX_COCKPIT_APPROVE_KEY" in response.json()["detail"]


def test_approve_refuses_with_wrong_key(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A configured key must be matched exactly; a wrong key is refused."""
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", KEY)
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key="not-the-right-key")
    assert response.status_code == 401


def test_approve_refuses_with_missing_key_header(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """With a key configured, omitting the header is refused."""
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", KEY)
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key=None)
    assert response.status_code == 401


def test_approve_accepts_correct_key(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """A matching header passes the gate; an unknown id then yields 404, not 401/503."""
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", KEY)
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key=KEY)
    assert response.status_code == 404


def test_approve_allows_dev_override_without_key(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """The local-dev override permits unauthenticated approve; unknown id -> 404."""
    monkeypatch.delenv("HELIX_COCKPIT_APPROVE_KEY", raising=False)
    monkeypatch.setenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", "true")
    response = _post_approve(client, key=None)
    assert response.status_code == 404


def test_approve_records_identity_as_asserted_not_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: a matching key approves a real intervention and the audit note
    states the manager id was asserted by the key holder, not verified."""
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", KEY)
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    engine = CockpitStateEngine()
    with TestClient(create_app(engine)) as client:
        trigger = client.post(
            "/api/v1/telemetry",
            json=IngestPayload(
                metrics=QueueMetrics(
                    timestamp=1000.0,
                    calls_waiting=200,
                    longest_wait_time=400.0,
                    sla_percentage=5.0,
                    active_agents=30,
                    aux_agents=30,
                ),
                state=SimulationState(is_spike_active=True, current_interval_volume=1000.0),
            ).model_dump(mode="json"),
        )
        assert trigger.status_code == 200
        pending = trigger.json()["newly_generated"]
        assert pending is not None

        response = client.post(
            APPROVE_URL,
            json={
                "intervention_id": pending["id"],
                "decision": "approve",
                "manager_id": "MGR-07",
            },
            headers={"X-Cockpit-Key": KEY},
        )
        assert response.status_code == 200
        note = response.json()["execution_trace"]["note"]
        assert "MGR-07" in note
        assert "not verified" in note


def test_approve_non_ascii_key_header_returns_401_not_500(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A non-ASCII X-Cockpit-Key header must be refused with 401, never raise a
    TypeError that escapes as a 500. Both keys are compared as UTF-8 bytes, so an
    arbitrary non-ASCII header value cannot trip compare_digest's str guard.
    """
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", KEY)
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    # Raw UTF-8 bytes ride the wire; Starlette decodes the header as latin-1, so the
    # server sees a non-ASCII str -- exactly the input that used to raise.
    headers = [(b"X-Cockpit-Key", "café-🔑-naïve".encode("utf-8"))]
    response = client.post(
        APPROVE_URL,
        json={
            "intervention_id": "does-not-exist",
            "decision": "approve",
            "manager_id": "MGR-01",
        },
        headers=headers,
    )
    assert response.status_code == 401


def test_approve_empty_key_with_empty_header_does_not_authenticate(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A configured key of "" is not a secret: it must be refused like an unset one.

    Even when the caller sends an empty X-Cockpit-Key header that would "match" an
    empty key, the endpoint returns 503 (unavailable), never 200 or 404.
    """
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", "")
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key="")
    assert response.status_code == 503


def test_approve_whitespace_only_key_does_not_authenticate(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A whitespace-only key is treated as unset, so it cannot authenticate."""
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", "    ")
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key="    ")
    assert response.status_code == 503


def test_approve_short_key_is_refused(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """A key shorter than 16 characters is refused with 503, not accepted."""
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", "short")
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key="short")
    assert response.status_code == 503
    assert "16 characters" in response.json()["detail"]


def test_approve_valid_long_key_still_works(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A real (>=16 char) key still gates correctly: a matching header passes the
    auth check, so an unknown id then yields 404 rather than 401 or 503.
    """
    monkeypatch.setenv("HELIX_COCKPIT_APPROVE_KEY", "valid-long-approve-key-001")
    monkeypatch.delenv("HELIX_COCKPIT_ALLOW_UNAUTHENTICATED", raising=False)
    response = _post_approve(client, key="valid-long-approve-key-001")
    assert response.status_code == 404
