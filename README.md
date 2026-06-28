Here's the full README — copy everything below this line:

pan-ahi-casestudy
Account Health Index (AHI) — North Star Metric for PAN Global Customer Services
Built as part of the Principal IT PM, Data Analytics case study. This repo contains the full AI-assisted implementation of a composite health metric for GCS transitioning from TCV/Bookings to an ARR + consumption model.
AHI Formula
AHI = (Consumption Health  × 0.25)
    + (Deployment Depth    × 0.25)
    + (Platform Stability  × 0.20)
    + (Contract Expansion  × 0.15)
    + (Engagement Trend    × 0.15)
Scored 0–100 per account per month. Rolled up to CSM level as ARR-weighted average.
Repo Structure
/data_generation
  generate_data_FINAL.py

/specs
  AHI_Spec.md

/pipeline_and_tests
  ahi_pipeline_bigquery.sql
  ahi_pipeline_runner.py
  ahi_dq_tests_bigquery.sql
  ahi_dq_tests.py

/dashboard
  dashboard.html
  server.js

README.md
BigQuery Setup
Project: pan-ahi-casestudy / Dataset: ahi_case_study
Source tables: CSM_rep, Accounts, Contracts, Account_Health, Daily_Usage_Logs
Output tables: account_ahi_monthly (12,000 rows), csm_ahi_monthly (600 rows)
Running the Dashboard
node dashboard/server.js
open dashboard/dashboard.html
Proxy runs on localhost:3001 and connects live to BigQuery.
Edge Cases Handled

Spike and Drop — Isolation Forest anomaly flag, Engagement Trend x 0.5
Shelfware — Consumption and Deployment both score near zero
Consistent Overages — Consumption score x 0.85 penalty above 120%
Mid-Year Expansions — committed credits denominator resets at expansion date
Orphaned Usage — DQ layer excludes before AHI calculation

Palo Alto Networks · Principal IT PM, Data Analytics · Case Study — June 2026
