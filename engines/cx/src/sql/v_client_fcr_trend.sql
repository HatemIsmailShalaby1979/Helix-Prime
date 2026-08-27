-- v_client_fcr_trend.sql
-- Canonical First Contact Resolution trend view consumed by CX Churn Sentinel.
-- value = fraction of cases resolved on first contact (0.0–1.0).
CREATE OR REPLACE VIEW v_client_fcr_trend AS
SELECT
    c.client_id,
    d.snapshot_date AS date,
    AVG(CASE WHEN c.first_contact_resolution THEN 1.0 ELSE 0.0 END) AS value
FROM customer_interactions c
JOIN interaction_dates d ON d.interaction_id = c.interaction_id
WHERE c.metric = 'fcr'
GROUP BY c.client_id, d.snapshot_date;
