# Account Health Index (AHI)
## North Star Metric — Product & Technical Specification
**Palo Alto Networks · Global Customer Services · Principal IT PM Initiative**
*Version 2.0 · June 2026*

---

## 1. Context & Problem Statement

Palo Alto Networks' Global Customer Services (GCS) organization is transitioning from a traditional upfront Bookings and Total Contract Value (TCV) model to an Annual Recurring Revenue (ARR) model with hybrid consumption-based pricing.

The existing success metrics do not capture the behaviors that drive long-term customer retention and revenue expansion. A customer may sign a large contract but never deploy the product, or may consume heavily in month one and then go dark. Neither scenario is visible in TCV alone.

GCS leadership needs a single North Star metric that balances four dimensions:
- Initial contract deployment — are purchased products actively in use?
- Consumption health — is the customer consuming committed compute credits at a sustainable rate?
- Platform stability — is the technical experience clean?
- Engagement trajectory — is usage trending up, flat, or declining?

---

## 2. Data Strategy

### 2.1 Why Synthetic Data

PAN's proprietary customer data cannot be shared in a case study context. Synthetic data enables a more rigorous design process — the dataset was co-designed with the metric, with every table structure, edge case, and anomaly rate chosen to stress-test AHI's design assumptions.

### 2.2 Generation Approach

Generated using Python (Faker + Pandas) with AI-assisted development via Claude. Spec written first as a Markdown document before a single line of code was written.

| Table | Row Count | Design Purpose |
|---|---|---|
| CSM_rep | ~50 rows | Rollup hierarchy for comp calculations. Segmented by Enterprise and Mid-Market. |
| Accounts | ~1,000 rows | Master account list. Referential integrity anchor. |
| Contracts | ~1,200 rows | Supports mid-year expansion edge case. Contains committed credits denominator. |
| Account_Health | ~50,000 rows | Daily health snapshots. Reconciliation check against Daily_Usage_Logs. |
| Daily_Usage_Logs | ~200,000 rows | Granular daily consumption. Primary input for Consumption Health and Engagement Trend. |

### 2.3 Deliberate Edge Case Design

| Edge Case | Prevalence | Detection | What Breaks Without It |
|---|---|---|---|
| Spike & Drop | ~5% of accounts | Engagement Trend (0.5× anomaly multiplier via Isolation Forest) | Point-in-time metric scores spike-drop as Healthy in month 1 |
| Shelfware | ~10% of accounts | Deployment Depth + Consumption Health (both score near zero) | ARR-only metric shows these as high-value |
| Consistent Overages | ~15% of accounts | Consumption Health (0.85× penalty above 120%) | No CSM incentive to right-size contracts |
| Mid-Year Expansions | ~40 accounts | Contract Expansion (resets committed_credits baseline) | Wrong denominator corrupts consumption ratio |
| Orphaned/Rogue Usage | ~300 rows | DQ test layer (excluded before AHI runs) | Orphaned usage inflates consumption scores |

### 2.4 Data Quality Assurance

Quality enforced at two levels:
- **Generation-time**: referential integrity enforced in Python script
- **Pipeline-time**: six automated DQ assertions halt the pipeline on failure

### 2.5 Alignment to Business Use Case

The dataset was co-designed with the metric in this sequence:
1. Define the business question
2. Identify real-world data pathologies
3. Design metric dimensions to handle each pathology
4. Generate synthetic data with each pathology at realistic prevalence
5. Validate metric handles each pathology correctly

### 2.6 Explicit Assumptions

| Assumption | Value Used | Rationale | How to Validate in Production |
|---|---|---|---|
| Mid-year expansion count | 40 accounts (4%) | Brief says "several" — 4% reflects realistic mid-year upsell rate | Pull actual mid-year amendments from Salesforce CPQ |
| Definition of "high" ARR for shelfware | Above portfolio median (~$1.97M) | Relative definition scales with portfolio composition | Define as above 50th percentile of active ARR |
| Shelfware ARR range | $2M–$5M | Shelfware accounts are forced to Enterprise-tier ARR | Confirm against real shelfware accounts in CRM |
| Spike & drop definition | Month 1 > 90% of annual credits; Month 2+ < 2% of daily baseline | Brief specifies 90% explicitly | Validate against real usage patterns |
| Consistent overage threshold | Avg monthly > 120% of committed credits | Brief specifies 120%+ explicitly | Confirm against PAN's actual overage billing logic |
| Amendment contracts | 163 prior-year (2024) contracts, non-overlapping | Added to reach ~1,200 contract row target | Filter to current year contracts in production |
| Orphaned usage volume | 300 rows total | "A few hundred" per brief | Audit actual orphaned rows in production log table |
| Account_Health row structure | 50 daily snapshots per account | Target ~50,000 rows | Daily aggregate in production |
| CSM segment distribution | 31 Enterprise / 19 Mid-Market (random) | No distribution guidance given | Align to actual PAN CS headcount split |
| Date range | Jan 1 2025 – Dec 31 2025 (12 months) | Brief requires "at least 12 months" | Extend to 24 months in production |

