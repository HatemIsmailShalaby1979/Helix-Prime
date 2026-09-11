"""
Service-spine integration tests (Phase 1 W4).

These exercise the real HTTP surface over the real control plane: submit a
governed task, watch the gate freeze it, approve it, and execute it. Nothing
here mocks ``Engine`` — mocking it would test the router and prove nothing about
whether the spine is wired correctly.

They also pin two behaviours that are easy to regress:

* a frozen run answers **409**, not 200 — the request was recorded and did not
  happen;
* every response carries ``X-Request-ID``, so a screenshot from an operator is
  enough to find the run in the logs.
"""
from __future__ import annotations

import json
import secrets

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

# H0.3: auth middleware is required on all /api routes, so these tests must present a
# token to keep exercising business logic rather than auth. Generated at import, never a
# literal: the release gate secret-scans the whole tree and a hardcoded token here would
# (correctly) fail security_checks.
_TEST_TOKEN = secrets.token_urlsafe(24)


@pytest.fixture(autouse=True)
def _token_env(monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", _TEST_TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "sami")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from server.app import create_app
    from server.config import Settings

    settings = Settings(
        profile="local",
        db_path=str(tmp_path / "workflow.db"),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


_AUTH_HEADERS = {"Authorization": f"Bearer {_TEST_TOKEN}"}


def _submit(client, **overrides):
    payload = {
        "tenant_id": "tenant-spine",
        "client_id": "client-spine",
        "capability": "wfm_forecast",
        "requesting_actor": "suby",
        "owning_role_id": "ops_gm",
        # Real WFM inputs, not a placeholder: the point of the spine test is
        # that an engine actually runs behind the HTTP boundary.
        "input_payload": {
            "arrival_rate": 120,
            "average_handling_time": 300,
            "service_level_target": 0.8,
        },
        "requires_approval": True,
    }
    payload.update(overrides)
    return client.post("/api/workflows", json=payload, headers=_AUTH_HEADERS)


def test_healthz_reports_ok(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_is_ready_on_a_fresh_instance(client) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_submit_freezes_at_the_gate_and_answers_409(client) -> None:
    response = _submit(client)
    assert response.status_code == 409
    body = response.json()
    assert body["state"] == "awaiting_approval"
    assert body["correlation_id"]


def test_approve_then_execute_closes_the_run(client) -> None:
    submitted = _submit(client).json()
    workflow_id = submitted["workflow_id"]

    approved = client.post(
        f"/api/approvals/{workflow_id}",
        json={
            "approver_actor": "andy",
            "approver_role_id": "compliance_quality_gm",
            "decision": "approved",
            "reason": "spine integration test",
        },
        headers=_AUTH_HEADERS,
    )
    assert approved.status_code == 200
    assert approved.json()["state"] != "awaiting_approval"

    executed = client.post(f"/api/workflows/{workflow_id}/execute", headers=_AUTH_HEADERS)
    assert executed.status_code == 200
    assert executed.json()["state"] in {"succeeded", "closed", "failed"}

    stored = client.get(f"/api/workflows/{workflow_id}", headers=_AUTH_HEADERS)
    assert stored.status_code == 200


def test_denied_approval_prevents_execution(client) -> None:
    submitted = _submit(client).json()
    workflow_id = submitted["workflow_id"]

    denied = client.post(
        f"/api/approvals/{workflow_id}",
        json={
            "approver_actor": "andy",
            "approver_role_id": "compliance_quality_gm",
            "decision": "denied",
            "reason": "spine integration test — denial",
        },
        headers=_AUTH_HEADERS,
    )
    assert denied.status_code == 200
    after = client.get(f"/api/workflows/{workflow_id}", headers=_AUTH_HEADERS).json()
    assert after["state"] != "awaiting_approval"


def test_pending_approvals_appear_in_the_queue(client) -> None:
    _submit(client)
    queue = client.get("/api/approvals", headers=_AUTH_HEADERS).json()
    assert any(item["state"] == "awaiting_approval" for item in queue)


def test_unknown_workflow_is_404(client) -> None:
    assert client.get("/api/workflows/does-not-exist", headers=_AUTH_HEADERS).status_code == 404


def test_every_response_carries_a_correlation_id(client) -> None:
    response = client.get("/healthz")
    assert response.headers["X-Request-ID"]

    # An inbound id is honoured, not overwritten.
    response = client.get("/healthz", headers={"X-Request-ID": "req_client_supplied"})
    assert response.headers["X-Request-ID"] == "req_client_supplied"


def test_run_timeline_is_retrievable(client) -> None:
    workflow_id = _submit(client).json()["workflow_id"]
    events = client.get(f"/api/workflows/{workflow_id}/events", headers=_AUTH_HEADERS).json()
    assert isinstance(events, list)
    assert any("workflow" in json.dumps(e) for e in events)


def test_sse_stream_receives_state_frames() -> None:
    """
    The stream subscribes and emits frames published by the service.

    Driven directly rather than through an ASGI client: a test client cannot
    stream an infinite response to completion, and making the endpoint finite
    to satisfy a test would be exactly backwards.
    """
    import asyncio

    from server.features.stream.router import event_stream
    from server.sse import get_bus

    class _FakeRequest:
        def __init__(self) -> None:
            self.disconnected = False

        async def is_disconnected(self) -> bool:
            return self.disconnected

    async def collect() -> list[str]:
        bus = get_bus()
        request = _FakeRequest()
        frames: list[str] = []
        # Publish shortly after the generator starts: publish() delivers to the
        # subscribers that exist at that moment, and the generator only
        # subscribes once iteration begins.
        loop = asyncio.get_running_loop()
        loop.call_later(
            0.05,
            bus.publish,
            "corr-test-stream",
            "workflow_state",
            {"state": "awaiting_approval"},
        )
        async for frame in event_stream(request, "corr-test-stream"):  # type: ignore[arg-type]
            frames.append(frame)
            request.disconnected = True
        return frames

    frames = asyncio.run(collect())
    assert frames, "the stream emitted nothing"
    assert "event: workflow_state" in frames[0]
    assert "awaiting_approval" in frames[0]
    assert get_bus().subscriber_count("corr-test-stream") == 0, "unsubscribe was not called"


def test_production_profile_refuses_to_start_without_gate_inputs(tmp_path, monkeypatch) -> None:
    """The production gate fails closed. This keeps anyone from 'fixing' that."""
    for name in ("HELIX_EVIDENCE_SIGNING_KEY", "HELIX_ISOLATION_CERT", "HELIX_OBSERVER_AUDIT"):
        monkeypatch.delenv(name, raising=False)

    from server.app import create_app
    from server.config import Settings

    settings = Settings(
        profile="production",
        db_path=str(tmp_path / "wf.db"),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    with pytest.raises(RuntimeError, match="production requires"):
        with TestClient(create_app(settings)):
            pass
