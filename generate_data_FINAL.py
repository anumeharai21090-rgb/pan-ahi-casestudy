"""
AHI Case Study — Synthetic Data Generation Script v2
Palo Alto Networks · Global Customer Services

Fixes from v1:
  - Contracts: ~1,200 rows (added multi-product contracts per account)
  - Account_Health: ~50,000 rows (switched to daily rows, 1000 accounts x ~50 days sampled)
  - Daily_Usage_Logs: trimmed to ~200,000 rows
  - Shelfware detection tightened (truly empty logs)
  - Spike-drop tightened (cleaner collapse)

Tables generated:
  CSM_rep         ~50 rows
  Accounts        ~1,000 rows
  Contracts       ~1,200 rows
  Account_Health  ~50,000 rows
  Daily_Usage_Logs ~200,000 rows
"""

import pandas as pd
import numpy as np
from faker import Faker
import random
import os
from datetime import date, timedelta

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

OUTPUT_DIR = "./output_v2"
os.makedirs(OUTPUT_DIR, exist_ok=True)

START_DATE  = date(2025, 1, 1)
END_DATE    = date(2025, 12, 31)
DATE_RANGE  = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS      = len(DATE_RANGE)  # 365

REGIONS   = ["West", "East", "EMEA", "APAC"]
SEGMENTS  = ["Enterprise", "Mid-Market"]
INDUSTRIES = ["Technology", "Financial Services", "Healthcare",
              "Manufacturing", "Retail", "Energy", "Government",
              "Telecommunications", "Aerospace", "Pharma"]

N_CSMS            = 50
N_ACCOUNTS        = 1000
PCT_SPIKE_DROP    = 0.05
PCT_SHELFWARE     = 0.10
PCT_OVERAGES      = 0.15
N_MID_YEAR_EXP    = 40
N_ORPHANED        = 300

print("=" * 60)
print("AHI Synthetic Data Generator v2")
print("=" * 60)

# ── TABLE 1: CSM_rep ─────────────────────────────────────────
print("\n[1/5] Generating CSM_rep...")
csm_records = []
for i in range(N_CSMS):
    csm_records.append({
        "csm_id":  f"CSM_{i+1:03d}",
        "name":    fake.name(),
        "region":  random.choice(REGIONS),
        "segment": random.choice(SEGMENTS),
    })
csm_df = pd.DataFrame(csm_records)
print(f"  ✓ {len(csm_df)} rows")

# ── TABLE 2: Accounts ────────────────────────────────────────
print("\n[2/5] Generating Accounts...")
account_ids = [f"ACC_{i+1:04d}" for i in range(N_ACCOUNTS)]

n_spike   = int(N_ACCOUNTS * PCT_SPIKE_DROP)    # 50
n_shelf   = int(N_ACCOUNTS * PCT_SHELFWARE)     # 100
n_over    = int(N_ACCOUNTS * PCT_OVERAGES)      # 150

shuffled = account_ids.copy()
random.shuffle(shuffled)
spike_accs    = set(shuffled[:n_spike])
shelf_accs    = set(shuffled[n_spike:n_spike+n_shelf])
over_accs     = set(shuffled[n_spike+n_shelf:n_spike+n_shelf+n_over])
exp_accs      = set(shuffled[n_spike+n_shelf+n_over:n_spike+n_shelf+n_over+N_MID_YEAR_EXP])

def edge_case(a):
    if a in spike_accs:  return "spike_drop"
    if a in shelf_accs:  return "shelfware"
    if a in over_accs:   return "overage"
    if a in exp_accs:    return "expansion"
    return "normal"

account_records = []
for acc_id in account_ids:
    account_records.append({
        "account_id":    acc_id,
        "company_name":  fake.company(),
        "industry":      random.choice(INDUSTRIES),
        "rep_id":        random.choice(csm_df["csm_id"].tolist()),
        "_edge":         edge_case(acc_id),
    })
accounts_df = pd.DataFrame(account_records)
edge_map = dict(zip(accounts_df["account_id"], accounts_df["_edge"]))
accounts_out = accounts_df.drop(columns=["_edge"])
print(f"  ✓ {len(accounts_df)} rows")

# ── TABLE 3: Contracts (~1,200 rows) ─────────────────────────
print("\n[3/5] Generating Contracts...")

def get_segment(acc_id):
    rep = accounts_df.loc[accounts_df["account_id"]==acc_id,"rep_id"].values[0]
    return csm_df.loc[csm_df["csm_id"]==rep,"segment"].values[0]

def random_arr(seg, force_high=False):
    if force_high:
        # Shelfware must be above portfolio median — unambiguously high value
        # Floor set at $2M to guarantee above median regardless of portfolio composition
        return round(random.uniform(2_000_000, 5_000_000), -3)
    if seg == "Enterprise":
        return round(random.uniform(500_000, 5_000_000), -3)
    return round(random.uniform(50_000, 500_000), -3)

contract_records = []
ctr = 1
arr_map = {}