---

## 3. Data Model & Output Table Schema

**Storage layer**: Google BigQuery Sandbox (free tier). BigQuery selected for analytical aggregation performance at scale.

### 3.1 Data Model Overview

| Table | Primary Key | Role in AHI | Joins To |
|---|---|---|---|
| CSM_rep | csm_id | Master list of all Customer Success Managers | Accounts via rep_id |
| Accounts | account_id | Master account list. Referential integrity anchor. | CSM_rep via rep_id = csm_id |
| Contracts | contract_id | Annual committed spend and included compute credits | Accounts via account_id |
| Account_Health | account_id + date | Monthly health color and aggregate consumption | Accounts via account_id |
| Daily_Usage_Logs | log_id | Granular daily compute credit consumption | Accounts via account_id |

**Key join note**: `csm_id` does not appear in Contracts, Account_Health, or Daily_Usage_Logs. To attribute usage to a CSM, the pipeline joins through Accounts as the bridge: `Daily_Usage_Logs → Accounts (account_id) → CSM_rep (rep_id = csm_id)`.

### 3.2 account_ahi_monthly

| Column | Type | Description |
|---|---|---|
| account_id | STRING | Foreign key to Accounts table |
| month | DATE | First day of the calculation month |
| ahi_score | FLOAT64 | Composite AHI score (0–100) |
| consumption_score | FLOAT64 | Dimension 1 score (0–100) |
| deployment_score | FLOAT64 | Dimension 2 score (0–100) |
| stability_score | FLOAT64 | Dimension 3 score (0–100) |
| expansion_score | FLOAT64 | Dimension 4 — Contract Expansion (0–100) |
| trend_score | FLOAT64 | Dimension 5 — Engagement Trend (0–100) |
| overage_flag | BOOLEAN | TRUE if raw_ratio > 1.20 |
| anomaly_flag | BOOLEAN | TRUE if Isolation Forest detected anomalous pattern |
| contract_overlap_flag | BOOLEAN | TRUE if overlapping active contracts exist |

### 3.3 csm_ahi_monthly

| Column | Type | Description |
|---|---|---|
| csm_id | STRING | Foreign key to CSM_rep table |
| month | DATE | First day of the calculation month |
| ahi_score | FLOAT64 | ARR-weighted AHI across book of business |
| accounts_at_risk | INT64 | Count of accounts with AHI < 50 |
| total_arr | FLOAT64 | Total ARR in CSM's book |
| arr_at_risk | FLOAT64 | ARR from accounts with AHI < 50 |
| upsell_opportunities | INT64 | Accounts with overage_flag = TRUE |
| anomaly_accounts | INT64 | Accounts with anomaly_flag = TRUE |

---

## 4. Data Quality Tests

Six automated assertions run before every AHI pipeline execution. Any FAIL halts the pipeline.

| Test Name | Logic | Failure Action |
|---|---|---|
| orphaned_usage_check | Usage logs with account_id not in Accounts (excluding seeded GHOST_ rows) | Exclude orphaned rows; flag in output |
| overlapping_contracts_check | Accounts with 2+ active 2025 contracts where second is NOT larger mid-year expansion | Flag account; use most recent contract |
| negative_consumption_check | All compute_credits_consumed >= 0 | Reject rows; alert data engineering |
| future_usage_check | No usage log date > 2025-12-31 (beyond 200 rows triggers FAIL) | Flag as rogue usage; exclude from AHI |
| contract_date_usage_check | Usage date falls within account's active contract date range | Flag as rogue usage; exclude from AHI |
| null_account_id_check | No NULL account_ids in any table | Reject rows |

**Two-layer DQ framework**:
- Layer 1 — Python assertions (`ahi_dq_tests.py`): run at generation time against CSV files before BigQuery upload
- Layer 2 — BigQuery SQL assertions (`ahi_dq_tests_bigquery.sql`): run against live tables before every pipeline execution

