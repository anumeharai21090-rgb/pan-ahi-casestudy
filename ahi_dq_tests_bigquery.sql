-- =============================================================================
-- AHI Pipeline — BigQuery SQL Data Quality Tests
-- Palo Alto Networks · Global Customer Services
--
-- Run these six queries BEFORE executing the AHI pipeline.
-- Each query returns zero rows if the test passes.
-- Any rows returned = test failure = investigate before running pipeline.
--
-- Tests:
--   1. orphaned_usage_check        — account_ids in logs not in Accounts
--   2. overlapping_contracts_check — unexpected overlapping contracts
--   3. negative_consumption_check  — compute_credits_consumed < 0
--   4. future_usage_check          — usage dates beyond 2025-12-31
--   5. contract_date_usage_check   — usage outside active contract dates
--   6. null_account_id_check       — NULL account_ids in any table
-- =============================================================================


-- =============================================================================
-- TEST 1: Orphaned Usage Check
-- Returns rows where account_id in Daily_Usage_Logs
-- does not exist in the Accounts table.
-- Expected result: 150 GHOST_ rows (seeded edge case).
-- FAIL condition: any non-GHOST_ account_ids returned.
-- =============================================================================
SELECT
  'orphaned_usage_check'        AS test_name,
  l.log_id,
  l.account_id,
  l.date,
  l.compute_credits_consumed,
  'account_id not found in Accounts table' AS failure_reason
FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs` AS l
LEFT JOIN `pan-ahi-casestudy.ahi_case_study.Accounts` AS a
  ON l.account_id = a.account_id
WHERE
  a.account_id IS NULL
  -- Exclude deliberately seeded GHOST_ rows (known edge case)
  AND NOT STARTS_WITH(l.account_id, 'GHOST_')
ORDER BY l.account_id, l.date;


-- =============================================================================
-- TEST 2: Overlapping Contracts Check
-- Returns accounts with multiple active 2025 contracts
-- where the second contract is NOT a legitimate expansion
-- (i.e. second contract is smaller or same size as first).
-- Expected result: zero rows (all overlaps are valid expansions).
-- =============================================================================
WITH active_contracts AS (
  SELECT
    account_id,
    contract_id,
    start_date,
    end_date,
    annual_commit_dollars,
    ROW_NUMBER() OVER (
      PARTITION BY account_id
      ORDER BY start_date, annual_commit_dollars
    ) AS contract_rank
  FROM `pan-ahi-casestudy.ahi_case_study.Contracts`
  WHERE end_date >= DATE '2025-01-01'
),
multi_contract AS (
  SELECT account_id
  FROM active_contracts
  GROUP BY account_id
  HAVING COUNT(*) > 1
),
ranked AS (
  SELECT
    ac.*,
    LAG(ac.annual_commit_dollars) OVER (
      PARTITION BY ac.account_id ORDER BY ac.start_date
    ) AS prev_arr,
    LAG(ac.start_date) OVER (
      PARTITION BY ac.account_id ORDER BY ac.start_date
    ) AS prev_start
  FROM active_contracts ac
  INNER JOIN multi_contract mc ON ac.account_id = mc.account_id
)
SELECT
  'overlapping_contracts_check'     AS test_name,
  account_id,
  contract_id,
  start_date,
  annual_commit_dollars,
  prev_arr                          AS prior_contract_arr,
  'Second contract not larger than first — unexpected overlap' AS failure_reason
FROM ranked
WHERE
  contract_rank > 1
  AND annual_commit_dollars <= COALESCE(prev_arr, 0)
  AND start_date > DATE '2025-01-01'
ORDER BY account_id;


-- =============================================================================
-- TEST 3: Negative Consumption Check
-- Returns any rows where compute_credits_consumed is negative.
-- Expected result: zero rows.
-- =============================================================================
SELECT
  'negative_consumption_check'      AS test_name,
  log_id,
  account_id,
  date,
  compute_credits_consumed,
  'Negative compute credits — data entry error' AS failure_reason
FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs`
WHERE compute_credits_consumed < 0
ORDER BY account_id, date;


-- =============================================================================
-- TEST 4: Future Usage Check
-- Returns usage logs dated after Dec 31 2025 (outside contract year).
-- Expected result: 150 seeded rogue-date rows.
-- These are flagged and excluded from AHI — not pipeline-halting.
-- FAIL condition: more than 200 future rows (beyond seeded count).
-- =============================================================================
SELECT
  'future_usage_check'              AS test_name,
  log_id,
  account_id,
  date,
  compute_credits_consumed,
  'Usage date beyond contract year end (2025-12-31)' AS failure_reason
FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs`
WHERE date > DATE '2025-12-31'
ORDER BY date, account_id;


-- =============================================================================
-- TEST 5: Contract Date Usage Check
-- Returns usage logs where the date falls outside the account's
-- active contract date range (before first contract or after last contract).
-- Expected result: ~150 rogue rows (seeded edge case).
-- =============================================================================
WITH contract_bounds AS (
  SELECT
    account_id,
    MIN(start_date) AS earliest_start,
    MAX(end_date)   AS latest_end
  FROM `pan-ahi-casestudy.ahi_case_study.Contracts`
  WHERE end_date >= DATE '2025-01-01'
  GROUP BY account_id
)
SELECT
  'contract_date_usage_check'       AS test_name,
  l.log_id,
  l.account_id,
  l.date,
  l.compute_credits_consumed,
  CASE
    WHEN cb.account_id IS NULL
      THEN 'No active contract found for this account'
    WHEN l.date < cb.earliest_start
      THEN 'Usage before contract start date'
    WHEN l.date > cb.latest_end
      THEN 'Usage after contract end date'
  END                               AS failure_reason
FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs` AS l
LEFT JOIN contract_bounds AS cb ON l.account_id = cb.account_id
WHERE
  l.date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
  AND (
    cb.account_id IS NULL
    OR l.date < cb.earliest_start
    OR l.date > cb.latest_end
  )
ORDER BY l.account_id, l.date;


-- =============================================================================
-- TEST 6: NULL account_id Check
-- Returns any NULL account_ids across all four tables.
-- Expected result: zero rows across all tables.
-- =============================================================================
SELECT 'null_account_id_check' AS test_name, 'Daily_Usage_Logs' AS source_table,
  CAST(NULL AS STRING) AS log_id, account_id, CAST(NULL AS DATE) AS date,
  'NULL account_id in Daily_Usage_Logs' AS failure_reason
FROM `pan-ahi-casestudy.ahi_case_study.Daily_Usage_Logs`
WHERE account_id IS NULL

UNION ALL

SELECT 'null_account_id_check', 'Accounts', NULL, account_id, NULL,
  'NULL account_id in Accounts'
FROM `pan-ahi-casestudy.ahi_case_study.Accounts`
WHERE account_id IS NULL

UNION ALL

SELECT 'null_account_id_check', 'Contracts', NULL, account_id, NULL,
  'NULL account_id in Contracts'
FROM `pan-ahi-casestudy.ahi_case_study.Contracts`
WHERE account_id IS NULL

UNION ALL

SELECT 'null_account_id_check', 'Account_Health', NULL, account_id, NULL,
  'NULL account_id in Account_Health'
FROM `pan-ahi-casestudy.ahi_case_study.Account_Health`
WHERE account_id IS NULL

ORDER BY source_table;
