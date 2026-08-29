"""Governed Codex Command Center view (Prompt 6).

Integrates the VERIFIED connector layer (Prompt 4) and customer-success wedge
(Prompt 5) into one read-only command-center view. This module is the Streamlit
shell only; all decision logic lives in :mod:`cockpit.command_center_integration`
(which is unit-tested without Streamlit).

The cockpit never performs external writes. It previews actions, enforces
cross-role approval (separation of duties), and records outcomes in memory.
"""
from __future__ import annotations

import streamlit as st

from connectors.contracts import ConnectorContext, ConnectorStatus
from connectors.fakes import FakeConnector
from connectors.registry import ConnectorRegistry
from customer_success.fixtures import (
    at_risk_account,
    contradictory_account,
    unknown_account,
)
from memory.governed_memory import GovernedMemory
from command_center_integration import (
    assemble_command_center,
    evaluate_approval,
    reset_demo,
)

DEFAULT_MEMORY_PATH = "memory/governed_memory.jsonl"


def render(client_name: str) -> None:
    st.markdown("<div class='section-hdr'>Codex Command Center</div>", unsafe_allow_html=True)
    st.info("Synthetic, governed customer-success command view. No external systems are written from here.")

    # 1. tenant/client selector + 2. data-mode indicator
    col_t, col_c, col_r, col_m = st.columns(4)
    tenant_id = col_t.text_input("Tenant ID", "local-demo-tenant")
    client_id = client_name
    col_c.text_input("Client ID", client_id, disabled=True)
    role_id = col_r.selectbox("Your role", ["customer_success_gm", "sales_gm", "ict_gm"])
    requested_data_mode = col_m.selectbox(
        "Data mode", ["simulated_realistic", "historical_consented", "live_external"],
    )

    correlation_id = st.session_state.get("session_id", "codex-session")
    actor = "local-operator"

    # Synthetic-state simulators (read-only demo controls)
    with st.expander("Synthetic demonstration controls"):
        sim_outage = st.checkbox("Simulate Zendesk outage (unavailable)")
        sim_contradictory = st.checkbox("Simulate contradictory data")
        sim_stale = st.checkbox("Simulate stale data")
        sim_missing = st.checkbox("Simulate missing data")
        if st.button("Reset synthetic outcomes"):
            if "cs_memory" in st.session_state:
                reset_demo(st.session_state.cs_memory)
            st.success("Governed memory reset (synthetic demo).")

    # Build the governed view
    ctx = ConnectorContext(
        tenant_id, "org-1", client_id, actor=actor,
        correlation_id=correlation_id, data_mode="simulated_realistic",
    )
    connectors = None
    bundle = None
    if sim_outage:
        reg = ConnectorRegistry(mode="fake")
        connectors = {p: reg.get_connector(p, ctx) for p in ("salesforce", "zendesk", "clay")}
        connectors["zendesk"] = FakeConnector("zendesk", "Zendesk", status=ConnectorStatus.DISCONNECTED)
    if sim_contradictory:
        bundle = contradictory_account(ctx)
    elif sim_stale:
        bundle = at_risk_account(ctx, stale=True)
    elif sim_missing:
        bundle = unknown_account(ctx)

    if "cs_memory" not in st.session_state:
        st.session_state.cs_memory = GovernedMemory(path=DEFAULT_MEMORY_PATH)

    view = assemble_command_center(
        tenant_id, client_id, actor, role_id, requested_data_mode, correlation_id,
        client_name=client_name, memory=st.session_state.cs_memory,
        connectors=connectors, bundle=bundle,
    )

    _display_view(view)


