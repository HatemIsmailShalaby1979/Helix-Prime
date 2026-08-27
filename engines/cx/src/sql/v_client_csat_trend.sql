-- v_client_csat_trend.sql
-- Canonical CSAT trend view consumed by CX Churn Sentinel (sql_extractor.py).
-- Returns one row per (client_id, date) with the CSAT score (0.0–1.0).
--
-- Adapter note: this is the reference PostgreSQL definition. To use it with a
-- different source, point the inner SELECT at your CSAT interactions table.
-- The CX engine expects columns: client_id, date, value.
CREATE OR REPLACE VIEW v_client_csat_trend AS
SELECT
    c.client_id,
    d.snapshot_date AS date,
    AVG(c.score::numeric) AS value
FROM customer_interactions c
JOIN interaction_dates d ON d.interaction_id = c.interaction_id
WHERE c.metric = 'csat'
GROUP BY c.client_id, d.snapshot_date;
