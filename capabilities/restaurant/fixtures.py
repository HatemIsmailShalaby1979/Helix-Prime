"""Synthetic restaurant fixtures for the read-only pilot (Prompt 11, item 10).

Clearly synthetic, deterministic data for one location. Used only for demonstration;
no live customer data and no network access.
"""
from __future__ import annotations

from connectors.contracts import SourceRef
from .ontology import (
    Employee, Shift, InventoryItem, Supplier, Complaint, DailySummary,
)

DATA_MODE = "simulated_realistic"


def _src(provider: str, record_id: str, as_of: str) -> SourceRef:
    return SourceRef(provider, record_id, as_of, "v1-synthetic", DATA_MODE)


def build_synthetic_restaurant(tenant_id: str, client_id: str, as_of: str) -> dict:
    employees = [
        Employee("emp-cook-1", "Sam Cook", "cook", ("lunch", "dinner"), tenant_id, client_id,
                 _src("HR", "emp-cook-1", as_of)),
        Employee("emp-server-1", "Dana Server", "server", ("lunch", "dinner"), tenant_id, client_id,
                 _src("HR", "emp-server-1", as_of)),
        Employee("emp-host-1", "Lee Host", "host", ("lunch",), tenant_id, client_id,
                 _src("HR", "emp-host-1", as_of)),
    ]

    shifts = [
        Shift("sh-lunch", "2026-08-29", "11:00", "15:00", "lunch", 3,
              ("emp-cook-1", "emp-server-1"), tenant_id, client_id,
              _src("Scheduling", "sh-lunch", as_of)),
        Shift("sh-dinner", "2026-08-29", "17:00", "22:00", "dinner", 4,
              ("emp-cook-1", "emp-server-1", "emp-host-1"), tenant_id, client_id,
              _src("Scheduling", "sh-dinner", as_of)),
    ]

    inventory = [
        InventoryItem("inv-lettuce", "Lettuce", "produce", 2.0, "kg", 5.0, "sup-fresh",
                      tenant_id, client_id, _src("Inventory", "inv-lettuce", as_of)),
        InventoryItem("inv-flour", "Flour", "dry_goods", 12.0, "kg", 8.0, "sup-staples",
                      tenant_id, client_id, _src("Inventory", "inv-flour", as_of)),
        InventoryItem("inv-cheese", "Cheese", "dairy", 1.0, "kg", 3.0, "sup-dairy",
                      tenant_id, client_id, _src("Inventory", "inv-cheese", as_of)),
    ]

    suppliers = [
        Supplier("sup-fresh", "Fresh Produce Co", 2, 0.92, tenant_id, client_id,
                 _src("Procurement", "sup-fresh", as_of)),
        Supplier("sup-staples", "Staples Ltd", 4, 0.88, tenant_id, client_id,
                 _src("Procurement", "sup-staples", as_of)),
        Supplier("sup-dairy", "Dairy Direct", 3, 0.70, tenant_id, client_id,
                 _src("Procurement", "sup-dairy", as_of)),
    ]

    complaints = [
        Complaint("cmp-1", "online", "high", "food", "2026-08-29T12:00:00Z",
                  "2026-08-29T18:00:00Z", "open", tenant_id, client_id,
                  _src("Feedback", "cmp-1", as_of)),
    ]

    summary = DailySummary("2026-08-29", 120, 3000.0, 1, 6, 7, tenant_id, client_id,
                           _src("POS", "daily-2026-08-29", as_of))

    return {
        "employees": employees,
        "shifts": shifts,
        "inventory": inventory,
        "suppliers": suppliers,
        "complaints": complaints,
        "daily_summary": [summary],
    }