for acc_id in account_ids:
    seg = get_segment(acc_id)
    arr = random_arr(seg, force_high=(acc_id in shelf_accs))
    arr_map[acc_id] = arr
    monthly_credits = max(100, round(arr / 12 / 10))

    # Primary contract
    contract_records.append({
        "contract_id":                    f"CON_{ctr:04d}",
        "account_id":                     acc_id,
        "start_date":                     START_DATE,
        "end_date":                       END_DATE,
        "annual_commit_dollars":          arr,
        "included_monthly_compute_credits": monthly_credits,
    })
    ctr += 1

    # Mid-year expansion = second contract
    if acc_id in exp_accs:
        exp_start = date(2025, random.randint(4, 8), 1)
        exp_arr   = round(arr * random.uniform(1.3, 2.5), -3)
        exp_cred  = max(100, round(exp_arr / 12 / 10))
        contract_records.append({
            "contract_id":                    f"CON_{ctr:04d}",
            "account_id":                     acc_id,
            "start_date":                     exp_start,
            "end_date":                       END_DATE,
            "annual_commit_dollars":          exp_arr,
            "included_monthly_compute_credits": exp_cred,
        })
        ctr += 1

    # Add amendment contracts for ~160 accounts to reach ~1,200 total row target
    # These are add-on product line contracts — SEQUENTIAL (non-overlapping dates)
    # and smaller than primary, so they do not satisfy the mid-year expansion edge case
    elif random.random() < 0.155:
        # Sequential: starts after a gap, well-defined separate product line
        amend_arr  = round(arr * random.uniform(0.15, 0.40), -3)
        amend_cred = max(50, round(amend_arr / 12 / 10))
        contract_records.append({
            "contract_id":                    f"CON_{ctr:04d}",
            "account_id":                     acc_id,
            "start_date":                     date(2024, 1, 1),   # prior year add-on — sequential, no overlap
            "end_date":                       date(2024, 12, 31), # ended before 2025 primary started
            "annual_commit_dollars":          amend_arr,
            "included_monthly_compute_credits": amend_cred,
        })
        ctr += 1

contracts_df = pd.DataFrame(contract_records)
monthly_credits_map = contracts_df.groupby("account_id")["included_monthly_compute_credits"].max().to_dict()
print(f"  ✓ {len(contracts_df)} rows")

# ── Daily usage generator ────────────────────────────────────
def gen_daily_usage(acc_id, edge, base_monthly, dates):
    daily_base = base_monthly / 30
    usage = []
    for d in dates:
        mn = d.month
        doy = (d - pd.Timestamp(START_DATE)).days

        if edge == "shelfware":
            # Truly empty — zero usage, matches spec "completely empty Daily_Usage_Logs"
            credits = 0.0

        elif edge == "spike_drop":
            if mn == 1:
                # 90% of annual in month 1
                credits = daily_base * random.uniform(10, 14)
            else:
                credits = max(0, np.random.normal(daily_base * 0.01, 0.1))

        elif edge == "overage":
            factor = random.uniform(1.20, 1.50)
            credits = max(0, np.random.normal(daily_base * factor, daily_base * 0.08))

        elif edge == "expansion":
            if mn <= 6:
                credits = max(0, np.random.normal(daily_base * 0.75, daily_base * 0.1))
            else:
                credits = max(0, np.random.normal(daily_base * 1.35, daily_base * 0.1))

        else:  # normal
            seasonal = 1.0 + 0.15 * np.sin(2 * np.pi * doy / 365)
            credits = max(0, np.random.normal(daily_base * 0.85 * seasonal, daily_base * 0.1))

        usage.append(round(credits, 2))
    return usage

# ── TABLE 5: Daily_Usage_Logs (~200,000 rows) ────────────────
print("\n[4/5] Generating Daily_Usage_Logs (~200K rows)...")

log_records = []
log_ctr = 1

# Shelfware accounts: skip entirely (completely empty logs per spec)
# All other accounts: generate daily logs
# To hit ~200K rows from ~900 non-shelfware accounts x 365 days = 328K
# We'll sample ~60% of days for normal/expansion/overage to land near 200K
# Spike-drop and overage get full daily logs; normal/expansion sampled at 55%

for i, acc_id in enumerate(account_ids):
    if i % 200 == 0:
        print(f"  Processing {i+1}/{N_ACCOUNTS}...", end="\r")

    edge = edge_map[acc_id]
    base = monthly_credits_map.get(acc_id, 1000)

    # Shelfware: truly empty — no logs at all (spec: completely empty Daily_Usage_Logs)
    if acc_id in shelf_accs:
        continue

    daily = gen_daily_usage(acc_id, edge, base, DATE_RANGE)

    for d, credits in zip(DATE_RANGE, daily):
        # Sample days for normal/expansion to control row count
        if edge in ("normal", "expansion") and random.random() > 0.55:
            continue
        if credits == 0 and edge != "spike_drop":
            continue
        log_records.append({
            "log_id":                   f"LOG_{log_ctr:07d}",
            "account_id":               acc_id,
            "date":                     d.date(),
            "compute_credits_consumed": credits,
        })
        log_ctr += 1