def _display_view(view) -> None:
    meta = view.meta

    # 2. data-mode indicator (never present simulated as live)
    if meta.live_warning:
        st.warning("⚠ Live mode requested but not activated — showing SIMULATED data only.")
    st.caption(f"Data mode: requested={meta.requested_data_mode} • effective={meta.effective_data_mode} "
               f"• classification={meta.classification} • correlation={meta.correlation_id}")

    # 12. clear state banners
    for alert in view.state_flags.get("alerts", []):
        st.error(f"⚠ {alert}")

    # 3. connector status (Zendesk / Salesforce / Clay)
    st.markdown("### Connector status")
    st.dataframe([c.health | {"governance_tenant": meta.tenant_id,
                              "governance_client": meta.client_id} for c in view.connector_status],
                 width="stretch", hide_index=True)

    # 4. account-health diagnosis
    d = view.diagnosis
    st.markdown("### Account-health diagnosis")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Health state", d.health_state)
    m2.metric("Score", f"{d.score:.0f}/100")
    m3.metric("Confidence", f"{d.confidence:.0%}")
    m4.metric("Approval required", "Yes" if d.approval_requirement else "No")

    # 5. structured risk factors + evidence references
    st.markdown("### Risk factors & evidence references")
    if d.risk_factors:
        for rf in d.risk_factors:
            st.warning(f"**{rf.factor}** — severity {rf.severity} — evidence: {', '.join(rf.evidence_refs) or 'n/a'}")
    else:
        st.success("No current risks detected in the available data.")

    # 6. recommended next action + 7. responsible role & confidence
    st.markdown("### Recommended next action")
    st.write(f"• {d.recommended_action}")
    st.caption(f"Responsible role: **{d.responsible_role}** • Expected outcome: {d.expected_outcome}")

    # 8. approval preview + cross-role enforcement
    st.markdown("### Approval preview")
    p = view.approval_preview
    st.write(f"Required: **{p.required}** • Role: **{p.role}** • Policy: {p.policy}")
    st.write(f"Reason: {p.reason}")
    with st.form("approval_check"):
        ap_actor = st.text_input("Approver actor", "approver-bob")
        ap_role = st.selectbox("Approver role", ["customer_success_gm", "sales_gm", "ict_gm"])
        submitted = st.form_submit_button("Evaluate approval (preview only)")
        if submitted:
            decision = evaluate_approval(view, ap_actor, ap_role)
            if decision.decision == "allowed":
                st.success(f"Approval {decision.decision}: {decision.reason}")
            elif decision.decision == "denied":
                st.error(f"Approval {decision.decision}: {decision.reason}")
            else:
                st.info(f"Approval {decision.decision}: {decision.reason}")

    # record an outcome in governed memory (read-only over sources)
    with st.expander("Record recommendation outcome (governed memory only)"):
        decision = st.selectbox("Decision", ["accepted", "rejected", "deferred"])
        rationale = st.text_input("Rationale", "demo decision")
        if st.button("Record outcome"):
            rec = st.session_state.cs_memory.add(
                kind="outcome",
                nature="verified_outcome" if d.health_state != "contradictory" else "model_inference",
                tenant_id=meta.tenant_id,
                client_id=meta.client_id,
                actor="local-operator",
                role_id=meta.role_id,
                source="codex_command_center",
                classification=meta.classification,
                timestamp="2026-08-29T12:00:00Z",
                correlation_id=meta.correlation_id,
                confidence=d.confidence,
                evidence_refs=[e.ref for e in d.evidence],
                data_mode=meta.effective_data_mode,
                provenance={
                    "correlation_id": meta.correlation_id,
                    "data_mode": meta.effective_data_mode,
                    "basis": d.provenance.basis,
                    "sources": list(d.provenance.sources),
                },
                body={"decision": decision, "rationale": rationale, "diagnosis_ref": d.fingerprint()},
            )
            st.success(f"Recorded {rec.record_id} ({decision}).")

    # 9. evidence & provenance timeline
    st.markdown("### Evidence & provenance timeline")
    for e in sorted(view.evidence_timeline, key=lambda x: x.observed_at):
        st.write(f"- `{e.provider}` {e.record_id} @ {e.observed_at} [{e.data_mode}] — {e.detail}")

    # 10. governed memory timeline (all record kinds, tenant-scoped)
    st.markdown("### Governed memory timeline")
    if view.memory_timeline:
        for m in view.memory_timeline:
            st.write(
                f"- `{m.record_id}` **{m.kind}** [{m.nature}] cls={m.classification} "
                f"by {m.actor}/{m.role_id} @ {m.timestamp} — {m.summary}"
            )
    else:
        st.info("No governed-memory records yet for this tenant/client.")

    # 10b. outcome-memory timeline (outcome kind only)
    st.markdown("### Outcome-memory timeline")
    if view.outcome_timeline:
        for o in view.outcome_timeline:
            st.write(f"- {o.recorded_at} **{o.decision}** ({o.nature}) by {o.actor}/{o.role_id} — {o.rationale} (ref {o.diagnosis_ref})")
    else:
        st.info("No recorded outcomes yet for this account.")

    # 11. audit status
    st.markdown("### Audit status")
    st.write(f"Audit chain: **{view.audit_status}**")

    # governance footer — every item preserves tenant/client/role/classification/correlation/data-mode
    st.divider()
    st.caption(
        f"Governance: tenant={meta.tenant_id} client={meta.client_id} role={meta.role_id} "
        f"classification={meta.classification} correlation={meta.correlation_id} "
        f"data_mode={meta.effective_data_mode}"
    )
