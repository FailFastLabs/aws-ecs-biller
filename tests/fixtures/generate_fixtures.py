"""
Generate fake CUR fixture files deterministically (no random module).
Part 0 of the AWS CUR Analyzer project.
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

# ── Universe of values ──────────────────────────────────────────────────────
PAYER = "123456789012"
ACCOUNTS = [
    ("123456789012", "acme-prod", True),
    ("234567890123", "acme-dev", False),
    ("345678901234", "acme-staging", False),
]

RI_ARNS = {
    "ri-0a1b2c3d4e5f6789a": {
        "instance_type": "m5.large", "region": "us-east-1",
        "offering_class": "standard", "count": 10, "norm_factor": 4.0,
        "recurring_per_instance": 0.0624,
    },
    "ri-0b2c3d4e5f6789ab": {
        "instance_type": "c5.xlarge", "region": "us-east-1",
        "offering_class": "convertible", "count": 5, "norm_factor": 8.0,
        "recurring_per_instance": 0.0935,
    },
    "ri-0c3d4e5f6789abc": {
        "instance_type": "m5.2xlarge", "region": "us-west-2",
        "offering_class": "convertible", "count": 3, "norm_factor": 16.0,
        "recurring_per_instance": 0.2496,
    },
    "ri-0d4e5f6789abcd": {
        "instance_type": "r5.large", "region": "eu-west-1",
        "offering_class": "standard", "count": 4, "norm_factor": 4.0,
        "recurring_per_instance": 0.0819,
    },
}

SP_ARN = "arn:aws:savingsplans::123456789012:savingsplan/sp-abc123def456"

OD_RATES = {
    ("m5.large",   "us-east-1"): 0.0960,
    ("m5.xlarge",  "us-east-1"): 0.1920,
    ("m5.2xlarge", "us-east-1"): 0.3840,
    ("c5.xlarge",  "us-east-1"): 0.1700,
    ("c5.2xlarge", "us-east-1"): 0.3400,
    ("r5.large",   "us-east-1"): 0.1260,
    ("r5.2xlarge", "us-east-1"): 0.5040,
    ("t3.medium",  "us-east-1"): 0.0416,
    ("m5.large",   "us-west-2"): 0.1040,
    ("m5.xlarge",  "us-west-2"): 0.2080,
    ("m5.2xlarge", "us-west-2"): 0.4160,
    ("c5.xlarge",  "us-west-2"): 0.1810,
    ("c5.2xlarge", "us-west-2"): 0.3620,
    ("r5.large",   "us-west-2"): 0.1340,
    ("r5.2xlarge", "us-west-2"): 0.5360,
    ("m5.large",   "eu-west-1"): 0.1070,
    ("m5.xlarge",  "eu-west-1"): 0.2140,
    ("c5.xlarge",  "eu-west-1"): 0.1940,
    ("c5.2xlarge", "eu-west-1"): 0.3880,
    ("r5.large",   "eu-west-1"): 0.1450,
}

NORM_FACTORS = {
    "m5.large": 4.0, "m5.xlarge": 8.0, "m5.2xlarge": 16.0,
    "c5.xlarge": 8.0, "c5.2xlarge": 16.0,
    "r5.large": 4.0, "r5.2xlarge": 16.0,
    "t3.medium": 2.0,
}

FAMILIES = {
    "m5.large": "m5", "m5.xlarge": "m5", "m5.2xlarge": "m5",
    "c5.xlarge": "c5", "c5.2xlarge": "c5",
    "r5.large": "r5", "r5.2xlarge": "r5",
    "t3.medium": "t3",
}

TAGS = [
    '{"user:team": "backend", "user:env": "prod", "user:app": "api-server"}',
    '{"user:team": "frontend", "user:env": "prod", "user:app": "web-app"}',
    '{"user:team": "data", "user:env": "prod", "user:app": "spark-cluster"}',
    '{"user:team": "backend", "user:env": "staging", "user:app": "api-server"}',
    '{"user:team": "platform", "user:env": "prod", "user:app": "k8s-system"}',
]

# Anomaly week: Jan 13-17 (Mon-Fri)
ANOMALY_START = datetime(2025, 1, 13, tzinfo=timezone.utc)
ANOMALY_END   = datetime(2025, 1, 18, tzinfo=timezone.utc)

def is_anomaly_hour(dt: datetime) -> bool:
    return ANOMALY_START <= dt < ANOMALY_END

def usage_scale(dt: datetime) -> float:
    """Deterministic usage scale based on hour and day."""
    hour = dt.hour
    dow  = dt.weekday()  # 0=Mon, 6=Sun
    if dow >= 5:   # weekend
        return 0.4
    if 8 <= hour <= 18:
        return 1.0
    return 0.7

def get_scale(dt: datetime, account_id: str, region: str) -> float:
    scale = usage_scale(dt)
    if is_anomaly_hour(dt) and account_id == "123456789012" and region == "us-east-1":
        scale = 3.0
    return scale

# ── CSV header ───────────────────────────────────────────────────────────────
HEADER = [
    "identity_line_item_id", "identity_time_interval",
    "bill_bill_type", "bill_billing_entity",
    "bill_billing_period_start_date", "bill_billing_period_end_date",
    "bill_invoice_id", "bill_payer_account_id", "bill_payer_account_name",
    "line_item_usage_account_id", "line_item_usage_account_name",
    "line_item_usage_start_date", "line_item_usage_end_date",
    "line_item_line_item_type", "line_item_product_code",
    "line_item_usage_type", "line_item_operation",
    "line_item_resource_id", "line_item_availability_zone",
    "line_item_usage_amount", "line_item_unblended_cost",
    "line_item_blended_cost", "line_item_net_unblended_cost",
    "line_item_normalization_factor", "line_item_normalized_usage_amount",
    "line_item_line_item_description", "line_item_currency_code",
    "pricing_term", "pricing_unit", "pricing_public_on_demand_cost",
    "pricing_public_on_demand_rate", "pricing_offering_class",
    "pricing_purchase_option", "pricing_lease_contract_length",
    "product_region_code", "product_instance_type",
    "product_instance_family", "product_product_family",
    "product_servicecode", "product_sku",
    "reservation_reservation_a_r_n", "reservation_effective_cost",
    "reservation_amortized_upfront_cost_for_usage",
    "reservation_recurring_fee_for_usage",
    "reservation_unused_quantity", "reservation_unused_recurring_fee",
    "reservation_normalized_units_per_reservation",
    "reservation_number_of_reservations",
    "reservation_start_time", "reservation_end_time",
    "reservation_subscription_id",
    "savings_plan_savings_plan_a_r_n",
    "savings_plan_savings_plan_effective_cost",
    "savings_plan_offering_type", "savings_plan_payment_option",
    "savings_plan_purchase_term", "savings_plan_region",
    "savings_plan_used_commitment", "savings_plan_total_commitment_to_date",
    "split_line_item_split_cost", "split_line_item_actual_usage",
    "split_line_item_split_usage_ratio", "split_line_item_parent_resource_id",
    "resource_tags", "cost_category", "discount_total_discount",
]

def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def make_empty_row(line_item_id: str, dt: datetime, acct_id: str, acct_name: str) -> dict:
    end_dt = dt + timedelta(hours=1)
    return {
        "identity_line_item_id": line_item_id,
        "identity_time_interval": f"{fmt_dt(dt)}/{fmt_dt(end_dt)}",
        "bill_bill_type": "Anniversary",
        "bill_billing_entity": "AWS",
        "bill_billing_period_start_date": "2025-01-01T00:00:00Z",
        "bill_billing_period_end_date": "2025-02-01T00:00:00Z",
        "bill_invoice_id": "INV-20250101",
        "bill_payer_account_id": PAYER,
        "bill_payer_account_name": "acme-prod",
        "line_item_usage_account_id": acct_id,
        "line_item_usage_account_name": acct_name,
        "line_item_usage_start_date": fmt_dt(dt),
        "line_item_usage_end_date": fmt_dt(end_dt),
        "line_item_line_item_type": "",
        "line_item_product_code": "",
        "line_item_usage_type": "",
        "line_item_operation": "",
        "line_item_resource_id": "",
        "line_item_availability_zone": "",
        "line_item_usage_amount": "0",
        "line_item_unblended_cost": "0",
        "line_item_blended_cost": "0",
        "line_item_net_unblended_cost": "0",
        "line_item_normalization_factor": "",
        "line_item_normalized_usage_amount": "0",
        "line_item_line_item_description": "",
        "line_item_currency_code": "USD",
        "pricing_term": "",
        "pricing_unit": "",
        "pricing_public_on_demand_cost": "0",
        "pricing_public_on_demand_rate": "0",
        "pricing_offering_class": "",
        "pricing_purchase_option": "",
        "pricing_lease_contract_length": "",
        "product_region_code": "",
        "product_instance_type": "",
        "product_instance_family": "",
        "product_product_family": "",
        "product_servicecode": "",
        "product_sku": "",
        "reservation_reservation_a_r_n": "",
        "reservation_effective_cost": "0",
        "reservation_amortized_upfront_cost_for_usage": "0",
        "reservation_recurring_fee_for_usage": "0",
        "reservation_unused_quantity": "0",
        "reservation_unused_recurring_fee": "0",
        "reservation_normalized_units_per_reservation": "0",
        "reservation_number_of_reservations": "0",
        "reservation_start_time": "",
        "reservation_end_time": "",
        "reservation_subscription_id": "",
        "savings_plan_savings_plan_a_r_n": "",
        "savings_plan_savings_plan_effective_cost": "0",
        "savings_plan_offering_type": "",
        "savings_plan_payment_option": "",
        "savings_plan_purchase_term": "",
        "savings_plan_region": "",
        "savings_plan_used_commitment": "0",
        "savings_plan_total_commitment_to_date": "0",
        "split_line_item_split_cost": "0",
        "split_line_item_actual_usage": "0",
        "split_line_item_split_usage_ratio": "0",
        "split_line_item_parent_resource_id": "",
        "resource_tags": "",
        "cost_category": "",
        "discount_total_discount": "0",
    }


def generate_rows():
    rows = []
    seq = [0]  # mutable counter

    def next_id(date_str, hour, acct, svc, res):
        seq[0] += 1
        return f"li-{date_str}-{hour:02d}-{acct}-{svc}-{res}-{seq[0]:05d}"

    # Jan 2025: hourly from Jan 1 00:00 through Jan 31 23:00
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    hours = [start + timedelta(hours=h) for h in range(31 * 24)]  # 744 hours

    for dt in hours:
        date_str = dt.strftime("%Y%m%d")
        hour = dt.hour
        dow = dt.weekday()

        # ── Pattern A: On-Demand EC2 (acme-dev: 3× m5.large us-east-1) ──────
        acct_id, acct_name = "234567890123", "acme-dev"
        scale = get_scale(dt, acct_id, "us-east-1")
        usage = round(3.0 * scale, 4)
        od = OD_RATES[("m5.large", "us-east-1")]
        cost = round(usage * od, 10)
        row = make_empty_row(
            next_id(date_str, hour, "dev", "ec2", "m5lg"), dt, acct_id, acct_name
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonEC2",
            "line_item_usage_type": "USE1-BoxUsage:m5.large",
            "line_item_operation": "RunInstances",
            "line_item_resource_id": "i-0dev-m5lg-001",
            "line_item_availability_zone": "us-east-1a",
            "line_item_usage_amount": str(usage),
            "line_item_unblended_cost": str(cost),
            "line_item_blended_cost": str(cost),
            "line_item_net_unblended_cost": str(round(cost * 0.95, 10)),
            "line_item_normalization_factor": str(NORM_FACTORS["m5.large"]),
            "line_item_normalized_usage_amount": str(round(usage * NORM_FACTORS["m5.large"], 4)),
            "line_item_line_item_description": "$0.096 per On Demand Linux m5.large Instance Hour",
            "pricing_term": "OnDemand",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(cost),
            "pricing_public_on_demand_rate": str(od),
            "product_region_code": "us-east-1",
            "product_instance_type": "m5.large",
            "product_instance_family": "m5",
            "product_product_family": "Compute Instance",
            "product_servicecode": "AmazonEC2",
            "product_sku": "4NA7Y4WS69NRXPCS",
            "resource_tags": TAGS[0],
        })
        rows.append(row)

        # ── Pattern A: On-Demand EC2 (acme-staging: 2× c5.xlarge us-west-2, weekdays 9am-6pm) ──
        acct_id, acct_name = "345678901234", "acme-staging"
        if dow < 5 and 9 <= hour <= 18:
            stg_usage = 2.0
        else:
            stg_usage = 0.05
        od_stg = OD_RATES[("c5.xlarge", "us-west-2")]
        cost_stg = round(stg_usage * od_stg, 10)
        row = make_empty_row(
            next_id(date_str, hour, "stg", "ec2", "c5xl"), dt, acct_id, acct_name
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonEC2",
            "line_item_usage_type": "USW2-BoxUsage:c5.xlarge",
            "line_item_operation": "RunInstances",
            "line_item_resource_id": "i-0stg-c5xl-001",
            "line_item_availability_zone": "us-west-2a",
            "line_item_usage_amount": str(stg_usage),
            "line_item_unblended_cost": str(cost_stg),
            "line_item_blended_cost": str(cost_stg),
            "line_item_net_unblended_cost": str(round(cost_stg * 0.95, 10)),
            "line_item_normalization_factor": str(NORM_FACTORS["c5.xlarge"]),
            "line_item_normalized_usage_amount": str(round(stg_usage * NORM_FACTORS["c5.xlarge"], 4)),
            "line_item_line_item_description": "$0.181 per On Demand Linux c5.xlarge Instance Hour",
            "pricing_term": "OnDemand",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(cost_stg),
            "pricing_public_on_demand_rate": str(od_stg),
            "product_region_code": "us-west-2",
            "product_instance_type": "c5.xlarge",
            "product_instance_family": "c5",
            "product_product_family": "Compute Instance",
            "product_servicecode": "AmazonEC2",
            "product_sku": "X7KYJZB2NDKQQ2YZ",
            "resource_tags": TAGS[3],
        })
        rows.append(row)

        # ── Pattern A: On-Demand EC2 (prod: 8× m5.xlarge overflow above RI) ──
        acct_id, acct_name = "123456789012", "acme-prod"
        scale = get_scale(dt, acct_id, "us-east-1")
        od_usage = round(8.0 * scale, 4)
        od_mxl = OD_RATES[("m5.xlarge", "us-east-1")]
        cost_od = round(od_usage * od_mxl, 10)
        row = make_empty_row(
            next_id(date_str, hour, "prod", "ec2", "m5xl"), dt, acct_id, acct_name
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonEC2",
            "line_item_usage_type": "USE1-BoxUsage:m5.xlarge",
            "line_item_operation": "RunInstances",
            "line_item_resource_id": "i-0prod-m5xl-001",
            "line_item_availability_zone": "us-east-1b",
            "line_item_usage_amount": str(od_usage),
            "line_item_unblended_cost": str(cost_od),
            "line_item_blended_cost": str(cost_od),
            "line_item_net_unblended_cost": str(round(cost_od * 0.95, 10)),
            "line_item_normalization_factor": str(NORM_FACTORS["m5.xlarge"]),
            "line_item_normalized_usage_amount": str(round(od_usage * NORM_FACTORS["m5.xlarge"], 4)),
            "line_item_line_item_description": "$0.192 per On Demand Linux m5.xlarge Instance Hour",
            "pricing_term": "OnDemand",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(cost_od),
            "pricing_public_on_demand_rate": str(od_mxl),
            "product_region_code": "us-east-1",
            "product_instance_type": "m5.xlarge",
            "product_instance_family": "m5",
            "product_product_family": "Compute Instance",
            "product_servicecode": "AmazonEC2",
            "product_sku": "8NCS5QAR9CRNXQD4",
            "resource_tags": TAGS[0],
        })
        rows.append(row)

        # ── Pattern B: RI-Covered EC2 — m5.large (10× fully covered) ─────────
        ri_arn_a = "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-0a1b2c3d4e5f6789a"
        ri_rate = 0.0624
        ri_usage = 10.0
        ri_cost = round(ri_usage * ri_rate, 10)
        row = make_empty_row(
            next_id(date_str, hour, "prod", "ri", "m5lg"), dt, "123456789012", "acme-prod"
        )
        row.update({
            "line_item_line_item_type": "DiscountedUsage",
            "line_item_product_code": "AmazonEC2",
            "line_item_usage_type": "USE1-BoxUsage:m5.large",
            "line_item_operation": "RunInstances:SSD",
            "line_item_resource_id": "i-0ri-m5lg-001",
            "line_item_availability_zone": "us-east-1a",
            "line_item_usage_amount": str(ri_usage),
            "line_item_unblended_cost": str(ri_cost),
            "line_item_blended_cost": str(ri_cost),
            "line_item_net_unblended_cost": str(ri_cost),
            "line_item_normalization_factor": "4.0",
            "line_item_normalized_usage_amount": str(ri_usage * 4.0),
            "line_item_line_item_description": "Linux/UNIX m5.large reserved instance applied",
            "line_item_currency_code": "USD",
            "pricing_term": "Reserved",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(round(ri_usage * OD_RATES[("m5.large", "us-east-1")], 10)),
            "pricing_public_on_demand_rate": str(OD_RATES[("m5.large", "us-east-1")]),
            "pricing_offering_class": "standard",
            "pricing_purchase_option": "No Upfront",
            "pricing_lease_contract_length": "3yr",
            "product_region_code": "us-east-1",
            "product_instance_type": "m5.large",
            "product_instance_family": "m5",
            "product_product_family": "Compute Instance",
            "product_servicecode": "AmazonEC2",
            "product_sku": "4NA7Y4WS69NRXPCS",
            "reservation_reservation_a_r_n": ri_arn_a,
            "reservation_effective_cost": str(ri_cost),
            "reservation_amortized_upfront_cost_for_usage": "0",
            "reservation_recurring_fee_for_usage": str(ri_cost),
            "reservation_unused_quantity": "0",
            "reservation_unused_recurring_fee": "0",
            "reservation_normalized_units_per_reservation": "4.0",
            "reservation_number_of_reservations": "10",
            "reservation_start_time": "2024-01-01T00:00:00Z",
            "reservation_end_time": "2027-01-01T00:00:00Z",
            "reservation_subscription_id": "sub-0a1b2c3d",
            "resource_tags": TAGS[4],
        })
        rows.append(row)

        # ── Pattern B: RI-Covered EC2 — c5.xlarge (5× convertible, 2 unused on weekends) ──
        ri_arn_b = "arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-0b2c3d4e5f6789ab"
        c5_rate = 0.0935
        if dow >= 5:  # weekend: 3 of 5 utilized
            c5_utilized = 3.0
            c5_unused = 2.0
        else:
            c5_utilized = 5.0
            c5_unused = 0.0

        # DiscountedUsage for utilized portion
        c5_cost = round(c5_utilized * c5_rate, 10)
        row = make_empty_row(
            next_id(date_str, hour, "prod", "ri", "c5xl"), dt, "123456789012", "acme-prod"
        )
        row.update({
            "line_item_line_item_type": "DiscountedUsage",
            "line_item_product_code": "AmazonEC2",
            "line_item_usage_type": "USE1-BoxUsage:c5.xlarge",
            "line_item_operation": "RunInstances",
            "line_item_resource_id": "i-0ri-c5xl-001",
            "line_item_availability_zone": "us-east-1c",
            "line_item_usage_amount": str(c5_utilized),
            "line_item_unblended_cost": str(c5_cost),
            "line_item_blended_cost": str(c5_cost),
            "line_item_net_unblended_cost": str(c5_cost),
            "line_item_normalization_factor": "8.0",
            "line_item_normalized_usage_amount": str(c5_utilized * 8.0),
            "line_item_line_item_description": "Linux/UNIX c5.xlarge convertible reserved instance applied",
            "line_item_currency_code": "USD",
            "pricing_term": "Reserved",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(round(c5_utilized * OD_RATES[("c5.xlarge", "us-east-1")], 10)),
            "pricing_public_on_demand_rate": str(OD_RATES[("c5.xlarge", "us-east-1")]),
            "pricing_offering_class": "convertible",
            "pricing_purchase_option": "No Upfront",
            "pricing_lease_contract_length": "3yr",
            "product_region_code": "us-east-1",
            "product_instance_type": "c5.xlarge",
            "product_instance_family": "c5",
            "product_product_family": "Compute Instance",
            "product_servicecode": "AmazonEC2",
            "product_sku": "X7KYJZB2NDKQQ2YZ",
            "reservation_reservation_a_r_n": ri_arn_b,
            "reservation_effective_cost": str(c5_cost),
            "reservation_amortized_upfront_cost_for_usage": "0",
            "reservation_recurring_fee_for_usage": str(c5_cost),
            "reservation_unused_quantity": str(c5_unused),
            "reservation_unused_recurring_fee": str(round(c5_unused * c5_rate, 10)),
            "reservation_normalized_units_per_reservation": "8.0",
            "reservation_number_of_reservations": "5",
            "reservation_start_time": "2024-06-01T00:00:00Z",
            "reservation_end_time": "2027-06-01T00:00:00Z",
            "reservation_subscription_id": "sub-0b2c3d4e",
            "resource_tags": TAGS[0],
        })
        rows.append(row)

        # ── Pattern C: RIFee rows for each RI ARN ────────────────────────────
        for ri_id, ri_info in RI_ARNS.items():
            full_arn = f"arn:aws:ec2:{ri_info['region']}:123456789012:reserved-instances/{ri_id}"
            count = ri_info["count"]
            rate = ri_info["recurring_per_instance"]
            total_hourly = round(count * rate, 10)
            norm_u = ri_info["norm_factor"]
            itype = ri_info["instance_type"]
            region = ri_info["region"]

            # Map region to usage type prefix
            region_prefix = {"us-east-1": "USE1", "us-west-2": "USW2", "eu-west-1": "EUW1"}[region]

            row = make_empty_row(
                next_id(date_str, hour, "prod", "rifee", ri_id[-4:]), dt, "123456789012", "acme-prod"
            )
            row.update({
                "line_item_line_item_type": "RIFee",
                "line_item_product_code": "AmazonEC2",
                "line_item_usage_type": f"{region_prefix}-HeavyUsage:{itype}",
                "line_item_operation": "RunInstances",
                "line_item_resource_id": full_arn,
                "line_item_availability_zone": f"{region}a",
                "line_item_usage_amount": str(float(count)),
                "line_item_unblended_cost": str(total_hourly),
                "line_item_blended_cost": str(total_hourly),
                "line_item_net_unblended_cost": str(total_hourly),
                "line_item_normalization_factor": str(norm_u),
                "line_item_normalized_usage_amount": str(count * norm_u),
                "line_item_line_item_description": f"Fee for {count} reserved {itype} instance(s)",
                "line_item_currency_code": "USD",
                "pricing_term": "Reserved",
                "pricing_unit": "Hrs",
                "pricing_public_on_demand_cost": "0",
                "pricing_public_on_demand_rate": "0",
                "pricing_offering_class": ri_info["offering_class"],
                "pricing_purchase_option": "No Upfront",
                "pricing_lease_contract_length": "3yr",
                "product_region_code": region,
                "product_instance_type": itype,
                "product_instance_family": FAMILIES[itype],
                "product_product_family": "Compute Instance",
                "product_servicecode": "AmazonEC2",
                "product_sku": f"SKU{ri_id[-8:].upper()}",
                "reservation_reservation_a_r_n": full_arn,
                "reservation_effective_cost": str(total_hourly),
                "reservation_amortized_upfront_cost_for_usage": "0",
                "reservation_recurring_fee_for_usage": str(total_hourly),
                "reservation_unused_quantity": "0",
                "reservation_unused_recurring_fee": "0",
                "reservation_normalized_units_per_reservation": str(norm_u),
                "reservation_number_of_reservations": str(count),
                "reservation_start_time": "2024-01-01T00:00:00Z",
                "reservation_end_time": "2027-01-01T00:00:00Z",
                "reservation_subscription_id": f"sub-{ri_id[-8:]}",
                "resource_tags": TAGS[4],
            })
            rows.append(row)

        # ── Pattern D: Savings Plan covered usage ─────────────────────────────
        sp_usage = round(2.0 * get_scale(dt, "123456789012", "us-east-1"), 4)
        sp_od_rate = OD_RATES[("m5.2xlarge", "us-east-1")]
        sp_rate = round(sp_od_rate * 0.80, 6)  # SP covers at 80% of OD
        sp_od_cost = round(sp_usage * sp_od_rate, 10)
        sp_eff_cost = round(sp_usage * sp_rate, 10)
        row = make_empty_row(
            next_id(date_str, hour, "prod", "sp", "m52xl"), dt, "123456789012", "acme-prod"
        )
        row.update({
            "line_item_line_item_type": "SavingsPlanCoveredUsage",
            "line_item_product_code": "AmazonEC2",
            "line_item_usage_type": "USE1-BoxUsage:m5.2xlarge",
            "line_item_operation": "RunInstances",
            "line_item_resource_id": "i-0prod-m52xl-sp-001",
            "line_item_availability_zone": "us-east-1a",
            "line_item_usage_amount": str(sp_usage),
            "line_item_unblended_cost": str(sp_eff_cost),
            "line_item_blended_cost": str(sp_eff_cost),
            "line_item_net_unblended_cost": str(sp_eff_cost),
            "line_item_normalization_factor": "16.0",
            "line_item_normalized_usage_amount": str(round(sp_usage * 16.0, 4)),
            "line_item_line_item_description": "m5.2xlarge Linux covered by Compute Savings Plan",
            "line_item_currency_code": "USD",
            "pricing_term": "SavingsPlan",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(sp_od_cost),
            "pricing_public_on_demand_rate": str(sp_od_rate),
            "product_region_code": "us-east-1",
            "product_instance_type": "m5.2xlarge",
            "product_instance_family": "m5",
            "product_product_family": "Compute Instance",
            "product_servicecode": "AmazonEC2",
            "product_sku": "AWSSP2XLARGE001",
            "savings_plan_savings_plan_a_r_n": SP_ARN,
            "savings_plan_savings_plan_effective_cost": str(sp_eff_cost),
            "savings_plan_offering_type": "ComputeSavingsPlan",
            "savings_plan_payment_option": "No Upfront",
            "savings_plan_purchase_term": "1yr",
            "savings_plan_region": "us-east-1",
            "savings_plan_used_commitment": str(sp_eff_cost),
            "savings_plan_total_commitment_to_date": "2.50",
            "resource_tags": TAGS[0],
        })
        rows.append(row)

        # ── Pattern E: RDS ────────────────────────────────────────────────────
        # prod: 2× db.r5.large always on
        rds_od = 0.1260  # r5.large us-east-1 OD
        rds_cost = round(2.0 * rds_od, 10)
        row = make_empty_row(
            next_id(date_str, hour, "prod", "rds", "r5lg"), dt, "123456789012", "acme-prod"
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonRDS",
            "line_item_usage_type": "USE1-InstanceUsage:db.r5.large",
            "line_item_operation": "CreateDBInstance:0014",
            "line_item_resource_id": "db-prod-r5lg-001",
            "line_item_availability_zone": "us-east-1a",
            "line_item_usage_amount": "2.0",
            "line_item_unblended_cost": str(rds_cost),
            "line_item_blended_cost": str(rds_cost),
            "line_item_net_unblended_cost": str(round(rds_cost * 0.97, 10)),
            "line_item_normalization_factor": "4.0",
            "line_item_normalized_usage_amount": "8.0",
            "line_item_line_item_description": "$0.126 per RDS db.r5.large Multi-AZ instance hour",
            "line_item_currency_code": "USD",
            "pricing_term": "OnDemand",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(rds_cost),
            "pricing_public_on_demand_rate": str(rds_od),
            "product_region_code": "us-east-1",
            "product_instance_type": "db.r5.large",
            "product_instance_family": "r5",
            "product_product_family": "Database Instance",
            "product_servicecode": "AmazonRDS",
            "product_sku": "RDSR5LARGE001",
            "resource_tags": TAGS[2],
        })
        rows.append(row)

        # dev: 1× db.r5.large always on
        rds_dev_cost = round(1.0 * rds_od, 10)
        row = make_empty_row(
            next_id(date_str, hour, "dev", "rds", "r5lg"), dt, "234567890123", "acme-dev"
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonRDS",
            "line_item_usage_type": "USE1-InstanceUsage:db.r5.large",
            "line_item_operation": "CreateDBInstance:0014",
            "line_item_resource_id": "db-dev-r5lg-001",
            "line_item_availability_zone": "us-east-1b",
            "line_item_usage_amount": "1.0",
            "line_item_unblended_cost": str(rds_dev_cost),
            "line_item_blended_cost": str(rds_dev_cost),
            "line_item_net_unblended_cost": str(round(rds_dev_cost * 0.97, 10)),
            "line_item_normalization_factor": "4.0",
            "line_item_normalized_usage_amount": "4.0",
            "line_item_line_item_description": "$0.126 per RDS db.r5.large instance hour",
            "line_item_currency_code": "USD",
            "pricing_term": "OnDemand",
            "pricing_unit": "Hrs",
            "pricing_public_on_demand_cost": str(rds_dev_cost),
            "pricing_public_on_demand_rate": str(rds_od),
            "product_region_code": "us-east-1",
            "product_instance_type": "db.r5.large",
            "product_instance_family": "r5",
            "product_product_family": "Database Instance",
            "product_servicecode": "AmazonRDS",
            "product_sku": "RDSR5LARGE002",
            "resource_tags": TAGS[3],
        })
        rows.append(row)

        # ── Pattern G: EKS cluster fee ($0.10/hr) ────────────────────────────
        eks_cost = 0.10
        row = make_empty_row(
            next_id(date_str, hour, "prod", "eks", "cluster"), dt, "123456789012", "acme-prod"
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonEKS",
            "line_item_usage_type": "USE1-AmazonEKS-Hours:perCluster",
            "line_item_operation": "EKSCluster",
            "line_item_resource_id": "i-0eks-cluster-prod-001",
            "line_item_availability_zone": "us-east-1a",
            "line_item_usage_amount": "1.0",
            "line_item_unblended_cost": str(eks_cost),
            "line_item_blended_cost": str(eks_cost),
            "line_item_net_unblended_cost": str(round(eks_cost * 0.97, 10)),
            "line_item_normalization_factor": "",
            "line_item_normalized_usage_amount": "0",
            "line_item_line_item_description": "$0.10 per Amazon EKS cluster per hour",
            "line_item_currency_code": "USD",
            "pricing_term": "OnDemand",
            "pricing_unit": "Hours",
            "pricing_public_on_demand_cost": str(eks_cost),
            "pricing_public_on_demand_rate": str(eks_cost),
            "product_region_code": "us-east-1",
            "product_instance_type": "",
            "product_instance_family": "",
            "product_product_family": "Compute",
            "product_servicecode": "AmazonEKS",
            "product_sku": "EKSCLUSTER001",
            # EKS cost splitting: include split columns
            "split_line_item_split_cost": str(round(eks_cost * 0.40, 10)),
            "split_line_item_actual_usage": "1.0",
            "split_line_item_split_usage_ratio": "0.40",
            "split_line_item_parent_resource_id": "i-0eks-cluster-prod-001",
            "resource_tags": TAGS[4],
        })
        rows.append(row)

        # ── Pattern G: Lambda GB-seconds ─────────────────────────────────────
        # Vary by hour of day: more during business hours
        lambda_gb_sec = round(1000.0 * usage_scale(dt), 2)
        lambda_rate = 0.0000166667  # per GB-second
        lambda_cost = round(lambda_gb_sec * lambda_rate, 10)
        row = make_empty_row(
            next_id(date_str, hour, "prod", "lambda", "gbsec"), dt, "123456789012", "acme-prod"
        )
        row.update({
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AWSLambda",
            "line_item_usage_type": "USE1-Lambda-GB-Second",
            "line_item_operation": "Invoke",
            "line_item_resource_id": "arn:aws:lambda:us-east-1:123456789012:function:api-processor",
            "line_item_availability_zone": "",
            "line_item_usage_amount": str(lambda_gb_sec),
            "line_item_unblended_cost": str(lambda_cost),
            "line_item_blended_cost": str(lambda_cost),
            "line_item_net_unblended_cost": str(lambda_cost),
            "line_item_normalization_factor": "",
            "line_item_normalized_usage_amount": "0",
            "line_item_line_item_description": "$0.0000166667 per GB-second",
            "line_item_currency_code": "USD",
            "pricing_term": "OnDemand",
            "pricing_unit": "GB-Second",
            "pricing_public_on_demand_cost": str(lambda_cost),
            "pricing_public_on_demand_rate": str(lambda_rate),
            "product_region_code": "us-east-1",
            "product_product_family": "Serverless",
            "product_servicecode": "AWSLambda",
            "product_sku": "LAMBDA001",
            "resource_tags": TAGS[1],
        })
        rows.append(row)

    # ── Pattern F: S3 — daily storage rows (one per day) ─────────────────────
    for day in range(31):
        dt = datetime(2025, 1, day + 1, 0, 0, tzinfo=timezone.utc)
        date_str = dt.strftime("%Y%m%d")
        end_dt = dt + timedelta(days=1)
        # Storage: 50 TB = 50 * 1024^4 / (1024^3) GB-hrs (approximately)
        # Actually TB-mo → simplify to bytes per day
        storage_bytes = 50.0 * 1024 * 1024 * 1024 * 1024  # 50 TB in bytes
        storage_gb_mo = round(storage_bytes / (1024 * 1024 * 1024), 4)  # GB
        # S3 standard storage: $0.023 per GB-month, pro-rate to per-day
        s3_storage_cost = round(storage_gb_mo * 0.023 / 30, 10)
        row = {k: "" for k in HEADER}
        seq[0] += 1
        row.update({
            "identity_line_item_id": f"li-{date_str}-00-prod-s3-stor-{seq[0]:05d}",
            "identity_time_interval": f"{fmt_dt(dt)}/{fmt_dt(end_dt)}",
            "bill_bill_type": "Anniversary",
            "bill_billing_entity": "AWS",
            "bill_billing_period_start_date": "2025-01-01T00:00:00Z",
            "bill_billing_period_end_date": "2025-02-01T00:00:00Z",
            "bill_invoice_id": "INV-20250101",
            "bill_payer_account_id": PAYER,
            "bill_payer_account_name": "acme-prod",
            "line_item_usage_account_id": "123456789012",
            "line_item_usage_account_name": "acme-prod",
            "line_item_usage_start_date": fmt_dt(dt),
            "line_item_usage_end_date": fmt_dt(end_dt),
            "line_item_line_item_type": "Usage",
            "line_item_product_code": "AmazonS3",
            "line_item_usage_type": "USE1-TimedStorage-ByteHrs",
            "line_item_operation": "StandardStorage",
            "line_item_resource_id": "arn:aws:s3:::acme-data-lake",
            "line_item_availability_zone": "",
            "line_item_usage_amount": str(round(storage_bytes * 24, 4)),  # byte-hours
            "line_item_unblended_cost": str(s3_storage_cost),
            "line_item_blended_cost": str(s3_storage_cost),
            "line_item_net_unblended_cost": str(round(s3_storage_cost * 0.98, 10)),
            "line_item_normalization_factor": "",
            "line_item_normalized_usage_amount": "0",
            "line_item_line_item_description": "$0.023 per GB - US East (Northern Virginia) Standard Storage",
            "line_item_currency_code": "USD",
            "pricing_term": "OnDemand",
            "pricing_unit": "GB-Mo",
            "pricing_public_on_demand_cost": str(s3_storage_cost),
            "pricing_public_on_demand_rate": "0.023",
            "pricing_offering_class": "",
            "pricing_purchase_option": "",
            "pricing_lease_contract_length": "",
            "product_region_code": "us-east-1",
            "product_instance_type": "",
            "product_instance_family": "",
            "product_product_family": "Storage",
            "product_servicecode": "AmazonS3",
            "product_sku": "S3STORAGE001",
            "reservation_reservation_a_r_n": "",
            "reservation_effective_cost": "0",
            "reservation_amortized_upfront_cost_for_usage": "0",
            "reservation_recurring_fee_for_usage": "0",
            "reservation_unused_quantity": "0",
            "reservation_unused_recurring_fee": "0",
            "reservation_normalized_units_per_reservation": "0",
            "reservation_number_of_reservations": "0",
            "reservation_start_time": "",
            "reservation_end_time": "",
            "reservation_subscription_id": "",
            "savings_plan_savings_plan_a_r_n": "",
            "savings_plan_savings_plan_effective_cost": "0",
            "savings_plan_offering_type": "",
            "savings_plan_payment_option": "",
            "savings_plan_purchase_term": "",
            "savings_plan_region": "",
            "savings_plan_used_commitment": "0",
            "savings_plan_total_commitment_to_date": "0",
            "split_line_item_split_cost": "0",
            "split_line_item_actual_usage": "0",
            "split_line_item_split_usage_ratio": "0",
            "split_line_item_parent_resource_id": "",
            "resource_tags": TAGS[2],
            "cost_category": "",
            "discount_total_discount": "0",
        })
        rows.append(row)

        # S3 requests (hourly, per day via 24 rows)
        for h in range(24):
            hour_dt = datetime(2025, 1, day + 1, h, 0, tzinfo=timezone.utc)
            s3_reqs = round(5000.0 * usage_scale(hour_dt), 0)
            s3_req_cost = round(s3_reqs * 0.0000004, 10)  # $0.0004 per 1000 requests = $0.0000004 per req
            seq[0] += 1
            row2 = make_empty_row(
                f"li-{date_str}-{h:02d}-prod-s3-req-{seq[0]:05d}", hour_dt,
                "123456789012", "acme-prod"
            )
            row2.update({
                "line_item_line_item_type": "Usage",
                "line_item_product_code": "AmazonS3",
                "line_item_usage_type": "USE1-Requests-Tier1",
                "line_item_operation": "GetObject",
                "line_item_resource_id": "arn:aws:s3:::acme-data-lake",
                "line_item_availability_zone": "",
                "line_item_usage_amount": str(s3_reqs),
                "line_item_unblended_cost": str(s3_req_cost),
                "line_item_blended_cost": str(s3_req_cost),
                "line_item_net_unblended_cost": str(s3_req_cost),
                "line_item_normalization_factor": "",
                "line_item_normalized_usage_amount": "0",
                "line_item_line_item_description": "$0.004 per 10,000 GET and SELECT requests",
                "line_item_currency_code": "USD",
                "pricing_term": "OnDemand",
                "pricing_unit": "Requests",
                "pricing_public_on_demand_cost": str(s3_req_cost),
                "pricing_public_on_demand_rate": "0.0000004",
                "product_region_code": "us-east-1",
                "product_product_family": "API Request",
                "product_servicecode": "AmazonS3",
                "product_sku": "S3REQUESTS001",
                "resource_tags": TAGS[2],
            })
            rows.append(row2)

    return rows


def main():
    out_dir = os.path.dirname(__file__)
    cur_path = os.path.join(out_dir, "cur_sample_2025_01.csv")

    print("Generating CUR rows...")
    rows = generate_rows()
    print(f"Total rows: {len(rows)}")

    with open(cur_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)

    size = os.path.getsize(cur_path)
    print(f"File size: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")

    # ── EDP Discounts ──────────────────────────────────────────────────────
    edp_path = os.path.join(out_dir, "edp_discounts.csv")
    with open(edp_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["service", "region", "discount_pct"])
        w.writerows([
            ["AmazonEC2",       "us-east-1", "5.0"],
            ["AmazonEC2",       "us-west-2", "5.0"],
            ["AmazonEC2",       "eu-west-1", "4.0"],
            ["AmazonRDS",       "us-east-1", "3.0"],
            ["AmazonRDS",       "us-west-2", "3.0"],
            ["AmazonS3",        "us-east-1", "2.0"],
            ["AmazonS3",        "us-west-2", "2.0"],
            ["AWSLambda",       "us-east-1", "1.0"],
            ["AmazonEKS",       "us-east-1", "3.0"],
            ["AmazonCloudFront","us-east-1", "2.0"],
        ])
    print(f"Wrote {edp_path}")

    # ── Spot Price History ────────────────────────────────────────────────
    spot_path = os.path.join(out_dir, "spot_price_history.csv")
    with open(spot_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region", "instance_type", "availability_zone", "timestamp", "spot_price_usd"])
        spot_configs = [
            ("us-east-1", "m5.large",   "us-east-1a", 0.0960, 0.31),
            ("us-east-1", "m5.large",   "us-east-1b", 0.0960, 0.30),
            ("us-east-1", "m5.xlarge",  "us-east-1a", 0.1920, 0.32),
            ("us-east-1", "c5.xlarge",  "us-east-1a", 0.1700, 0.33),
            ("us-east-1", "r5.2xlarge", "us-east-1a", 0.5040, 0.35),
            ("us-west-2", "m5.large",   "us-west-2a", 0.1040, 0.30),
            ("us-west-2", "m5.large",   "us-west-2b", 0.1040, 0.29),
            ("us-west-2", "c5.xlarge",  "us-west-2a", 0.1810, 0.31),
            ("eu-west-1", "m5.large",   "eu-west-1a", 0.1070, 0.33),
            ("eu-west-1", "r5.large",   "eu-west-1a", 0.1450, 0.34),
        ]
        # Write 744 hours (Jan 2025) for each config — this creates 7440 rows
        for region, itype, az, od, spot_frac in spot_configs:
            base_spot = round(od * spot_frac, 6)
            for h in range(744):
                dt = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h)
                # Minor variation: every 6 hours add a fractional shift
                period = h // 6
                # Use period modulo arithmetic for deterministic "variation"
                variation = (period % 7) * 0.001
                # Occasional spike: every 168 hours (weekly)
                if h % 168 == 0:
                    spot = round(od * 0.70, 6)  # spike to 70% of OD
                else:
                    spot = round(base_spot + variation, 6)
                w.writerow([region, itype, az, dt.strftime("%Y-%m-%dT%H:%M:%SZ"), spot])
    print(f"Wrote {spot_path}")

    # ── Instance Pricing ─────────────────────────────────────────────────
    pricing_path = os.path.join(out_dir, "instance_pricing.csv")
    with open(pricing_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region", "instance_type", "od_hourly",
                    "convertible_1yr_hourly", "convertible_3yr_hourly",
                    "standard_1yr_hourly", "standard_3yr_hourly"])
        w.writerows([
            ["us-east-1", "m5.large",   "0.0960", "0.0680", "0.0520", "0.0624", "0.0480"],
            ["us-east-1", "m5.xlarge",  "0.1920", "0.1360", "0.1040", "0.1248", "0.0960"],
            ["us-east-1", "m5.2xlarge", "0.3840", "0.2720", "0.2080", "0.2496", "0.1920"],
            ["us-east-1", "c5.xlarge",  "0.1700", "0.1190", "0.0910", "0.1105", "0.0850"],
            ["us-east-1", "c5.2xlarge", "0.3400", "0.2380", "0.1820", "0.2210", "0.1700"],
            ["us-east-1", "r5.large",   "0.1260", "0.0882", "0.0672", "0.0819", "0.0630"],
            ["us-east-1", "r5.2xlarge", "0.5040", "0.3528", "0.2688", "0.3276", "0.2520"],
            ["us-east-1", "t3.medium",  "0.0416", "0.0291", "0.0222", "0.0270", "0.0208"],
            ["us-west-2", "m5.large",   "0.1040", "0.0728", "0.0556", "0.0676", "0.0520"],
            ["us-west-2", "m5.xlarge",  "0.2080", "0.1456", "0.1112", "0.1352", "0.1040"],
            ["us-west-2", "m5.2xlarge", "0.4160", "0.2912", "0.2224", "0.2704", "0.2080"],
            ["us-west-2", "c5.xlarge",  "0.1810", "0.1267", "0.0968", "0.1177", "0.0905"],
            ["us-west-2", "c5.2xlarge", "0.3620", "0.2534", "0.1936", "0.2353", "0.1810"],
            ["us-west-2", "r5.large",   "0.1340", "0.0938", "0.0716", "0.0871", "0.0670"],
            ["us-west-2", "r5.2xlarge", "0.5360", "0.3752", "0.2864", "0.3484", "0.2680"],
            ["eu-west-1", "m5.large",   "0.1070", "0.0749", "0.0572", "0.0696", "0.0535"],
            ["eu-west-1", "m5.xlarge",  "0.2140", "0.1498", "0.1144", "0.1391", "0.1070"],
            ["eu-west-1", "c5.xlarge",  "0.1940", "0.1358", "0.1037", "0.1261", "0.0970"],
            ["eu-west-1", "c5.2xlarge", "0.3880", "0.2716", "0.2074", "0.2522", "0.1940"],
            ["eu-west-1", "r5.large",   "0.1450", "0.1015", "0.0775", "0.0943", "0.0725"],
        ])
    print(f"Wrote {pricing_path}")

    # ── Manifest JSON ─────────────────────────────────────────────────────
    manifest = {
        "assemblyId": "cost-and-usage-report-2025-01",
        "account": "123456789012",
        "columns": HEADER,
        "charset": "UTF-8",
        "compression": "GZIP",
        "contentType": "text/csv",
        "reportId": "acme-cur",
        "reportName": "acme-cur",
        "billingPeriod": {
            "start": "20250101T000000.000Z",
            "end": "20250201T000000.000Z",
        },
        "bucket": "acme-cur-bucket",
        "reportKeys": ["acme-cur/20250101-20250201/acme-cur-1.csv.gz"],
        "additionalArtifactKeys": [],
    }
    manifest_path = os.path.join(out_dir, "cur_manifest_2025_01.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {manifest_path}")

    print("Done!")
    return size


if __name__ == "__main__":
    main()