---

## 5. Metric Definition

### 5.1 Name
Account Health Index (AHI)

### 5.2 Formula

```
AHI = (Consumption Health  × 0.25)
    + (Deployment Depth    × 0.25)
    + (Platform Stability  × 0.20)
    + (Contract Expansion  × 0.15)
    + (Engagement Trend    × 0.15)
```

Scored 0–100. Calculated monthly per `account_id`. Rolled up to `csm_id` as ARR-weighted average.

### 5.3 Weight Rationale

| GCS Business Question | AHI Dimension(s) | Weight |
|---|---|---|
| What's purchased vs. consumed? | Consumption Health + Deployment Depth | 0.25 + 0.25 = 50% |
| Technical health (support tickets)? | Platform Stability | 0.20 = 20% |
| Overall product platform usage? | Engagement Trend + Contract Expansion | 0.15 + 0.15 = 30% |
| Balance initial contract bookings? | Contract Expansion | 0.15 = 15% |

One-sentence rationale per dimension:
- **Consumption (0.25)** — Are they using what they paid for?
- **Deployment (0.25)** — Have they even turned it on?
- **Platform Stability (0.20)** — Is the technical experience clean?
- **Contract Expansion (0.15)** — Is the relationship growing?
- **Engagement Trend (0.15)** — Is usage trending up or down?

### 5.4 Health Status Classification

**Good = AHI ≥ 80.** An account is healthy when it has deployed purchased products, is consuming credits sustainably, maintains a clean support record, shows contract growth, and has stable or rising usage.

| AHI Score | Status | Renewal Risk | CSM Action |
|---|---|---|---|
| 80–100 | Healthy | Low | Maintain cadence. Identify expansion signals. |
| 65–79 | Monitor | Moderate | Diagnose lagging dimension. 30-day check-in. |
| 50–64 | At Risk | High | Escalate to CSM manager. 60-day recovery plan. |
| 35–49 | Critical | Very High | Executive sponsor engagement. 2-week intervention. |
| Below 35 | Churning | Imminent | Immediate escalation to VP CS. Contract review. |

**Why 80 is the Healthy threshold — grounded in PAN's own data:**

PAN's Q4 FY2025 and Q2 FY2026 earnings calls report platform customers retain at 120% NRR with low single-digit churn. An account scoring 80+ on AHI exhibits the behavioral profile of a platform customer: deployed, consuming, growing, and stable. The 80 threshold is calibrated to that profile — not an arbitrary round number.

During the 90-day shadow period, this threshold will be validated against actual renewal outcomes and recalibrated if the empirical breakpoint differs.

### 5.5 Dimension Definitions

**Dimension 1: Consumption Health (weight 0.25)**
```
raw_ratio = actual_credits_consumed / committed_monthly_credits
capped_ratio = LEAST(raw_ratio, 1.10)
consumption_score = (capped_ratio / 1.10) × 100

-- Overage penalty when raw_ratio > 1.20:
final_score = IF raw_ratio > 1.20 THEN consumption_score × 0.85 ELSE consumption_score
```

**Dimension 2: Deployment Depth (weight 0.25)**
```
deployment_score = (products_with_active_usage / products_purchased) × 100
```
A product is actively deployed if it has at least one log entry in the trailing 30 days.

**Dimension 3: Platform Stability (weight 0.20)**
```
weighted_tickets = (P1_open × 3) + (P2_open × 2) + (P3_open × 1)
stability_score = MAX(0, 100 - ((weighted_tickets / baseline) × 100))
```
Proxy in synthetic data: Account_Health color (Green=100, Yellow=60, Red=20).

**Dimension 4: Contract Expansion (weight 0.15)**
```
expansion_ratio = current_arr / original_arr
expansion_score = MIN(expansion_ratio, 1.5) / 1.5 × 100
```

**Dimension 5: Engagement Trend (weight 0.15)**

120-day linear regression slope on daily compute credits consumed, normalized to 0–100:
```
slope > +5%/month  → 100  (strong growth)
slope > 0          → 75   (flat/slight growth)
slope > -5%/month  → 50   (slight decline)
slope > -15%/month → 25   (moderate decline)
else               → 0    (steep decline)
```
Isolation Forest anomaly flag applies 0.5× multiplier to final trend score.

---

## 6. Edge Case Handling

