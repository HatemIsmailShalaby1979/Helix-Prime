#!/usr/bin/env python3
"""Helix Codex synthetic demonstration — run from a clean setup (in-memory memory).

No network, no live connectors, no cloud, no external writes. Demonstrates the same
governed core supporting a call-centre pilot tenant and a restaurant capability-pack
tenant in one governed memory. Claims only what this script shows.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)

from memory.governed_memory import GovernedMemory  # noqa: E402
from pilot import PilotRuntime, PilotConfig, ConsentRecord, build_evidence_pack  # noqa: E402
from capabilities.restaurant import (  # noqa: E402
    RestaurantCapabilityPack, build_synthetic_restaurant,
)
from connectors.contracts import ConnectorContext  # noqa: E402

AS_OF = "2026-08-29T12:00:00Z"


def _consent(tenant_id, client_id):
    return ConsentRecord(
        consent_id=f"consent-{tenant_id}", tenant_id=tenant_id, client_id=client_id,
        customer_id=f"cust-{tenant_id}", status="granted",
        granted_at="2026-01-01T00:00:00Z", expires_at="2027-01-01T00:00:00Z",
        data_modes_permitted=("historical_consented", "simulated_realistic"),
        recorded_by="csm", signature="demo-sig",
    )


def main() -> int:
    print("=" * 70)
    print("HELIX CODEX — SYNTHETIC DEMONSTRATION (clean setup)")
    print("=" * 70)

    mem = GovernedMemory()  # clean, in-memory

    # --- call-centre pilot (verified core) ---
    cc = PilotRuntime(PilotConfig.from_dict({}), mem)
    cc.prepare_first_real_pilot("2026-08-01T00:00:00Z", "2026-09-01T00:00:00Z",
                                _consent("cc-1", "cc-c1"), AS_OF)
    cc.dry_run([("cc-1", "cc-c1")], consent=_consent("cc-1", "cc-c1"))
    cc.exit_read_only_period(AS_OF, "approver-1", "ict_gm")
    cc_pack = build_evidence_pack(cc, AS_OF)

    # --- restaurant capability pack (same governed core) ---
    rt = RestaurantCapabilityPack(mem)
    fixtures = {(("r1", "rc1")): build_synthetic_restaurant("r1", "rc1", AS_OF)}
    rt.prepare_first_real_pilot("2026-08-01T00:00:00Z", "2026-09-01T00:00:00Z",
                                _consent("r1", "rc1"), AS_OF)
    rt.dry_run([("r1", "rc1")], fixtures, consent=_consent("r1", "rc1"))
    rt.exit_read_only_period(AS_OF, "approver-1", "restaurant_gm")
    rt_pack = rt.build_evidence_pack(AS_OF)

    # --- invariants (must hold) ---
    ok, chain_msg = mem.verify_chain()
    assert ok, f"audit chain broken: {chain_msg}"
    assert all(r.data_mode != "live_customer" for r in mem._records), "live data leaked"
    assert cc.config.live_activated is False and rt.config.live_activated is False
    assert cc_pack["final_status"]["production_readiness"] == "NOT_ESTABLISHED"
    assert rt_pack["final_status"]["production_readiness"] == "NOT_ESTABLISHED"
    # tenant isolation across both packs in one memory
    assert cc.tenant_isolation_ok("cc-1", "r1") is True

    # prove connectors never execute writes
    ctx = ConnectorContext("r1", "org-1", "rc1", actor="x", correlation_id="c", data_mode="simulated_realistic")
    from capabilities.restaurant.contracts import RestaurantConnector
    assert RestaurantConnector("restaurant_ops", "RestaurantOps", {}).request_write(ctx, "reorder", {}, None).executed is False

    print("\n[call-centre pilot] tenants:", cc.tenant_ids, "diagnoses:", cc.summary()["diagnoses"])
    print("[call-centre pilot] approval summary:", cc_pack["approval_summary"])
    print("[call-centre pilot] live_customer_records:", cc_pack["live_customer_records"], "audit_chain_intact:", cc_pack["audit_chain_intact"])
    print("[call-centre pilot] final_status:", cc_pack["final_status"])
    print("\n[restaurant pack] tenants:", rt.tenant_ids, "diagnoses:", rt.summary()["diagnoses"])
    print("[restaurant pack] metrics:", {k: rt_pack["metrics"][k] for k in ("escalation_accuracy", "recommendation_acceptance_rate", "customer_health_visibility")})
    print("[restaurant pack] approval summary:", rt_pack["approval_summary"])
    print("[restaurant pack] live_customer_records:", rt_pack["live_customer_records"], "audit_chain_intact:", rt_pack["audit_chain_intact"])
    print("[restaurant pack] final_status:", rt_pack["final_status"])
    print("\n[shared memory] total records:", len(mem._records), "audit_chain_intact:", ok)
    print("\nSYNTHETIC DEMO OK — read-only, synthetic, no external writes, audit intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
