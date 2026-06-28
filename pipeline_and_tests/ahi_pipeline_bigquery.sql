-- =============================================================================
-- AHI PIPELINE — BigQuery SQL v3 (Steps 2-6 only, Step 1 already complete)
-- =============================================================================


-- STEP 2 of 6: stg_monthly_consumption
CREATE OR REPLACE TABLE `pan-ahi-casestudy.ahi_case_study.stg_monthly_consumption` AS
SELECT
  d.account_id,
  DATE_TRUNC(d.date, MONTH)          AS month_start,
  SUM(d.compute_credits_consumed)    AS actual_credits_consumed,
  COUNT(DISTINCT d.date)             AS active_days
FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs` d
JOIN `pan-ahi-casestudy.ahi_case_study.Accounts` acc2 ON d.account_id = acc2.account_id
WHERE d.date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
GROUP BY d.account_id, DATE_TRUNC(d.date, MONTH);


-- STEP 3 of 6: stg_engagement_trend
CREATE OR REPLACE TABLE `pan-ahi-casestudy.ahi_case_study.stg_engagement_trend` AS
WITH monthly_usage AS (
  SELECT
    d.account_id,
    DATE_TRUNC(d.date, MONTH)        AS month_start,
    SUM(d.compute_credits_consumed)  AS monthly_credits
  FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs` d
  JOIN `pan-ahi-casestudy.ahi_case_study.Accounts` acc3 ON d.account_id = acc3.account_id
  WHERE d.date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
  GROUP BY d.account_id, DATE_TRUNC(d.date, MONTH)
),
indexed AS (
  SELECT
    account_id,
    monthly_credits,
    DATE_DIFF(month_start, DATE '2025-01-01', MONTH) AS month_idx
  FROM monthly_usage
),
regression AS (
  SELECT
    account_id,
    COUNT(*)                                                          AS n,
    SUM(CAST(month_idx AS FLOAT64) * monthly_credits)                AS sum_xy,
    SUM(CAST(month_idx AS FLOAT64))                                  AS sum_x,
    SUM(monthly_credits)                                             AS sum_y,
    SUM(CAST(month_idx AS FLOAT64) * CAST(month_idx AS FLOAT64))    AS sum_x2,
    AVG(monthly_credits)                                             AS avg_monthly,
    SAFE_DIVIDE(
      MAX(CASE WHEN month_idx = 0 THEN monthly_credits ELSE 0 END),
      NULLIF(SUM(monthly_credits), 0)
    )                                                                AS m1_share
  FROM indexed
  GROUP BY account_id
),
slope AS (
  SELECT
    account_id, avg_monthly, m1_share,
    SAFE_DIVIDE(
      (n * sum_xy - sum_x * sum_y),
      NULLIF(n * sum_x2 - sum_x * sum_x, 0)
    ) AS slope_per_month
  FROM regression
),
scored AS (
  SELECT
    account_id, slope_per_month, avg_monthly, m1_share,
    m1_share > 0.70 AS anomaly_flag,
    CASE
      WHEN SAFE_DIVIDE(slope_per_month, NULLIF(avg_monthly,0)) >  0.05 THEN 100.0
      WHEN SAFE_DIVIDE(slope_per_month, NULLIF(avg_monthly,0)) >  0.00 THEN 75.0
      WHEN SAFE_DIVIDE(slope_per_month, NULLIF(avg_monthly,0)) > -0.05 THEN 50.0
      WHEN SAFE_DIVIDE(slope_per_month, NULLIF(avg_monthly,0)) > -0.15 THEN 25.0
      ELSE 0.0
    END AS raw_trend_score
  FROM slope
)
SELECT
  account_id, slope_per_month, avg_monthly, m1_share, anomaly_flag,
  CASE
    WHEN anomaly_flag THEN ROUND(raw_trend_score * 0.5, 2)
    ELSE raw_trend_score
  END AS trend_score
