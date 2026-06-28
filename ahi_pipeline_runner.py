"""
AHI Pipeline Runner — Local Execution
Palo Alto Networks · Global Customer Services

Mirrors the BigQuery SQL pipeline (ahi_pipeline.sql) using pandas.
Use this for local testing and dashboard development.
For production: run ahi_pipeline.sql against BigQuery directly.

Outputs:
  - account_ahi_monthly.csv   → /output_pipeline/
  - csm_ahi_monthly.csv       → /output_pipeline/

Usage:
  python3 ahi_pipeline_runner.py
"""

import pandas as pd
import numpy as np
import os
from datetime import date

INPUT_DIR  = "./output_v2"
OUTPUT_DIR = "./output_pipeline"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 60)
print("AHI Pipeline Runner")
print("=" * 60)

# ── LOAD SOURCE TABLES ───────────────────────────────────────
print("\n[1/6] Loading source tables...")
csm    = pd.read_csv(f"{INPUT_DIR}/CSM_rep.csv")
acc    = pd.read_csv(f"{INPUT_DIR}/Accounts.csv")
con    = pd.read_csv(f"{INPUT_DIR}/Contracts.csv",
                     parse_dates=["start_date","end_date"])
health = pd.read_csv(f"{INPUT_DIR}/Account_Health.csv",
                     parse_dates=["date"])
logs   = pd.read_csv(f"{INPUT_DIR}/Daily_Usage_Logs.csv",
                     parse_dates=["date"])

print(f"  CSM_rep:          {len(csm):>8,} rows")
print(f"  Accounts:         {len(acc):>8,} rows")
print(f"  Contracts:        {len(con):>8,} rows")
print(f"  Account_Health:   {len(health):>8,} rows")
print(f"  Daily_Usage_Logs: {len(logs):>8,} rows")

# ── STEP 1: stg_active_contracts ────────────────────────────
print("\n[2/6] Building stg_active_contracts...")

months = pd.date_range("2025-01-01", "2025-12-01", freq="MS")

contract_rows = []
for _, c in con.iterrows():
    for m in months:
        m_end = m + pd.offsets.MonthEnd(0)
        # Active if contract overlaps this month AND is a 2025 contract
        if (c["start_date"] <= m_end and
            c["end_date"] >= m and
            c["end_date"] >= pd.Timestamp("2025-01-01")):
            contract_rows.append({
                "account_id":               c["account_id"],
                "contract_id":              c["contract_id"],
                "month_start":              m.date(),
                "annual_commit_dollars":    c["annual_commit_dollars"],
                "included_monthly_compute_credits": c["included_monthly_compute_credits"],
            })

active_con = pd.DataFrame(contract_rows)
stg_contracts = active_con.groupby(["account_id","month_start"]).agg(
    committed_monthly_credits=("included_monthly_compute_credits", "max"),
    original_arr=("annual_commit_dollars", "min"),
    current_arr=("annual_commit_dollars", "sum"),
    contract_count=("contract_id", "nunique"),
).reset_index()
stg_contracts["has_expansion"] = stg_contracts["contract_count"] > 1
print(f"  ✓ {len(stg_contracts):,} account-month rows")

# ── STEP 2: stg_monthly_consumption ─────────────────────────
print("\n[3/6] Building stg_monthly_consumption...")

# DQ: exclude orphaned and rogue-date rows
logs_clean = logs.copy()
logs_clean = logs_clean[logs_clean["account_id"].isin(acc["account_id"])]
logs_clean = logs_clean[
    (logs_clean["date"] >= pd.Timestamp("2025-01-01")) &
    (logs_clean["date"] <= pd.Timestamp("2025-12-31"))
]
logs_clean["month_start"] = logs_clean["date"].dt.to_period("M").dt.to_timestamp().dt.date

stg_consumption = logs_clean.groupby(["account_id","month_start"]).agg(
    actual_credits_consumed=("compute_credits_consumed", "sum"),
    active_days=("date", "nunique"),
).reset_index()
print(f"  ✓ {len(stg_consumption):,} account-month rows")
print(f"  ✓ Excluded {len(logs)-len(logs_clean):,} orphaned/rogue rows")

# ── STEP 3: stg_engagement_trend ────────────────────────────
print("\n[4/6] Computing engagement trends (linear regression)...")

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import IsolationForest

# Linear regression slope per account over full year
logs_clean["day_idx"] = (logs_clean["date"] - pd.Timestamp("2025-01-01")).dt.days

trend_rows = []
anomaly_inputs = []

for acc_id, grp in logs_clean.groupby("account_id"):
    if len(grp) < 7:
        # Not enough data — default to flat
        trend_rows.append({
            "account_id": acc_id,
            "slope_per_day": 0,
            "avg_daily": grp["compute_credits_consumed"].mean(),
        })
        continue
    X = grp["day_idx"].values.reshape(-1, 1)
    y = grp["compute_credits_consumed"].values
    model = LinearRegression().fit(X, y)
    trend_rows.append({
        "account_id": acc_id,
        "slope_per_day": model.coef_[0],
        "avg_daily": y.mean(),
    })
    # Build anomaly detection features
    monthly = grp.groupby("month_start")["compute_credits_consumed"].sum()
    m_vals = monthly.values
    anomaly_inputs.append({
        "account_id":    acc_id,
        "variance":      np.var(m_vals) if len(m_vals) > 1 else 0,
        "max_mean_ratio":np.max(m_vals) / (np.mean(m_vals) + 1),
        "m1_share":      m_vals[0] / (np.sum(m_vals) + 1) if len(m_vals) > 0 else 0,
        "zero_months":   np.sum(m_vals < 1),
    })

