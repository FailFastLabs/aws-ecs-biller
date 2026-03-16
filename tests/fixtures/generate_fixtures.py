"""
Realistic AWS CUR fixture generator.

Cost model per EC2 instance type:
  hourly_instances = base_count
    * growth(t)            linear slope +1.5%/month
    * daily_sin(hour)      peaks 14:00 UTC, trough 03:00 UTC
    * weekly_factor(dow)   40% on weekends
    * random_walk(t)       log-normal, ±3% daily steps
    * breaking_points(t)   step changes ~every 45 days
    * drop_events(t)       50% drops ~every 60 days, 3-7 days each

S3: monotonically growing storage (8%/month), always positive

Reservations: sized at P25 of daily instance count (OD price × (1 - discount))
Savings Plan: hourly commitment = 10% of P25 daily total spend / 24
"""

import csv
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent
PAYER = "123456789012"
LINKED_PROD = "123456789012"
LINKED_STAGING = "234567890123"

START_DT = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
NOW_DT = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)

# ── EC2 instance configs ──────────────────────────────────────────────────────
EC2_CFGS = [
    dict(region="us-east-1", az="us-east-1a", itype="m5.xlarge",  ifamily="m5",
         account=LINKED_PROD,    od_hourly=0.1920, ri_discount=0.30,
         base_count=8, seed=42, tag_env="prod",    tag_team="backend"),
    dict(region="us-east-1", az="us-east-1b", itype="m5.large",   ifamily="m5",
         account=LINKED_PROD,    od_hourly=0.0960, ri_discount=0.0,
         base_count=5, seed=43, tag_env="dev",     tag_team="backend"),
    dict(region="us-east-1", az="us-east-1c", itype="c5.xlarge",  ifamily="c5",
         account=LINKED_PROD,    od_hourly=0.1700, ri_discount=0.32,
         base_count=6, seed=44, tag_env="prod",    tag_team="data"),
    dict(region="us-east-1", az="us-east-1a", itype="r5.2xlarge", ifamily="r5",
         account=LINKED_PROD,    od_hourly=0.5040, ri_discount=0.35,
         base_count=4, seed=45, tag_env="prod",    tag_team="data",
         active_from=datetime(2025, 2, 1, tzinfo=timezone.utc)),
    dict(region="us-west-2", az="us-west-2a", itype="m5.2xlarge", ifamily="m5",
         account=LINKED_STAGING, od_hourly=0.4160, ri_discount=0.28,
         base_count=3, seed=46, tag_env="staging", tag_team="platform"),
    dict(region="eu-west-1", az="eu-west-1a", itype="r5.large",   ifamily="r5",
         account=LINKED_PROD,    od_hourly=0.1480, ri_discount=0.0,
         base_count=2, seed=47, tag_env="prod",    tag_team="frontend"),
]

# Savings plan ARN
SP_ARN = "arn:aws:savingsplans::123456789012:savingsplan/sp-abc123def456"


# ── Cost pattern generators ───────────────────────────────────────────────────

def _hours_range(start: datetime, end: datetime) -> pd.DatetimeIndex:
    return pd.date_range(start, end - timedelta(hours=1), freq="h", tz="UTC")


