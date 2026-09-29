-- The "slow dashboard query". Goal: under 5 ms.
SELECT date_trunc('day', created_at) AS day, kind, count(*) AS n
FROM events
WHERE account_id = 42
  AND created_at >= TIMESTAMPTZ '2026-06-01 00:00:00+00'
GROUP BY 1, 2
ORDER BY 1, 2