trend_df = pd.DataFrame(trend_rows)

# Isolation Forest anomaly detection
if anomaly_inputs:
    anom_df   = pd.DataFrame(anomaly_inputs)
    features  = ["variance","max_mean_ratio","m1_share","zero_months"]
    iso       = IsolationForest(contamination=0.05, random_state=42)
    preds     = iso.fit_predict(anom_df[features])
    anom_df["anomaly_flag"] = preds == -1
    trend_df  = trend_df.merge(
        anom_df[["account_id","anomaly_flag"]], on="account_id", how="left"
    )
else:
    trend_df["anomaly_flag"] = False

# Normalise slope to 0-100 trend score
def slope_to_score(row):
    avg = row["avg_daily"]
    if avg == 0:
        return 50
    pct = row["slope_per_day"] / avg
    if   pct >  0.05: return 100
    elif pct >  0.00: return 75
    elif pct > -0.05: return 50
    elif pct > -0.15: return 25
    else:             return 0

trend_df["raw_trend_score"] = trend_df.apply(slope_to_score, axis=1)
trend_df["trend_score"] = trend_df.apply(
    lambda r: round(r["raw_trend_score"] * 0.5, 2) if r["anomaly_flag"]
              else float(r["raw_trend_score"]),
    axis=1
)
n_anomalies = trend_df["anomaly_flag"].sum()
print(f"  ✓ {len(trend_df):,} account trend scores computed")
print(f"  ✓ Isolation Forest flagged {n_anomalies} anomalous accounts (0.5x multiplier applied)")

# ── STEP 4 & 5: dim_account_ahi → account_ahi_monthly ───────
print("\n[5/6] Computing AHI dimension scores...")

# Base join
base = stg_contracts.merge(stg_consumption, on=["account_id","month_start"], how="left")
base["actual_credits_consumed"] = base["actual_credits_consumed"].fillna(0)
base["active_days"]             = base["active_days"].fillna(0)

# ── Dimension 1: Consumption Health ─────────────────────────
base["raw_ratio"] = np.where(
    base["committed_monthly_credits"] > 0,
    base["actual_credits_consumed"] / base["committed_monthly_credits"],
    0
)
base["base_consumption"] = (
    np.minimum(base["raw_ratio"], 1.10) / 1.10 * 100
).round(2)
base["overage_flag"] = base["raw_ratio"] > 1.20
base["consumption_score"] = np.where(
    base["overage_flag"],
    (base["base_consumption"] * 0.85).round(2),
    base["base_consumption"]
)

# ── Dimension 2: Deployment Depth ───────────────────────────
base["month_start_dt"] = pd.to_datetime(base["month_start"])
base["days_in_month"]  = base["month_start_dt"].apply(
    lambda d: (d + pd.offsets.MonthEnd(0) - d).days + 1
)
base["deployment_score"] = (
    np.minimum(base["active_days"], base["days_in_month"])
    / base["days_in_month"] * 100
).round(2)

# ── Dimension 3: Platform Stability ─────────────────────────
health["month_start"] = health["date"].dt.to_period("M").dt.to_timestamp().dt.date
health_score_map = {"Green": 100, "Yellow": 60, "Red": 20}
health["stability_val"] = health["health_color"].map(health_score_map).fillna(20)
stability = health.groupby(["account_id","month_start"])["stability_val"].mean().round(2).reset_index()
stability.columns = ["account_id","month_start","stability_score"]
base = base.merge(stability, on=["account_id","month_start"], how="left")
base["stability_score"] = base["stability_score"].fillna(50)

# ── Dimension 4: Contract Expansion ─────────────────────────
base["expansion_ratio"] = np.where(
    base["original_arr"] > 0,
    base["current_arr"] / base["original_arr"],
    1.0
)
base["expansion_score"] = (
    np.minimum(base["expansion_ratio"], 1.5) / 1.5 * 100
).round(2)

# ── Dimension 5: Engagement Trend ───────────────────────────
base = base.merge(
    trend_df[["account_id","trend_score","anomaly_flag"]],
    on="account_id", how="left"
)
base["trend_score"]  = base["trend_score"].fillna(50)
base["anomaly_flag"] = base["anomaly_flag"].fillna(False)

# ── Composite AHI Score ──────────────────────────────────────
base["ahi_score"] = (
    base["consumption_score"] * 0.25 +
    base["deployment_score"]  * 0.25 +
    base["stability_score"]   * 0.20 +
    base["expansion_score"]   * 0.15 +
    base["trend_score"]       * 0.15
).round(2)