# Orphaned: ghost accounts (don't exist in Accounts)
print(f"\n  Seeding {N_ORPHANED} orphaned rows...")
ghost_ids = [f"GHOST_{i:04d}" for i in range(150)]
for _ in range(150):
    log_records.append({
        "log_id":                   f"LOG_{log_ctr:07d}",
        "account_id":               random.choice(ghost_ids),
        "date":                     START_DATE + timedelta(days=random.randint(0, 364)),
        "compute_credits_consumed": round(random.uniform(10, 500), 2),
    })
    log_ctr += 1

# Orphaned: rogue dates (outside contract period)
non_shelf_ids = [a for a in account_ids if a not in shelf_accs]
for acc_id in random.sample(non_shelf_ids, 150):
    log_records.append({
        "log_id":                   f"LOG_{log_ctr:07d}",
        "account_id":               acc_id,
        "date":                     END_DATE + timedelta(days=random.randint(30, 180)),
        "compute_credits_consumed": round(random.uniform(5, 200), 2),
    })
    log_ctr += 1

logs_df = pd.DataFrame(log_records)
print(f"  ✓ {len(logs_df):,} rows")

# ── TABLE 4: Account_Health (~50,000 rows = daily per account) ──
print("\n[5/5] Generating Account_Health (~50K rows)...")

# 50,000 rows = 1,000 accounts × ~50 daily health snapshots each
# Strategy: sample ~50 dates per account spread across the year
N_HEALTH_DAYS = 50  # per account → 50,000 total

def usage_to_health_color(pct):
    if pct >= 0.80: return "Green"
    if pct >= 0.50: return "Yellow"
    return "Red"

health_records = []
# Pre-aggregate daily logs by account+date for fast lookup
logs_clean = logs_df[logs_df["date"] <= END_DATE].copy()
logs_clean["date"] = pd.to_datetime(logs_clean["date"])
daily_by_acc = logs_clean.groupby(["account_id", "date"])["compute_credits_consumed"].sum()

for acc_id in account_ids:
    base = monthly_credits_map.get(acc_id, 1000)
    daily_committed = base / 30

    # Sample 50 dates spread across the year
    sampled_dates = sorted(random.sample(list(DATE_RANGE), N_HEALTH_DAYS))

    for d in sampled_dates:
        try:
            consumed = daily_by_acc.loc[(acc_id, d)]
        except KeyError:
            consumed = 0.0

        pct = consumed / daily_committed if daily_committed > 0 else 0
        health_records.append({
            "health_color":             usage_to_health_color(pct),
            "account_id":               acc_id,
            "date":                     d.date(),
            "compute_credits_consumed": round(float(consumed), 2),
        })

health_df = pd.DataFrame(health_records)
print(f"  ✓ {len(health_df):,} rows")

# ── SAVE ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Saving to ./output_v2/")

files = {
    "CSM_rep.csv":          csm_df,
    "Accounts.csv":         accounts_out,
    "Contracts.csv":        contracts_df,
    "Account_Health.csv":   health_df,
    "Daily_Usage_Logs.csv": logs_df,
}
for fname, df in files.items():
    path = os.path.join(OUTPUT_DIR, fname)
    df.to_csv(path, index=False)
    print(f"  ✓ {fname:<30} {len(df):>8,} rows")

# ── VALIDATION ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("Edge Case Validation")
print("=" * 60)

total_usage = logs_df[logs_df["date"] <= END_DATE].groupby("account_id")["compute_credits_consumed"].sum()
shelf_check = sum(1 for a in shelf_accs if total_usage.get(a, 0) == 0)
print(f"\n  Shelfware (zero logs):        {shelf_check}/{len(shelf_accs)} accounts (target 100%)")

monthly = logs_df[pd.to_datetime(logs_df["date"]).dt.year == 2025].copy()
monthly["month"] = pd.to_datetime(monthly["date"]).dt.month
mon_sum = monthly.groupby(["account_id","month"])["compute_credits_consumed"].sum().unstack().fillna(0)
if 1 in mon_sum.columns and 2 in mon_sum.columns:
    spike_check = sum(1 for a in spike_accs if a in mon_sum.index and
                      mon_sum.loc[a,1] > mon_sum.loc[a,2] * 50)
    print(f"  Spike-drop (M1>>M2 by 50x):   {spike_check}/{len(spike_accs)} accounts")

over_check = 0
for a in over_accs:
    base = monthly_credits_map.get(a, 1)
    avg = total_usage.get(a, 0) / 12
    if avg > base * 1.2:
        over_check += 1
print(f"  Overages (avg > 120%):        {over_check}/{len(over_accs)} accounts")

exp_check = contracts_df.groupby("account_id").size()
print(f"  Mid-year expansions:          {sum(exp_check > 1)} accounts with 2+ contracts")

ghost_rows = logs_df[~logs_df["account_id"].isin(accounts_out["account_id"])]
rogue_rows = logs_df[pd.to_datetime(logs_df["date"]) > pd.Timestamp(END_DATE)]
print(f"  Orphaned ghost rows:          {len(ghost_rows)}")
print(f"  Rogue date rows:              {len(rogue_rows)}")

print("\n" + "=" * 60)
print("Done. Upload ./output_v2/ CSVs to BigQuery dataset: ahi_case_study")
print("=" * 60)