FROM scored;


-- STEP 4 of 6: dim_account_ahi
CREATE OR REPLACE TABLE `pan-ahi-casestudy.ahi_case_study.dim_account_ahi` AS
WITH base AS (
  SELECT
    ac.account_id, ac.month_start,
    ac.committed_monthly_credits, ac.original_arr, ac.current_arr, ac.has_expansion,
    COALESCE(mc.actual_credits_consumed, 0) AS actual_credits,
    COALESCE(mc.active_days, 0)             AS active_days
  FROM `pan-ahi-casestudy.ahi_case_study.stg_active_contracts` ac
  LEFT JOIN `pan-ahi-casestudy.ahi_case_study.stg_monthly_consumption` mc
    ON ac.account_id = mc.account_id AND ac.month_start = mc.month_start
),
consumption AS (
  SELECT
    account_id, month_start,
    SAFE_DIVIDE(actual_credits, NULLIF(committed_monthly_credits,0)) AS raw_ratio,
    SAFE_DIVIDE(actual_credits, NULLIF(committed_monthly_credits,0)) > 1.20 AS overage_flag,
    CASE
      WHEN SAFE_DIVIDE(actual_credits, NULLIF(committed_monthly_credits,0)) > 1.20
        THEN ROUND(LEAST(SAFE_DIVIDE(actual_credits,NULLIF(committed_monthly_credits,0)),1.10)/1.10*100*0.85,2)
      ELSE ROUND(LEAST(SAFE_DIVIDE(actual_credits,NULLIF(committed_monthly_credits,0)),1.10)/1.10*100,2)
    END AS consumption_score
  FROM base
),
deployment AS (
  SELECT
    account_id, month_start,
    ROUND(
      SAFE_DIVIDE(
        LEAST(active_days, DATE_DIFF(DATE_ADD(month_start, INTERVAL 1 MONTH), month_start, DAY)),
        DATE_DIFF(DATE_ADD(month_start, INTERVAL 1 MONTH), month_start, DAY)
      ) * 100, 2
    ) AS deployment_score
  FROM base
),
stability AS (
  SELECT
    account_id,
    DATE_TRUNC(date, MONTH) AS month_start,
    ROUND(AVG(CASE health_color WHEN 'Green' THEN 100 WHEN 'Yellow' THEN 60 ELSE 20 END), 2) AS stability_score
  FROM `pan-ahi-casestudy.ahi_case_study.Account_Health`
  WHERE date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
  GROUP BY account_id, DATE_TRUNC(date, MONTH)
),
expansion AS (
  SELECT
    account_id, month_start,
    ROUND(LEAST(SAFE_DIVIDE(current_arr, NULLIF(original_arr,0)), 1.5) / 1.5 * 100, 2) AS expansion_score
  FROM base
)
SELECT
  b.account_id, b.month_start,
  COALESCE(c.consumption_score, 0)   AS consumption_score,
  COALESCE(d.deployment_score, 0)    AS deployment_score,
  COALESCE(s.stability_score, 50)    AS stability_score,
  COALESCE(e.expansion_score, 66.67) AS expansion_score,
  COALESCE(et.trend_score, 50)       AS trend_score,
  c.overage_flag,
  COALESCE(et.anomaly_flag, FALSE)   AS anomaly_flag,
  b.has_expansion                    AS contract_overlap_flag,
  c.raw_ratio                        AS consumption_ratio
FROM base b
LEFT JOIN consumption c  ON b.account_id = c.account_id  AND b.month_start = c.month_start
LEFT JOIN deployment  d  ON b.account_id = d.account_id  AND b.month_start = d.month_start
LEFT JOIN stability   s  ON b.account_id = s.account_id  AND b.month_start = s.month_start
LEFT JOIN expansion   e  ON b.account_id = e.account_id  AND b.month_start = e.month_start
LEFT JOIN `pan-ahi-casestudy.ahi_case_study.stg_engagement_trend` et ON b.account_id = et.account_id;