| Edge Case | Detection Logic | AHI Impact | CSM Action Signal |
|---|---|---|---|
| Spike & Drop | Isolation Forest: M1 share > 70% of annual → 0.5× trend multiplier | Trend score halved. Overall AHI drops 10–15 pts. | Escalate for re-engagement plan |
| Shelfware | Deployment = 0, Consumption ≈ 0 | AHI floors at 15–25 (Stability + Trend only) | Flag for deployment health review |
| Consistent Overages | raw_ratio > 1.20 → 0.85× penalty on Consumption | Consumption score reduced ~15% | CSM to initiate right-size conversation |
| Mid-Year Expansions | New contract resets committed_credits denominator from expansion start_date | Consumption ratio recalculated against new baseline | No action needed — expansion is positive |
| Orphaned/Rogue Usage | DQ test catches missing account_ids or out-of-range dates | Excluded entirely from AHI calculation | Route to data engineering for audit |

---

## 7. Rollup & Aggregation Logic

### 7.1 Account Level
AHI calculated monthly per `account_id`.

### 7.2 CSM Level
```
csm_ahi = SUM(account_ahi × account_arr) / SUM(account_arr)
```
ARR-weighting ensures large at-risk accounts have appropriate influence.

### 7.3 Regional Rollup
ARR-weighted average of all CSM-level AHI scores within the region.

---

## 8. AI Components

### 8.1 Anomaly Detection — Isolation Forest (Engagement Trend modifier)

- **Model**: sklearn IsolationForest, contamination=0.05
- **Features**: daily_credits variance, max-to-mean ratio, month-1 consumption share, consecutive zero-usage days
- **Output**: binary anomaly flag per account
- **Score impact**: anomaly_flag = TRUE → Engagement Trend score × 0.50

**Trade-off rationale**: hard override to zero rejected because it treats a recovering spike-and-drop account identically to one in active freefall. The 0.50 multiplier preserves directional signal.

### 8.2 LLM Narrative Generation — Claude API

For accounts with AHI < 80, a plain-English health narrative is generated via Claude API and displayed in the dashboard.

**Design principle**: the AI speaks up when it matters and stays quiet when it doesn't. Narratives only fire below 80 — their presence is itself a signal.

**Human-in-the-loop**: the narrative is a recommendation, not a command. CSM reads, decides, and logs the outcome. Override data feeds back into the shadow period calibration dataset.

---

## 9. Dashboard Specification

Three views connected to live BigQuery output via Node.js proxy:

### 9.1 Design Principles
- Executive-first information hierarchy
- Action-oriented: accounts requiring intervention surface first
- AI narratives only for AHI < 80
- Color as signal: Healthy (green) → Monitor (yellow) → At Risk (amber) → Critical (red) → Churning (dark red)

### 9.2 View 1 — Executive (VP CS audience)
Portfolio AHI, ARR at risk, accounts by status chart, AHI by region chart, regional summary table. Filterable by Region and Segment.

### 9.3 View 2 — CSM Rep (CSM audience)
Book of business ranked by AHI ascending (worst first). Columns: CSM name, region, segment, AHI score, accounts, at-risk count, ARR at risk, upsell opportunities, anomaly accounts.

### 9.4 View 3 — Account Detail (drill-down)
Per-account view with dimension score bars (C·D·S·E·T), status badge, ARR, overage and anomaly flags. Filterable by status and industry.

### 9.5 Technical Implementation
- **Stack**: HTML + Chart.js + Node.js proxy (Express + @google-cloud/bigquery)
- **Authentication**: service account JSON key, BigQuery Data Viewer + Job User roles
- **Data connection**: live queries to `account_ahi_monthly` and `csm_ahi_monthly` in BigQuery
- **Local demo**: `node server.js` → `open dashboard.html`

---

## 10. Compensation Translation

| AHI Score | Variable Comp Payout | Interpretation |
|---|---|---|
| 80–100 | 100% | Fully healthy book |
| 65–79 | 85% | Mostly healthy — minor gaps |
| 50–64 | 70% | At-risk accounts requiring attention |
| Below 50 | 50% + improvement plan | Significant book health issues |

### 10.1 Inherited Book Protection
CSMs inheriting an existing book are evaluated on AHI **delta** over first 180 days, not absolute score.

### 10.2 Shadow Period
AHI runs in parallel with existing TCV metrics for 90 days before comp is tied to it. CSMs see their score but comp is not affected. Used to calibrate weights and catch gaming before financial consequences.

---

## 11. Evaluation & Validation Framework

