-- v_client_aht_trend.sql
-- Canonical Average Handle Time trend view consumed by CX Churn Sentinel.
-- value = average handle time in minutes for the period.
-- (Risk scorer treats lower AHT as better via inverse normalization.)
CREATE OR REPLACE VIEW v_client_aht_trend AS
SELECT
    c.client_id,
    d.snapshot_date AS date,
    AVG(c.handle_time_seconds::numeric) / 60.0 AS value
FROM customer_interactions c
JOIN interaction_dates d ON d.interaction_id = c.interaction_id
WHERE c.metric = 'aht'
GROUP BY c.client_id, d.snapshot_date;