-- STEP 5 of 6: account_ahi_monthly
CREATE OR REPLACE TABLE `pan-ahi-casestudy.ahi_case_study.account_ahi_monthly` AS
SELECT
  d.account_id,
  d.month_start AS month,
  ROUND(d.consumption_score*0.25 + d.deployment_score*0.25 + d.stability_score*0.20 + d.expansion_score*0.15 + d.trend_score*0.15, 2) AS ahi_score,
  CASE
    WHEN (d.consumption_score*0.25+d.deployment_score*0.25+d.stability_score*0.20+d.expansion_score*0.15+d.trend_score*0.15) >= 80 THEN 'Healthy'
    WHEN (d.consumption_score*0.25+d.deployment_score*0.25+d.stability_score*0.20+d.expansion_score*0.15+d.trend_score*0.15) >= 65 THEN 'Monitor'
    WHEN (d.consumption_score*0.25+d.deployment_score*0.25+d.stability_score*0.20+d.expansion_score*0.15+d.trend_score*0.15) >= 50 THEN 'At Risk'
    WHEN (d.consumption_score*0.25+d.deployment_score*0.25+d.stability_score*0.20+d.expansion_score*0.15+d.trend_score*0.15) >= 35 THEN 'Critical'
    ELSE 'Churning'
  END AS health_status,
  d.consumption_score, d.deployment_score, d.stability_score,
  d.expansion_score, d.trend_score,
  d.overage_flag, d.anomaly_flag, d.contract_overlap_flag,
  d.consumption_ratio, a.industry, a.rep_id
FROM `pan-ahi-casestudy.ahi_case_study.dim_account_ahi` d
JOIN `pan-ahi-casestudy.ahi_case_study.Accounts` a ON d.account_id = a.account_id;


-- STEP 6 of 6: csm_ahi_monthly
CREATE OR REPLACE TABLE `pan-ahi-casestudy.ahi_case_study.csm_ahi_monthly` AS
SELECT
  a.rep_id                                                                          AS csm_id,
  r.name                                                                            AS csm_name,
  r.region, r.segment, ahi.month,
  ROUND(SAFE_DIVIDE(SUM(ahi.ahi_score * ac.current_arr), NULLIF(SUM(ac.current_arr),0)), 2) AS ahi_score,
  COUNT(DISTINCT ahi.account_id)                                                    AS total_accounts,
  COUNT(DISTINCT CASE WHEN ahi.ahi_score < 50    THEN ahi.account_id END)          AS accounts_at_risk,
  COUNT(DISTINCT CASE WHEN ahi.health_status = 'Churning' THEN ahi.account_id END) AS accounts_churning,
  ROUND(SUM(ac.current_arr), 0)                                                     AS total_arr,
  ROUND(SUM(CASE WHEN ahi.ahi_score < 50 THEN ac.current_arr ELSE 0 END), 0)       AS arr_at_risk,
  COUNT(DISTINCT CASE WHEN ahi.overage_flag  THEN ahi.account_id END)              AS upsell_opportunities,
  COUNT(DISTINCT CASE WHEN ahi.anomaly_flag  THEN ahi.account_id END)              AS anomaly_accounts
FROM `pan-ahi-casestudy.ahi_case_study.account_ahi_monthly` ahi
JOIN `pan-ahi-casestudy.ahi_case_study.Accounts` a   ON ahi.account_id = a.account_id
JOIN `pan-ahi-casestudy.ahi_case_study.CSM_rep` r    ON a.rep_id = r.csm_id
LEFT JOIN `pan-ahi-casestudy.ahi_case_study.stg_active_contracts` ac
  ON ahi.account_id = ac.account_id AND ahi.month = ac.month_start
GROUP BY a.rep_id, r.name, r.region, r.segment, ahi.month;
