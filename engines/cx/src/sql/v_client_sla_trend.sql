-- v_client_sla_trend.sql
-- Canonical SLA compliance trend view consumed by CX Churn Sentinel.
-- value = fraction of interactions meeting SLA in the period (0.0–1.0).
CREATE OR REPLACE VIEW v_client_sla_trend AS
SELECT
    c.client_id,
    d.snapshot_date AS date,
    AVG(CASE WHEN c.met_sla THEN 1.0 ELSE 0.0 END) AS value
FROM customer_interactions c
JOIN interaction_dates d ON d.interaction_id = c.interaction_id
WHERE c.metric = 'sla'
GROUP BY c.client_id, d.snapshot_date;