**AHI is a leading indicator. Renewal rate is the lagging validator.**

| Layer | Question | Method | Success Threshold | Timing |
|---|---|---|---|---|
| Layer 1 — Construct Validity | Does each dimension measure what we claim? | 6 automated DQ tests. Cross-validate Consumption against Account_Health. | All 6 DQ tests pass. Variance < 2%. | Before every pipeline run |
| Layer 2 — Concurrent Validity | Does AHI agree with CS expert judgment? | Shadow period: AHI vs. known at-risk accounts blind review. | < 30% disagreement rate. | Month 1 of shadow period |
| Layer 3 — Predictive Validity | Does AHI predict actual renewal outcomes? | After 12 months: correlate AHI 90 days pre-renewal against actual outcome. | AHI ≥ 80 predicts renewal at ≥ 70% precision. | Month 12 post-deployment |

### 11.1 Business KPI Alignment
- **Renewal rate improvement**: 15pp improvement in At Risk account renewal rate within 12 months
- **Time to intervention**: average days to CSM action after At Risk flag — target < 14 days
- **CSM adoption rate**: ≥ 70% of CSMs logging AHI-triggered action per week within 60 days

### 11.2 The Hard Truth
AHI v1 weights are hypotheses, not validated answers. The shadow period exists to test them. If Engagement Trend proves the strongest churn predictor, its weight will be recalibrated from 0.15 to a higher value before comp is attached.

---

## 12. Architecture Trade-offs

| Decision | Choice Made | Alternative Rejected | Rationale |
|---|---|---|---|
| Metric type | Weighted composite (AHI) | ML churn prediction model | No labeled training data. Explainability required when comp is attached. A CSM cannot appeal a 73% churn probability. |
| Storage layer | Google BigQuery (columnar) | Postgres / Snowflake | Analytical aggregation problem, not transactional. BigQuery Sandbox is free. |
| Dashboard framework | HTML + Chart.js + Node.js proxy | Streamlit | Executive audience requires UX control Streamlit cannot provide. |
| Trend calculation | Linear regression slope (120-day) | ARIMA / Prophet | ARIMA answers "what comes next?" We need "which direction?" Simplest model for the question. |
| Anomaly detection | Isolation Forest (unsupervised) | Rules-based threshold | Rules require manual calibration per segment. IF learns normal distribution from data. |
| Weight derivation | Business-logic weights (v1 hypothesis) | Statistically derived weights | No labeled historical dataset exists. Shadow period produces it for v2. |

---

## 13. Retrospective & Future State

### 13.1 What v2 Looks Like

**Addition 1: LLM intervention briefs**
Full intervention package per account: narrative + draft CSM outreach email + recommended escalation contact + suggested next-call agenda. One Claude API call. CSM approves in one click.

**Addition 2: Agentic intervention triggers**
When account crosses from Healthy into Monitor, an agent detects the threshold crossing, drafts outreach, identifies escalation contact, and queues for CSM approval — without the CSM having to check the dashboard first.

**Addition 3: Multimodal signal enrichment**
Support ticket text analyzed by LLM for sentiment and urgency signals. QBR notes parsed for competitive mentions. Call transcripts flagged for churn language. Feeds into Platform Stability more richly than ticket count alone.

### 13.2 What Would Be Built Differently

- Start with LLM narrative layer from day one — it drives CSM behavior change
- Use dbt for SQL pipeline (lineage, documentation, testability)
- Instrument CSM actions (acted/dismissed/escalated) from day one as feedback loop
- Involve a CS leader as co-designer from week one, not reviewer at the end

### 13.3 Closing Framing

AHI v1 is not a finished product. It is the right first thing to build: a trusted, explainable, CSM-facing metric with a clean data foundation, automated quality gates, and an AI layer that adds value without adding opacity. You cannot build an agentic CSM assistant without a trusted metric underneath it. The agentic layer is v2. The foundation is already there.

---

## 14. Open Questions for VP Review

1. Should the Contract Expansion dimension use a 1.5× cap or be graduated (e.g., 1.2× = 80 pts, 1.5× = 100 pts)?
2. Should the overage penalty (0.85×) be graduated rather than binary?
3. Should Platform Stability incorporate ticket age (days open) in addition to count and severity?
4. What is the right ARR floor for an account to be included in CSM AHI rollup?
5. Should AHI be calculated weekly for Enterprise accounts and monthly for Mid-Market?

---

*End of specification — v2.0*
