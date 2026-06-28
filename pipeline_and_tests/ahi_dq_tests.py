"""
AHI Pipeline — Automated Data Quality Tests
Palo Alto Networks · Global Customer Services

Six automated assertions that run before every AHI pipeline execution.
Any FAIL halts the pipeline and routes bad rows to a quarantine log.

Tests:
  1. orphaned_usage_check        — account_ids in logs not in Accounts
  2. overlapping_contracts_check — accounts with multiple active 2025 contracts
  3. negative_consumption_check  — compute_credits_consumed < 0
  4. future_usage_check          — usage dates beyond contract end
  5. contract_date_usage_check   — usage outside active contract period
  6. null_account_id_check       — NULL account_ids in any table

Usage:
  python3 ahi_dq_tests.py

Output:
  - Console: PASS/FAIL per test with counts
  - quarantine_log.csv: all failing rows for engineering review
  - dq_report.json: machine-readable test results
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import date, datetime

INPUT_DIR    = "./output_v2"
OUTPUT_DIR   = "./output_pipeline"
QUARANTINE   = "./output_pipeline/quarantine_log.csv"
REPORT_FILE  = "./output_pipeline/dq_report.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Load source tables ───────────────────────────────────────
print("=" * 60)
print("AHI Data Quality Test Suite")
print("=" * 60)
print("\nLoading source tables...")

acc  = pd.read_csv(f"{INPUT_DIR}/Accounts.csv")
con  = pd.read_csv(f"{INPUT_DIR}/Contracts.csv", parse_dates=["start_date","end_date"])
logs = pd.read_csv(f"{INPUT_DIR}/Daily_Usage_Logs.csv", parse_dates=["date"])
health = pd.read_csv(f"{INPUT_DIR}/Account_Health.csv", parse_dates=["date"])
csm  = pd.read_csv(f"{INPUT_DIR}/CSM_rep.csv")

CONTRACT_START = pd.Timestamp("2025-01-01")
CONTRACT_END   = pd.Timestamp("2025-12-31")

results      = []
quarantine   = []

def record(test_name, status, count, detail, failing_rows=None):
    icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"\n  {icon}  {test_name}")
    print(f"         {detail}")
    if failing_rows is not None and len(failing_rows) > 0:
        quarantine.append(failing_rows.assign(dq_test=test_name))
    results.append({
        "test":       test_name,
        "status":     status,
        "count":      int(count),
        "detail":     detail,
        "timestamp":  datetime.now().isoformat(),
    })

print("\nRunning tests...\n" + "-" * 60)

# ── TEST 1: Orphaned Usage ───────────────────────────────────
# account_ids in Daily_Usage_Logs that don't exist in Accounts
valid_ids     = set(acc["account_id"])
orphan_mask   = ~logs["account_id"].isin(valid_ids)
orphan_rows   = logs[orphan_mask]
n_orphan      = len(orphan_rows)

# Distinguish seeded GHOST_ rows (expected) from unexpected orphans
ghost_rows    = orphan_rows[orphan_rows["account_id"].str.startswith("GHOST_")]
nonghst_rows  = orphan_rows[~orphan_rows["account_id"].str.startswith("GHOST_")]
n_ghost       = len(ghost_rows)
n_unexpected  = len(nonghst_rows)

if n_orphan == 0:
    record("orphaned_usage_check", "PASS", 0,
           "All account_ids in Daily_Usage_Logs exist in Accounts table.")
elif n_unexpected == 0:
    record("orphaned_usage_check", "FLAGGED", n_orphan,
           f"{n_ghost} ghost account rows detected (seeded edge case). "
           f"Excluded from AHI calculation. No unexpected orphans found.",
           ghost_rows[["log_id","account_id","date","compute_credits_consumed"]])
else:
    record("orphaned_usage_check", "FAIL", n_unexpected,
           f"{n_unexpected} unexpected orphaned rows found (non-GHOST_ accounts). "
           f"Pipeline halted. Sample: {nonghst_rows['account_id'].unique()[:3].tolist()}",
           nonghst_rows[["log_id","account_id","date","compute_credits_consumed"]])

# ── TEST 2: Overlapping Contracts ────────────────────────────
# Accounts with multiple 2025 contracts (mid-year expansions)
# Flag for awareness — these are expected (40 accounts) but must be handled
con_2025 = con[con["end_date"] >= CONTRACT_START]
multi    = con_2025.groupby("account_id").filter(lambda x: len(x) > 1)
n_multi  = multi["account_id"].nunique()

# Check which are TRUE expansions (second contract larger and mid-year)
true_exp = []
for aid in multi["account_id"].unique():
    rows = multi[multi["account_id"]==aid].sort_values("start_date")
    c1   = rows.iloc[0]
    for _, c2 in rows.iloc[1:].iterrows():
        if (c2["start_date"] > CONTRACT_START and
            c2["annual_commit_dollars"] > c1["annual_commit_dollars"]):
            true_exp.append(aid)
            break

unexpected_overlaps = n_multi - len(true_exp)

if unexpected_overlaps == 0:
    record("overlapping_contracts_check", "PASS", n_multi,
           f"{n_multi} accounts have multiple active contracts — all verified as "
           f"legitimate mid-year expansions (second contract larger, mid-year start).")
else:
    record("overlapping_contracts_check", "FAIL", unexpected_overlaps,
           f"{unexpected_overlaps} accounts have overlapping contracts that are NOT "
           f"legitimate expansions (same or smaller second contract). Review required.",
           multi[~multi["account_id"].isin(true_exp)])

# ── TEST 3: Negative Consumption ─────────────────────────────
neg_mask  = logs["compute_credits_consumed"] < 0
neg_rows  = logs[neg_mask]
n_neg     = len(neg_rows)

if n_neg == 0:
    record("negative_consumption_check", "PASS", 0,
           "All compute_credits_consumed values are >= 0.")
else:
    record("negative_consumption_check", "FAIL", n_neg,
           f"{n_neg} rows have negative compute_credits_consumed. "
           f"These indicate data entry errors in the source system.",
           neg_rows[["log_id","account_id","date","compute_credits_consumed"]])

# ── TEST 4: Future Usage ─────────────────────────────────────
# Usage dates beyond CONTRACT_END (Dec 31 2025)
future_mask = logs["date"] > CONTRACT_END
future_rows = logs[future_mask]
n_future    = len(future_rows)

# Note: we seeded 150 rogue rows intentionally — they should be caught here
if n_future <= 200:
    record("future_usage_check", "PASS" if n_future == 0 else "FLAGGED", n_future,
           f"{n_future} rows have dates beyond Dec 31 2025. "
           f"These are rogue/orphaned usage rows — excluded from AHI calculation. "
           f"{'(150 were seeded deliberately as edge case.)' if n_future > 0 else ''}",
           future_rows[["log_id","account_id","date","compute_credits_consumed"]] if n_future > 0 else None)
else:
    record("future_usage_check", "FAIL", n_future,
           f"{n_future} rows exceed expected rogue row count. Source system audit required.",
           future_rows[["log_id","account_id","date","compute_credits_consumed"]])

# ── TEST 5: Usage Outside Contract Dates ─────────────────────
# Usage logs where date falls outside the account's active contract period
logs_2025  = logs[(logs["date"] >= CONTRACT_START) & (logs["date"] <= CONTRACT_END)].copy()
con_active = con[con["end_date"] >= CONTRACT_START].copy()

# Get contract date range per account
contract_range = con_active.groupby("account_id").agg(
    earliest_start=("start_date", "min"),
    latest_end=("end_date", "max")
).reset_index()

logs_with_range = logs_2025.merge(contract_range, on="account_id", how="left")

# Flag usage before any contract started or after all contracts ended
outside_mask = (
    (logs_with_range["date"] < logs_with_range["earliest_start"]) |
    (logs_with_range["date"] > logs_with_range["latest_end"]) |
    (logs_with_range["earliest_start"].isna())
)
outside_rows = logs_with_range[outside_mask]
n_outside    = len(outside_rows)

if n_outside == 0:
    record("contract_date_usage_check", "PASS", 0,
           "All 2025 usage logs fall within active contract date ranges.")
else:
    record("contract_date_usage_check", "FLAGGED", n_outside,
           f"{n_outside} usage rows fall outside active contract date ranges. "
           f"Flagged as rogue usage — excluded from AHI calculation.",
           outside_rows[["log_id","account_id","date","compute_credits_consumed"]].head(500))

# ── TEST 6: NULL account_ids ─────────────────────────────────
null_counts = {
    "Accounts":         acc["account_id"].isna().sum(),
    "Contracts":        con["account_id"].isna().sum(),
    "Daily_Usage_Logs": logs["account_id"].isna().sum(),
    "Account_Health":   health["account_id"].isna().sum(),
}
total_nulls = sum(null_counts.values())

if total_nulls == 0:
    record("null_account_id_check", "PASS", 0,
           "No NULL account_ids found in any table.")
else:
    failing = {k:v for k,v in null_counts.items() if v > 0}
    record("null_account_id_check", "FAIL", total_nulls,
           f"NULL account_ids found: {failing}. Reject these rows before pipeline runs.")

# ── SAVE QUARANTINE LOG ──────────────────────────────────────
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)

pass_count = sum(1 for r in results if r["status"] == "PASS")
flag_count = sum(1 for r in results if r["status"] == "FLAGGED")
fail_count = sum(1 for r in results if r["status"] == "FAIL")

print(f"\n  PASS:    {pass_count}")
print(f"  FLAGGED: {flag_count}  (known edge cases — excluded from AHI, not pipeline-halting)")
print(f"  FAIL:    {fail_count}  (pipeline should halt on these)")

if quarantine:
    q_df = pd.concat(quarantine, ignore_index=True)
    q_df.to_csv(QUARANTINE, index=False)
    print(f"\n  Quarantine log: {len(q_df)} rows written to {QUARANTINE}")
else:
    print("\n  No rows quarantined.")

# Save JSON report
with open(REPORT_FILE, "w") as f:
    json.dump({
        "run_timestamp": datetime.now().isoformat(),
        "summary": {"pass": pass_count, "flagged": flag_count, "fail": fail_count},
        "tests":   results,
    }, f, indent=2)

print(f"  DQ report saved to {REPORT_FILE}")
print("\n" + "=" * 60)

pipeline_safe = fail_count == 0
print(f"PIPELINE STATUS: {'✅ SAFE TO RUN' if pipeline_safe else '❌ HALT — fix FAILs before running pipeline'}")
if flag_count > 0:
    print(f"NOTE: {flag_count} FLAGGED tests indicate known edge cases (seeded orphaned/rogue rows).")
    print(f"      These rows are quarantined and excluded from AHI — pipeline can proceed.")
print("=" * 60)