# ── Health Status Label ──────────────────────────────────────
def health_label(score):
    if score >= 80: return "Healthy"
    if score >= 65: return "Monitor"
    if score >= 50: return "At Risk"
    if score >= 35: return "Critical"
    return "Churning"

base["health_status"] = base["ahi_score"].apply(health_label)

# ── Merge account metadata ───────────────────────────────────
account_ahi = base.merge(acc[["account_id","industry","rep_id"]], on="account_id", how="left")
account_ahi["contract_overlap_flag"] = account_ahi["has_expansion"]

# Final column selection
account_ahi_out = account_ahi[[
    "account_id", "month_start", "ahi_score", "health_status",
    "consumption_score", "deployment_score", "stability_score",
    "expansion_score", "trend_score",
    "overage_flag", "anomaly_flag", "contract_overlap_flag",
    "raw_ratio", "industry", "rep_id"
]].rename(columns={"month_start": "month"})

print(f"  ✓ {len(account_ahi_out):,} account-month AHI scores")

status_dist = account_ahi_out["health_status"].value_counts()
for status, cnt in status_dist.items():
    pct = cnt / len(account_ahi_out) * 100
    print(f"    {status:<12} {cnt:>6,} ({pct:.1f}%)")

# ── STEP 6: csm_ahi_monthly ─────────────────────────────────
print("\n[6/6] Rolling up to CSM level (ARR-weighted)...")

csm_base = account_ahi_out.merge(
    acc[["account_id","rep_id"]], on=["account_id","rep_id"], how="left"
).merge(
    stg_contracts[["account_id","month_start","current_arr"]].rename(
        columns={"month_start": "month"}),
    on=["account_id","month"], how="left"
)
csm_base["current_arr"] = csm_base["current_arr"].fillna(0)

def weighted_ahi(grp):
    total_arr = grp["current_arr"].sum()
    if total_arr == 0:
        return grp["ahi_score"].mean()
    return (grp["ahi_score"] * grp["current_arr"]).sum() / total_arr

csm_agg = csm_base.groupby(["rep_id","month"]).apply(
    lambda g: pd.Series({
        "ahi_score":           round(weighted_ahi(g), 2),
        "total_accounts":      g["account_id"].nunique(),
        "accounts_at_risk":    (g["ahi_score"] < 50).sum(),
        "accounts_churning":   (g["health_status"] == "Churning").sum(),
        "total_arr":           round(g["current_arr"].sum(), 0),
        "arr_at_risk":         round(g.loc[g["ahi_score"] < 50, "current_arr"].sum(), 0),
        "upsell_opportunities":g["overage_flag"].sum(),
        "anomaly_accounts":    g["anomaly_flag"].sum(),
    })
).reset_index()

csm_ahi_out = csm_agg.merge(
    csm[["csm_id","name","region","segment"]].rename(columns={"csm_id": "rep_id"}),
    on="rep_id", how="left"
).rename(columns={"rep_id": "csm_id", "name": "csm_name"})

print(f"  ✓ {len(csm_ahi_out):,} CSM-month rows")

# ── SAVE OUTPUTS ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("Saving pipeline outputs...")

account_ahi_out.to_csv(f"{OUTPUT_DIR}/account_ahi_monthly.csv", index=False)
csm_ahi_out.to_csv(f"{OUTPUT_DIR}/csm_ahi_monthly.csv", index=False)

print(f"  ✓ account_ahi_monthly.csv  {len(account_ahi_out):>8,} rows")
print(f"  ✓ csm_ahi_monthly.csv      {len(csm_ahi_out):>8,} rows")

# ── PIPELINE VALIDATION SUMMARY ──────────────────────────────
print("\n" + "=" * 60)
print("Pipeline Output Validation")
print("=" * 60)

# AHI score range
print(f"\n  AHI score range: {account_ahi_out['ahi_score'].min():.1f} – "
      f"{account_ahi_out['ahi_score'].max():.1f}  (expected 0–100)")

# Shelfware accounts should be Churning
shelf_status = account_ahi_out[account_ahi_out["consumption_score"] < 5]["health_status"].value_counts()
print(f"\n  Shelfware accounts (consumption < 5) health status:")
for s, c in shelf_status.items():
    print(f"    {s}: {c}")

# Overage accounts flagged
over_flagged = account_ahi_out["overage_flag"].sum()
print(f"\n  Overage flags set: {over_flagged} account-months")

# Anomaly flags
anom_flagged = account_ahi_out["anomaly_flag"].sum()
print(f"  Anomaly flags set: {anom_flagged} account-months (spike-drop)")

# CSM AHI distribution
print(f"\n  CSM AHI range:  {csm_ahi_out['ahi_score'].min():.1f} – "
      f"{csm_ahi_out['ahi_score'].max():.1f}")
print(f"  ARR at risk per CSM (avg): "
      f"${csm_ahi_out['arr_at_risk'].mean():,.0f}")

print("\n" + "=" * 60)
print("Pipeline complete.")
print(f"Outputs saved to {OUTPUT_DIR}/")
print("=" * 60)
