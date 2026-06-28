# pan-ahi-casestudy

**Account Health Index (AHI) — North Star Metric for PAN Global Customer Services**

Built as part of the Principal IT PM, Data Analytics case study. This repo contains the full AI-assisted implementation of a composite health metric for GCS transitioning from TCV/Bookings to an ARR + consumption model.

---

## What Was Built

| Deliverable | Location | Description |
|---|---|---|
| Product & Technical Spec | `/specs/AHI_Spec.md` | 14-section PRD defining formula, weights, edge case handling, DQ tests, evaluation framework |
| Data Generation | `/data_generation/generate_data_FINAL.py` | Python script generating 5 synthetic tables (1,000 accounts, 214K+ usage rows, 5 deliberate edge cases) |
| BigQuery SQL Pipeline | `/pipeline_and_tests/ahi_pipeline_bigquery.sql` | 6-step SQL pipeline: source tables → staging → account_ahi_monthly + csm_ahi_monthly |
| Local Python Pipeline | `/pipeline_and_tests/ahi_pipeline_runner.py` | Pandas mirror of BigQuery pipeline for local development |
| BigQuery DQ Tests | `/pipeline_and_tests/ahi_dq_tests_bigquery.sql` | 6 SQL assertions that run before every pipeline execution |
| Python DQ Tests | `/pipeline_and_tests/ahi_dq_tests.py` | Development-time quality gate against CSV files |
| Live Dashboard | `/dashboard/dashboard.html` | 3-view HTML dashboard connected to BigQuery via Node.js proxy |
| Dashboard Proxy | `/dashboard/server.js` | Express server authenticating with BigQuery service account |

---

## AHI Formula

```
AHI = (Consumption Health  × 0.25)
    + (Deployment Depth    × 0.25)
    + (Platform Stability  × 0.20)
    + (Contract Expansion  × 0.15)
    + (Engagement Trend    × 0.15)
```

Scored 0–100 per account per month. Rolled up to CSM level as ARR-weighted average.

| AHI Score | Status | Action |
|---|---|---|
| 80–100 | Healthy | Maintain cadence |
| 65–79 | Monitor | 30-day check-in |
| 50–64 | At Risk | 60-day recovery plan |
| 35–49 | Critical | Executive engagement |
| Below 35 | Churning | Immediate escalation |

---

## BigQuery Setup

**Project**: `pan-ahi-casestudy`
**Dataset**: `ahi_case_study`

### Source tables (uploaded from `/data_generation/` CSVs)
- `CSM_rep` — 50 CSMs
- `Accounts` — 1,000 accounts
- `Contracts` — 1,200+ contracts
- `Account_Health` — 50,000 daily health snapshots
- `Daily_Usage_Logs` — 214,000+ daily usage rows

### Pipeline output tables
- `stg_active_contracts` — clean contract baseline per account per month
- `stg_monthly_consumption` — monthly credits per account
- `stg_engagement_trend` — linear regression slope + Isolation Forest anomaly flags
- `dim_account_ahi` — all 5 dimension scores per account per month
- `account_ahi_monthly` — composite AHI score (12,000 rows: 1,000 accounts × 12 months)
- `csm_ahi_monthly` — ARR-weighted CSM rollup (600 rows: 50 CSMs × 12 months)

### Running the pipeline

Open BigQuery query editor and run each step in `/pipeline_and_tests/ahi_pipeline_bigquery.sql` in order (Steps 1–6). Each step depends on the previous.

---

## Running the Dashboard Locally

The dashboard connects live to BigQuery via a Node.js proxy server.

### Prerequisites
- Node.js v18+
- A Google Cloud service account JSON key with `BigQuery Data Viewer` and `BigQuery Job User` roles

### Setup

```bash
cd dashboard
npm install
cp /path/to/your-service-account-key.json credentials.json
```

### Start the proxy

```bash
node server.js
```

Proxy runs on `http://localhost:3001`

### Open the dashboard

```bash
open dashboard.html
```

Or open `dashboard.html` directly in Chrome.

### Dashboard views

- **Executive view** — Portfolio AHI, ARR at risk, status distribution chart, AHI by region, regional summary
- **CSM leaderboard** — 50 CSMs ranked by AHI ascending, filterable by region and segment
- **Account detail** — 1,000 accounts with dimension score bars, status badges, overage and anomaly flags

---

## Data Quality Tests

### BigQuery SQL tests (production gate)

Run `/pipeline_and_tests/ahi_dq_tests_bigquery.sql` before every pipeline execution.
Each query returns zero rows on pass. Any rows returned = investigation required before pipeline runs.

| Test | What It Catches |
|---|---|
| orphaned_usage_check | Usage logs with no matching account in Accounts table |
| overlapping_contracts_check | Unexpected contract overlaps (not legitimate expansions) |
| negative_consumption_check | Negative compute credit values |
| future_usage_check | Usage dates beyond Dec 31 2025 |
| contract_date_usage_check | Usage outside active contract date range |
| null_account_id_check | NULL account_ids in any table |

### Python tests (development gate)

```bash
python3 ahi_dq_tests.py
```

Runs against CSV files before BigQuery upload. Outputs quarantine log and JSON report.

---

## Edge Cases

| Edge Case | Prevalence | How AHI Handles It |
|---|---|---|
| Spike & Drop | ~5% of accounts | Isolation Forest flags; Engagement Trend × 0.5 |
| Shelfware | ~10% of accounts | Consumption + Deployment both score near zero → AHI floors at ~21 |
| Consistent Overages | ~15% of accounts | Consumption score × 0.85 penalty above 120% |
| Mid-Year Expansions | ~40 accounts | Committed credits denominator resets at expansion start date |
| Orphaned Usage | ~300 rows | DQ layer excludes before AHI calculation |

---

## AI Components

- **Isolation Forest** — unsupervised anomaly detection on monthly usage patterns. Contamination=0.05. Flags spike-and-drop accounts with 0.5× Engagement Trend multiplier.
- **Claude API** — LLM narrative generation for accounts with AHI < 80. Plain-English health summaries surface the "why" behind the score. Presence of narrative is itself a signal.
- **AI-assisted development** — spec, pipeline SQL, DQ tests, and dashboard all generated via Claude with iterative human review and validation.

---

## Repo Structure

```
/data_generation
  generate_data_FINAL.py       ← synthetic data generation

/specs
  AHI_Spec.md                  ← full product & technical specification

/pipeline_and_tests
  ahi_pipeline_bigquery.sql    ← BigQuery SQL pipeline (Steps 1–6)
  ahi_pipeline_runner.py       ← local Python pipeline mirror
  ahi_dq_tests_bigquery.sql    ← BigQuery SQL DQ assertions
  ahi_dq_tests.py              ← Python DQ tests

/dashboard
  dashboard.html               ← live BigQuery dashboard
  server.js                    ← Node.js BigQuery proxy

README.md
```

---

*Palo Alto Networks · Principal IT PM, Data Analytics · Case Study — June 2026*