def generate_ec2_hourly_counts(cfg: dict, hours: pd.DatetimeIndex) -> np.ndarray:
    """Return float instance counts per hour (may be fractional for cost purposes)."""
    rng = np.random.default_rng(cfg["seed"])
    n = len(hours)
    if n == 0:
        return np.array([])

    base = cfg["base_count"]

    # 1. Linear growth: +1.5%/month
    months_elapsed = np.array(
        [(h - START_DT).total_seconds() / (30 * 24 * 3600) for h in hours]
    )
    growth = 1.0 + 0.015 * np.maximum(months_elapsed, 0)

    # 2. Daily sinusoid: two humps peaking ~10:00 and ~17:00 UTC
    hour_of_day = np.array([h.hour + h.minute / 60.0 for h in hours])
    daily_sin = (
        0.55
        + 0.25 * np.sin(2 * np.pi * (hour_of_day - 10) / 24)
        + 0.20 * np.sin(4 * np.pi * (hour_of_day - 8) / 24)
    )
    daily_sin = np.clip(daily_sin, 0.05, 1.0)

    # 3. Weekly: 40% load on Saturday/Sunday
    dow = np.array([h.weekday() for h in hours])
    weekly = np.where(dow >= 5, 0.40, 1.0)

    # 4. Log-normal random walk (one step per day, constant within the day)
    n_days = int(np.ceil(n / 24)) + 1
    daily_steps = rng.normal(0.0, 0.030, n_days)  # 3% std per day
    daily_rw_raw = np.cumsum(daily_steps)
    # Soft mean-reversion: subtract a small fraction of cumulative drift
    drift_correction = 0.005 * np.arange(n_days)
    daily_rw = np.exp(daily_rw_raw - drift_correction)
    rw_hourly = np.repeat(daily_rw, 24)[:n]

    # 5. Breaking points: step changes ~every 45 days
    n_breaks = max(1, n // (24 * 45))
    break_times = sorted(rng.integers(24 * 7, max(24 * 8, n - 1), size=n_breaks).tolist())
    bp_factor = np.ones(n)
    cumulative = 1.0
    for bt in break_times:
        step = rng.uniform(0.78, 1.28)
        cumulative *= step
        bp_factor[bt:] = cumulative
    # Normalize so the mean breaking-point factor stays near 1
    bp_factor /= bp_factor.mean()

    # 6. Random 50% drop events (~1 per 60 days, duration 3–7 days)
    n_drops = max(1, n // (24 * 60))
    drop_factor = np.ones(n)
    for _ in range(n_drops):
        drop_start = int(rng.integers(0, max(1, n - 24 * 7)))
        drop_len = int(rng.integers(24 * 3, 24 * 7 + 1))
        drop_factor[drop_start: min(n, drop_start + drop_len)] *= 0.50

    counts = base * growth * daily_sin * weekly * rw_hourly * bp_factor * drop_factor
    return np.maximum(counts, 0.01)


def generate_s3_daily_costs(days: pd.DatetimeIndex) -> np.ndarray:
    """Always-positive, monotonically growing S3 costs (storage + requests)."""
    rng = np.random.default_rng(100)
    n = len(days)
    months_elapsed = np.array(
        [(d - pd.Timestamp(START_DT)).total_seconds() / (30 * 24 * 3600) for d in days]
    )
    # Storage: starts 10 TB, grows 8%/month
    storage_gb = 10_000 * np.exp(0.08 * months_elapsed)
    storage_cost = storage_gb * 0.023 / 30  # $0.023/GB-month → daily

    # Request costs: ~6% of storage, with small positive noise
    request_noise = 1.0 + np.abs(rng.normal(0, 0.04, n))
    total_daily = storage_cost * request_noise * 1.06

    # Enforce monotonically non-decreasing by taking cummax of a smoothed series
    smoothed = pd.Series(total_daily).rolling(7, min_periods=1).mean().values
    return np.maximum(smoothed, 0.01)


def generate_rds_hourly_costs(hours: pd.DatetimeIndex) -> np.ndarray:
    """Stable RDS costs: db.r5.large in us-east-1 (~$0.24/hr), slight growth."""
    rng = np.random.default_rng(200)
    n = len(hours)
    months_elapsed = np.array(
        [(h - START_DT).total_seconds() / (30 * 24 * 3600) for h in hours]
    )
    base = 0.240  # db.r5.large on-demand
    growth = 1.0 + 0.010 * months_elapsed  # 1%/month (DB tier grows slower)
    noise = 1.0 + rng.normal(0, 0.01, n)  # very low noise
    return np.maximum(base * growth * noise, 0.10)


def generate_eks_hourly_costs(hours: pd.DatetimeIndex) -> np.ndarray:
    """EKS cluster costs: 2 clusters × $0.10/hr = $0.20/hr, very stable."""
    rng = np.random.default_rng(300)
    n = len(hours)
    noise = 1.0 + rng.normal(0, 0.005, n)
    return np.maximum(0.20 * noise, 0.10)


def generate_lambda_hourly_costs(hours: pd.DatetimeIndex) -> np.ndarray:
    """Lambda costs with strong daily pattern. Covered by savings plan."""
    rng = np.random.default_rng(400)
    n = len(hours)
    months_elapsed = np.array(
        [(h - START_DT).total_seconds() / (30 * 24 * 3600) for h in hours]
    )
    hour_of_day = np.array([h.hour for h in hours])
    daily_sin = 0.3 + 0.7 * np.clip(np.sin(2 * np.pi * (hour_of_day - 10) / 24), 0, 1)
    growth = 1.0 + 0.020 * months_elapsed  # Lambda grows faster
    noise = 1.0 + rng.normal(0, 0.05, n)
    base = 0.090  # ~$2.16/day base
    return np.maximum(base * growth * daily_sin * noise, 0.001)


# ── CUR row helpers ───────────────────────────────────────────────────────────

CUR_COLS = [
    "identity_line_item_id", "identity_time_interval",
    "bill_billing_period_start_date", "bill_billing_period_end_date",
    "bill_bill_type", "bill_payer_account_id", "bill_invoice_id",
    "line_item_usage_account_id", "line_item_usage_account_name",
    "line_item_usage_start_date", "line_item_usage_end_date",
    "line_item_line_item_type", "line_item_product_code",
    "line_item_usage_type", "line_item_operation",
    "line_item_resource_id", "line_item_availability_zone",
    "line_item_usage_amount", "line_item_unblended_cost",
    "line_item_blended_cost", "line_item_net_unblended_cost",
    "line_item_normalization_factor", "line_item_normalized_usage_amount",
    "line_item_line_item_description", "line_item_currency_code",
    "pricing_public_on_demand_cost", "pricing_term", "pricing_unit",
    "pricing_offering_class", "pricing_purchase_option", "pricing_lease_contract_length",
    "product_region_code", "product_instance_type", "product_instance_family",
    "product_product_family", "product_servicecode", "product_sku", "product",
    "reservation_reservation_a_r_n", "reservation_effective_cost",
    "reservation_amortized_upfront_cost_for_usage", "reservation_recurring_fee_for_usage",
    "reservation_unused_quantity", "reservation_unused_recurring_fee",
    "reservation_normalized_units_per_reservation", "reservation_number_of_reservations",
    "reservation_start_time", "reservation_end_time", "reservation_subscription_id",
    "savings_plan_savings_plan_a_r_n", "savings_plan_savings_plan_effective_cost",
    "savings_plan_offering_type", "savings_plan_payment_option",
    "savings_plan_purchase_term", "savings_plan_region",
    "savings_plan_used_commitment", "savings_plan_total_commitment_to_date",
    "split_line_item_split_cost", "split_line_item_actual_usage",
    "split_line_item_split_usage_ratio", "split_line_item_parent_resource_id",
    "resource_tags", "cost_category", "discount_total_discount",
]

_EMPTY = {c: "" for c in CUR_COLS}


def _bp_dates(dt: datetime):
    """Return (bp_start_str, bp_end_str, invoice_id) for the month containing dt."""
    bp_start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if bp_start.month == 12:
        bp_end = bp_start.replace(year=bp_start.year + 1, month=1)
    else:
        bp_end = bp_start.replace(month=bp_start.month + 1)
    inv = f"INV-{bp_start.strftime('%Y%m')}"
    return (
        bp_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        bp_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        inv,
    )


def _time_interval(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def ec2_od_row(hour: datetime, cfg: dict, count: float) -> dict:
    end = hour + timedelta(hours=1)
    bp_start, bp_end, inv = _bp_dates(hour)
    od = cfg["od_hourly"]
    cost = count * od
    tags = json.dumps({"user:env": cfg["tag_env"], "user:team": cfg["tag_team"]})
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(hour, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     cfg["account"],
        "line_item_usage_account_name":   "acme-prod" if cfg["account"] == LINKED_PROD else "acme-staging",
        "line_item_usage_start_date":     hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       "Usage",
        "line_item_product_code":         "AmazonEC2",
        "line_item_usage_type":           f"BoxUsage:{cfg['itype']}",
        "line_item_operation":            "RunInstances",
        "line_item_resource_id":          f"i-{cfg['itype'].replace('.','')}{hour.strftime('%H%M')}",
        "line_item_availability_zone":    cfg["az"],
        "line_item_usage_amount":         f"{count:.6f}",
        "line_item_unblended_cost":       f"{cost:.6f}",
        "line_item_blended_cost":         f"{cost:.6f}",
        "line_item_net_unblended_cost":   f"{cost:.6f}",
        "line_item_normalization_factor": "8.0" if "xlarge" in cfg["itype"] else "4.0",
        "line_item_normalized_usage_amount": f"{count * 8:.6f}",
        "line_item_line_item_description": f"${ od:.4f} per On Demand Linux {cfg['itype']}",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  f"{cost:.6f}",
        "pricing_term":                   "OnDemand",
        "pricing_unit":                   "Hrs",
        "product_region_code":            cfg["region"],
        "product_instance_type":          cfg["itype"],
        "product_instance_family":        cfg["ifamily"],
        "product_product_family":         "Compute Instance",
        "product_servicecode":            "AmazonEC2",
        "product_sku":                    f"SKU-EC2-{cfg['itype'].upper().replace('.','')}-OD",
        "resource_tags":                  tags,
    }


def ec2_ri_covered_row(hour: datetime, cfg: dict, ri_count: float,
                        ri_hourly: float, ri_arn: str, ri_sub: str,
                        ri_start: str, ri_end: str) -> dict:
    end = hour + timedelta(hours=1)
    bp_start, bp_end, inv = _bp_dates(hour)
    cost = ri_count * ri_hourly
    od_cost = ri_count * cfg["od_hourly"]
    tags = json.dumps({"user:env": cfg["tag_env"], "user:team": cfg["tag_team"]})
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(hour, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     cfg["account"],
        "line_item_usage_account_name":   "acme-prod" if cfg["account"] == LINKED_PROD else "acme-staging",
        "line_item_usage_start_date":     hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       "DiscountedUsage",
        "line_item_product_code":         "AmazonEC2",
        "line_item_usage_type":           f"BoxUsage:{cfg['itype']}",
        "line_item_operation":            "RunInstances",
        "line_item_resource_id":          f"i-ri-{cfg['itype'].replace('.','')}{hour.strftime('%H%M')}",
        "line_item_availability_zone":    cfg["az"],
        "line_item_usage_amount":         f"{ri_count:.6f}",
        "line_item_unblended_cost":       f"{cost:.6f}",
        "line_item_blended_cost":         f"{cost:.6f}",
        "line_item_net_unblended_cost":   f"{cost:.6f}",
        "line_item_normalization_factor": "8.0",
        "line_item_normalized_usage_amount": f"{ri_count * 8:.6f}",
        "line_item_line_item_description": f"USD {ri_hourly:.6f} reserved instance applied",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  f"{od_cost:.6f}",
        "pricing_term":                   "Reserved",
        "pricing_unit":                   "Hrs",
        "pricing_offering_class":         "standard",
        "pricing_purchase_option":        "No Upfront",
        "pricing_lease_contract_length":  "1yr",
        "product_region_code":            cfg["region"],
        "product_instance_type":          cfg["itype"],
        "product_instance_family":        cfg["ifamily"],
        "product_product_family":         "Compute Instance",
        "product_servicecode":            "AmazonEC2",
        "product_sku":                    f"SKU-EC2-{cfg['itype'].upper().replace('.','')}-RI",
        "reservation_reservation_a_r_n":  ri_arn,
        "reservation_effective_cost":     f"{cost:.6f}",
        "reservation_recurring_fee_for_usage": f"{cost:.6f}",
        "reservation_start_time":         ri_start,
        "reservation_end_time":           ri_end,
        "reservation_subscription_id":    ri_sub,
        "resource_tags":                  tags,
    }


def ec2_rifee_row(day: datetime, cfg: dict, ri_count: float,
                   ri_hourly: float, ri_arn: str, ri_sub: str,
                   ri_start: str, ri_end: str) -> dict:
    """One RIFee row per day per reservation."""
    end = day + timedelta(days=1)
    bp_start, bp_end, inv = _bp_dates(day)
    daily_fee = ri_count * ri_hourly * 24
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(day, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     cfg["account"],
        "line_item_usage_account_name":   "acme-prod",
        "line_item_usage_start_date":     day.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       "RIFee",
        "line_item_product_code":         "AmazonEC2",
        "line_item_usage_type":           f"HeavyUsage:{cfg['itype']}",
        "line_item_operation":            "RunInstances",
        "line_item_resource_id":          ri_arn,
        "line_item_availability_zone":    "",
        "line_item_usage_amount":         f"{ri_count * 24:.6f}",
        "line_item_unblended_cost":       f"{daily_fee:.6f}",
        "line_item_blended_cost":         f"{daily_fee:.6f}",
        "line_item_net_unblended_cost":   f"{daily_fee:.6f}",
        "line_item_normalization_factor": "8.0",
        "line_item_normalized_usage_amount": f"{ri_count * 24 * 8:.6f}",
        "line_item_line_item_description": f"USD {ri_hourly:.6f}/Hrs {cfg['itype']} reserved",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  "0.000000",
        "pricing_term":                   "Reserved",
        "pricing_unit":                   "Hrs",
        "pricing_offering_class":         "standard",
        "pricing_purchase_option":        "No Upfront",
        "pricing_lease_contract_length":  "1yr",
        "product_region_code":            cfg["region"],
        "product_instance_type":          cfg["itype"],
        "product_instance_family":        cfg["ifamily"],
        "product_product_family":         "Compute Instance",
        "product_servicecode":            "AmazonEC2",
        "product_sku":                    f"SKU-EC2-{cfg['itype'].upper().replace('.','')}-RI",
        "reservation_reservation_a_r_n":  ri_arn,
        "reservation_effective_cost":     f"{daily_fee:.6f}",
        "reservation_recurring_fee_for_usage": f"{daily_fee:.6f}",
        "reservation_normalized_units_per_reservation": f"{ri_count * 8:.1f}",
        "reservation_number_of_reservations": str(int(ri_count)),
        "reservation_start_time":         ri_start,
        "reservation_end_time":           ri_end,
        "reservation_subscription_id":    ri_sub,
    }


def lambda_row(hour: datetime, cost: float, sp_commitment: float) -> dict:
    end = hour + timedelta(hours=1)
    bp_start, bp_end, inv = _bp_dates(hour)
    sp_effective = cost * 0.90  # 10% savings via SP
    used_commitment = min(cost, sp_commitment)
    is_sp = cost <= sp_commitment * 1.2  # covered if within 120% of commitment
    ltype = "SavingsPlanCoveredUsage" if is_sp else "Usage"
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(hour, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     LINKED_PROD,
        "line_item_usage_account_name":   "acme-prod",
        "line_item_usage_start_date":     hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       ltype,
        "line_item_product_code":         "AWSLambda",
        "line_item_usage_type":           "Lambda-GB-Second",
        "line_item_operation":            "Invoke",
        "line_item_resource_id":          "arn:aws:lambda:us-east-1:123456789012:function:acme-api",
        "line_item_availability_zone":    "",
        "line_item_usage_amount":         f"{cost / 0.00001667:.2f}",
        "line_item_unblended_cost":       f"{cost:.6f}",
        "line_item_blended_cost":         f"{cost:.6f}",
        "line_item_net_unblended_cost":   f"{sp_effective if is_sp else cost:.6f}",
        "line_item_normalization_factor": "1.0",
        "line_item_normalized_usage_amount": f"{cost / 0.00001667:.2f}",
        "line_item_line_item_description": "AWS Lambda",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  f"{cost:.6f}",
        "pricing_term":                   "OnDemand",
        "pricing_unit":                   "Lambda-GB-Second",
        "product_region_code":            "us-east-1",
        "product_servicecode":            "AWSLambda",
        "product_sku":                    "SKU-LAMBDA-GBS",
        **(
            {
                "savings_plan_savings_plan_a_r_n":        SP_ARN,
                "savings_plan_savings_plan_effective_cost": f"{sp_effective:.6f}",
                "savings_plan_offering_type":             "ComputeSavingsPlan",
                "savings_plan_payment_option":            "No Upfront",
                "savings_plan_purchase_term":             "1yr",
                "savings_plan_region":                    "us-east-1",
                "savings_plan_used_commitment":           f"{used_commitment:.6f}",
                "savings_plan_total_commitment_to_date":  f"{sp_commitment * 24:.6f}",
            }
            if is_sp else {}
        ),
    }


def rds_row(hour: datetime, cost: float) -> dict:
    end = hour + timedelta(hours=1)
    bp_start, bp_end, inv = _bp_dates(hour)
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(hour, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     LINKED_PROD,
        "line_item_usage_account_name":   "acme-prod",
        "line_item_usage_start_date":     hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       "Usage",
        "line_item_product_code":         "AmazonRDS",
        "line_item_usage_type":           "RDS:db.r5.large",
        "line_item_operation":            "CreateDBInstance:0014",
        "line_item_resource_id":          "arn:aws:rds:us-east-1:123456789012:db:acme-prod",
        "line_item_availability_zone":    "us-east-1b",
        "line_item_usage_amount":         "1.000000",
        "line_item_unblended_cost":       f"{cost:.6f}",
        "line_item_blended_cost":         f"{cost:.6f}",
        "line_item_net_unblended_cost":   f"{cost:.6f}",
        "line_item_normalization_factor": "1.0",
        "line_item_normalized_usage_amount": "1.000000",
        "line_item_line_item_description": "MySQL Community db.r5.large Multi-AZ",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  f"{cost:.6f}",
        "pricing_term":                   "OnDemand",
        "pricing_unit":                   "Hrs",
        "product_region_code":            "us-east-1",
        "product_instance_type":          "db.r5.large",
        "product_instance_family":        "r5",
        "product_product_family":         "Database Instance",
        "product_servicecode":            "AmazonRDS",
        "product_sku":                    "SKU-RDS-R5LG-MULTIAZ",
    }


def eks_row(hour: datetime, cost: float) -> dict:
    end = hour + timedelta(hours=1)
    bp_start, bp_end, inv = _bp_dates(hour)
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(hour, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     LINKED_PROD,
        "line_item_usage_account_name":   "acme-prod",
        "line_item_usage_start_date":     hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       "Usage",
        "line_item_product_code":         "AmazonEKS",
        "line_item_usage_type":           "AmazonEKS:perClusterHour",
        "line_item_operation":            "CreateKubernetesCluster",
        "line_item_resource_id":          "arn:aws:eks:us-east-1:123456789012:cluster/acme-prod",
        "line_item_availability_zone":    "",
        "line_item_usage_amount":         "2.000000",
        "line_item_unblended_cost":       f"{cost:.6f}",
        "line_item_blended_cost":         f"{cost:.6f}",
        "line_item_net_unblended_cost":   f"{cost:.6f}",
        "line_item_normalization_factor": "1.0",
        "line_item_normalized_usage_amount": "2.000000",
        "line_item_line_item_description": "Amazon Elastic Kubernetes Service",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  f"{cost:.6f}",
        "pricing_term":                   "OnDemand",
        "pricing_unit":                   "Hrs",
        "product_region_code":            "us-east-1",
        "product_product_family":         "Compute",
        "product_servicecode":            "AmazonEKS",
        "product_sku":                    "SKU-EKS-CLUSTER-HOUR",
        "resource_tags":                  '{"user:team": "platform"}',
    }


def s3_row(day: datetime, cost: float, storage_gb: float) -> dict:
    end = day + timedelta(days=1)
    bp_start, bp_end, inv = _bp_dates(day)
    return {
        **_EMPTY,
        "identity_line_item_id":          str(uuid.uuid4()).replace("-", "")[:32],
        "identity_time_interval":         _time_interval(day, end),
        "bill_billing_period_start_date": bp_start,
        "bill_billing_period_end_date":   bp_end,
        "bill_bill_type":                 "Anniversary",
        "bill_payer_account_id":          PAYER,
        "bill_invoice_id":                inv,
        "line_item_usage_account_id":     LINKED_PROD,
        "line_item_usage_account_name":   "acme-prod",
        "line_item_usage_start_date":     day.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_usage_end_date":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "line_item_line_item_type":       "Usage",
        "line_item_product_code":         "AmazonS3",
        "line_item_usage_type":           "TimedStorage-ByteHrs",
        "line_item_operation":            "StandardStorage",
        "line_item_resource_id":          "arn:aws:s3:::acme-data-lake",
        "line_item_availability_zone":    "",
        "line_item_usage_amount":         f"{storage_gb:.2f}",
        "line_item_unblended_cost":       f"{cost:.6f}",
        "line_item_blended_cost":         f"{cost:.6f}",
        "line_item_net_unblended_cost":   f"{cost:.6f}",
        "line_item_normalization_factor": "1.0",
        "line_item_normalized_usage_amount": f"{storage_gb:.2f}",
        "line_item_line_item_description": f"$0.023 per GB - first 50 TB / month",
        "line_item_currency_code":        "USD",
        "pricing_public_on_demand_cost":  f"{cost:.6f}",
        "pricing_term":                   "OnDemand",
        "pricing_unit":                   "GB-Mo",
        "product_region_code":            "us-east-1",
        "product_product_family":         "Storage",
        "product_servicecode":            "AmazonS3",
        "product_sku":                    "SKU-S3-STD-STORAGE",
    }


# ── Main generation ───────────────────────────────────────────────────────────

def main():
    all_hours = _hours_range(START_DT, NOW_DT)
    all_days = pd.date_range(START_DT, NOW_DT - timedelta(hours=1), freq="D", tz="UTC")

    print(f"Generating data from {START_DT.date()} to {NOW_DT.date()}")
    print(f"  {len(all_hours):,} hours, {len(all_days):,} days")

    # ── Step 1: generate raw EC2 instance counts ───────────────────────────
    ec2_counts: dict[int, np.ndarray] = {}
    for i, cfg in enumerate(EC2_CFGS):
        active_from = cfg.get("active_from", START_DT)
        active_hours = all_hours[all_hours >= active_from]
        counts = np.zeros(len(all_hours))
        if len(active_hours) > 0:
            offset = list(all_hours).index(active_hours[0])
            counts[offset:] = generate_ec2_hourly_counts(cfg, active_hours)
        ec2_counts[i] = counts
        print(f"  EC2 {cfg['region']}/{cfg['itype']}: {counts.max():.1f} peak instances")

    # ── Step 2: compute P25 daily costs → RI capacity ─────────────────────
    ri_cfgs: list[dict] = []  # will hold cfg + ri_count + ri_hourly etc.

    for i, cfg in enumerate(EC2_CFGS):
        if cfg["ri_discount"] <= 0:
            continue
        counts = ec2_counts[i]
        if counts.max() < 0.5:
            continue

        # Daily cost at OD price
        hour_df = pd.DataFrame({"count": counts}, index=all_hours)
        daily_od_cost = hour_df["count"].resample("D").sum() * cfg["od_hourly"]

        p25_daily_cost = float(np.percentile(daily_od_cost[daily_od_cost > 0], 25))
        # RI count: how many instances we'd need to cover P25 24×7
        ri_count_float = p25_daily_cost / (24 * cfg["od_hourly"])
        ri_count = max(1, int(np.floor(ri_count_float)))
        ri_hourly = cfg["od_hourly"] * (1 - cfg["ri_discount"])

        # Build RI ARN based on instance type + region
        ri_id = f"ri-{abs(hash(cfg['itype']+cfg['region'])):016x}"[:22]
        ri_arn = f"arn:aws:ec2:{cfg['region']}:123456789012:reserved-instances/{ri_id}"
        ri_sub = f"sub-{ri_id[:8]}"

        active_from = cfg.get("active_from", START_DT)
        ri_start = active_from.strftime("%Y-%m-%dT%H:%M:%SZ")
        ri_end = active_from.replace(year=active_from.year + 3).strftime("%Y-%m-%dT%H:%M:%SZ")

        ri_cfgs.append({
            "cfg_idx":   i,
            "cfg":       cfg,
            "ri_count":  ri_count,
            "ri_hourly": ri_hourly,
            "ri_arn":    ri_arn,
            "ri_sub":    ri_sub,
            "ri_start":  ri_start,
            "ri_end":    ri_end,
            "active_from": active_from,
        })
        print(f"  RI {cfg['itype']}: {ri_count} instances @ ${ri_hourly:.4f}/hr "
              f"(P25 daily ${p25_daily_cost:.2f})")

    # Build lookup: cfg_idx → ri_cfg
    ri_by_idx = {r["cfg_idx"]: r for r in ri_cfgs}

    # ── Step 3: compute SP commitment (10% of P25 total daily spend) ──────
    # Rough total: sum all EC2 OD costs (pre-RI) + other services
    total_hourly = np.zeros(len(all_hours))
    for i, cfg in enumerate(EC2_CFGS):
        total_hourly += ec2_counts[i] * cfg["od_hourly"]

    total_daily = pd.Series(total_hourly, index=all_hours).resample("D").sum()
    p25_total_daily = float(np.percentile(total_daily[total_daily > 0], 25))
    sp_hourly_commitment = p25_total_daily * 0.10 / 24
    print(f"  SP commitment: ${sp_hourly_commitment:.4f}/hr "
          f"(10% of P25 daily ${p25_total_daily:.2f})")

    # ── Step 4: generate other service costs ──────────────────────────────
    rds_costs   = generate_rds_hourly_costs(all_hours)
    eks_costs   = generate_eks_hourly_costs(all_hours)
    lambda_costs = generate_lambda_hourly_costs(all_hours)
    s3_daily    = generate_s3_daily_costs(all_days)
    s3_storage_gb = 10_000 * np.exp(
        0.08 * np.array([(d - pd.Timestamp(START_DT)).total_seconds() / (30*24*3600)
                         for d in all_days])
    )

    # ── Step 5: build all CUR rows ─────────────────────────────────────────
    print("Building CUR rows...")
    rows = []

    for h_idx, hour in enumerate(all_hours):
        hour_dt = hour.to_pydatetime()

        # EC2 rows
        for i, cfg in enumerate(EC2_CFGS):
            count = ec2_counts[i][h_idx]
            if count < 0.001:
                continue

            ri = ri_by_idx.get(i)
            if ri and hour_dt >= ri["active_from"]:
                ri_count = ri["ri_count"]
                covered = min(count, float(ri_count))
                od_count = max(0.0, count - covered)

                if covered > 0.001:
                    rows.append(ec2_ri_covered_row(
                        hour_dt, cfg, covered,
                        ri["ri_hourly"], ri["ri_arn"], ri["ri_sub"],
                        ri["ri_start"], ri["ri_end"],
                    ))
                if od_count > 0.001:
                    rows.append(ec2_od_row(hour_dt, cfg, od_count))
            else:
                rows.append(ec2_od_row(hour_dt, cfg, count))

        # Lambda row
        lc = float(lambda_costs[h_idx])
        if lc > 0.0001:
            rows.append(lambda_row(hour_dt, lc, sp_hourly_commitment))

        # RDS row
        rc = float(rds_costs[h_idx])
        if rc > 0.001:
            rows.append(rds_row(hour_dt, rc))

        # EKS row
        ec = float(eks_costs[h_idx])
        if ec > 0.001:
            rows.append(eks_row(hour_dt, ec))

    # RIFee rows: one per day per active RI
    for ri in ri_cfgs:
        active_days = all_days[all_days >= ri["active_from"]]
        for day in active_days:
            rows.append(ec2_rifee_row(
                day.to_pydatetime(), ri["cfg"],
                float(ri["ri_count"]), ri["ri_hourly"],
                ri["ri_arn"], ri["ri_sub"],
                ri["ri_start"], ri["ri_end"],
            ))

    # S3 rows: one per day
    for d_idx, day in enumerate(all_days):
        cost = float(s3_daily[d_idx])
        gb = float(s3_storage_gb[d_idx])
        rows.append(s3_row(day.to_pydatetime(), cost, gb))

    print(f"  Generated {len(rows):,} total rows")

    # ── Step 6: split Jan-2025-only vs full ───────────────────────────────
    jan_start = "2025-01-01T00:00:00Z"
    jan_end   = "2025-02-01T00:00:00Z"
    jan_rows = [r for r in rows
                if jan_start <= r["line_item_usage_start_date"] < jan_end]

    print(f"  Jan 2025 rows: {len(jan_rows):,}")

    # ── Step 7: write CSVs ─────────────────────────────────────────────────
    def write_csv(path, data):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CUR_COLS)
            w.writeheader()
            w.writerows(data)
        size_mb = os.path.getsize(path) / 1_048_576
        print(f"Wrote {len(data):,} rows, {size_mb:.2f} MB → {path}")

    write_csv(OUT / "cur_sample_2025_01.csv", jan_rows)
    write_csv(OUT / "cur_sample_full.csv",    rows)

    # ── EDP discounts ──────────────────────────────────────────────────────
    edp_path = OUT / "edp_discounts.csv"
    with open(edp_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["service", "region", "discount_pct", "effective_date", "source"])
        for svc, region, pct in [
            ("AmazonEC2",  "us-east-1", "5.0"),
            ("AmazonEC2",  "us-west-2", "4.5"),
            ("AmazonEC2",  "eu-west-1", "4.0"),
            ("AmazonRDS",  "us-east-1", "3.0"),
            ("AWSLambda",  "us-east-1", "2.0"),
            ("AmazonS3",   "us-east-1", "1.5"),
            ("AmazonEKS",  "us-east-1", "2.5"),
            ("AmazonEC2",  "us-east-1", "5.5"),
            ("AmazonRDS",  "us-west-2", "2.5"),
            ("AmazonS3",   "us-west-2", "1.0"),
        ]:
            w.writerow([svc, region, pct, "2024-01-01", "manual"])
    print(f"Wrote {edp_path}")

    # ── Spot price history ─────────────────────────────────────────────────
    spot_path = OUT / "spot_price_history.csv"
    spot_rows = 0
    with open(spot_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region", "instance_type", "availability_zone", "timestamp", "price_usd_per_hour"])
        rng_spot = np.random.default_rng(999)
        for region, itype, az, od_price in [
            ("us-east-1", "m5.xlarge",  "us-east-1a", 0.192),
            ("us-east-1", "m5.large",   "us-east-1b", 0.096),
            ("us-east-1", "c5.xlarge",  "us-east-1c", 0.170),
            ("us-east-1", "r5.2xlarge", "us-east-1a", 0.504),
            ("us-west-2", "m5.2xlarge", "us-west-2a", 0.416),
            ("eu-west-1", "r5.large",   "eu-west-1a", 0.148),
        ]:
            # Sample every 6 hours over the full period
            sample_hours = pd.date_range(START_DT, NOW_DT, freq="6h", tz="UTC")
            spot_base = od_price * 0.35  # spot ~ 35% of OD base
            for sh in sample_hours:
                months = (sh - pd.Timestamp(START_DT)).total_seconds() / (30*24*3600)
                spot = spot_base * (1 + 0.01 * months) * (1 + rng_spot.normal(0, 0.08))
                spot = max(0.01, spot)
                w.writerow([region, itype, az, sh.strftime("%Y-%m-%dT%H:%M:%SZ"), f"{spot:.6f}"])
                spot_rows += 1
    print(f"Wrote {spot_path} ({spot_rows:,} rows)")

    # ── Instance pricing catalog ───────────────────────────────────────────
    pricing_path = OUT / "instance_pricing.csv"
    with open(pricing_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region","instance_type","od_hourly",
                    "convertible_1yr_hourly","convertible_3yr_hourly",
                    "standard_1yr_hourly","standard_3yr_hourly","effective_date","source"])
        for row in [
            ["us-east-1","m5.large",   "0.0960","0.0672","0.0513","0.0624","0.0480","2024-01-01","manual"],
            ["us-east-1","m5.xlarge",  "0.1920","0.1344","0.1026","0.1248","0.0960","2024-01-01","manual"],
            ["us-east-1","m5.2xlarge", "0.3840","0.2688","0.2052","0.2496","0.1920","2024-01-01","manual"],
            ["us-east-1","c5.xlarge",  "0.1700","0.1156","0.0884","0.1054","0.0816","2024-01-01","manual"],
            ["us-east-1","r5.large",   "0.1260","0.0882","0.0672","0.0819","0.0630","2024-01-01","manual"],
            ["us-east-1","r5.2xlarge", "0.5040","0.3528","0.2688","0.3276","0.2520","2024-01-01","manual"],
            ["us-west-2","m5.large",   "0.1040","0.0728","0.0555","0.0676","0.0520","2024-01-01","manual"],
            ["us-west-2","m5.xlarge",  "0.2080","0.1456","0.1112","0.1352","0.1040","2024-01-01","manual"],
            ["us-west-2","m5.2xlarge", "0.4160","0.2912","0.2224","0.2704","0.2080","2024-01-01","manual"],
            ["us-west-2","c5.xlarge",  "0.1810","0.1267","0.0968","0.1177","0.0905","2024-01-01","manual"],
            ["us-west-2","r5.large",   "0.1340","0.0938","0.0716","0.0871","0.0670","2024-01-01","manual"],
            ["eu-west-1","m5.large",   "0.1070","0.0749","0.0572","0.0696","0.0535","2024-01-01","manual"],
            ["eu-west-1","m5.xlarge",  "0.2140","0.1498","0.1144","0.1391","0.1070","2024-01-01","manual"],
            ["eu-west-1","c5.xlarge",  "0.1940","0.1358","0.1037","0.1261","0.0970","2024-01-01","manual"],
            ["eu-west-1","r5.large",   "0.1450","0.1015","0.0775","0.0943","0.0725","2024-01-01","manual"],
            ["eu-west-1","r5.2xlarge", "0.5800","0.4060","0.3100","0.3770","0.2900","2024-01-01","manual"],
            ["us-east-1","r5.2xlarge", "0.5040","0.3528","0.2688","0.3276","0.2520","2024-01-01","manual"],
            ["us-east-1","m5.2xlarge", "0.3840","0.2688","0.2052","0.2496","0.1920","2024-01-01","manual"],
            ["us-east-1","c5.2xlarge", "0.3400","0.2380","0.1820","0.2210","0.1700","2024-01-01","manual"],
        ]:
            w.writerow(row)
    print(f"Wrote {pricing_path}")

    # ── Manifest ───────────────────────────────────────────────────────────
    manifest_path = OUT / "cur_manifest_2025_01.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "assemblyId": "abc123", "account": PAYER,
            "columns": [{"category": "identity", "name": "line_item_id"}],
            "charset": "UTF-8", "compression": "GZIP", "contentType": "text/csv",
            "reportId": "acme-cur", "reportName": "acme-cur",
            "billingPeriod": {"start": "20250101T000000.000Z", "end": "20250201T000000.000Z"},
            "bucket": "acme-cur-bucket",
            "reportKeys": ["cur/2025-01/acme-cur-00001.csv.gz"],
        }, f, indent=2)
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
