"""Cockpit views for the sports-academy pack (v1).

Each view is split into a pure ``compute_*`` function (no Streamlit import,
reusable by the future HTMX console) and a thin ``render_*`` wiring function
for the Streamlit cockpit. All data flows through the read-only connector so
tenant scoping and provenance are enforced; the synthetic-data banner is
always visible (constitution: simulated vs live remain visibly distinct).
"""
