# PART 0 — Generate Fake CUR Data (1 MB handwritten CSV)

## Objective
Write realistic fake AWS CUR CSV data directly to disk. No random number generation —
every row must use deterministic, realistic values drawn from the AWS universe.
The output file must be ≥ 1 MB.

## Output Files

All files go in `/Users/mfeldman/Documents/python/aws_ecs_biller/tests/fixtures/`:

1. `cur_sample_2025_01.csv` — main CUR CSV, ≥ 1 MB
2. `edp_discounts.csv` — EDP discount rates per service/region
3. `spot_price_history.csv` — spot prices over time
4. `instance_pricing.csv` — OD/RI pricing by instance type and region

---

## Universe of Values to Use

### AWS Accounts
| account_id | account_name | is_payer |
|------------|-------------|---------|
| 123456789012 | acme-prod | Yes |
| 234567890123 | acme-dev | No |
| 345678901234 | acme-staging | No |

### Services + Usage Types
| service (product_code) | usage_type examples |
|------------------------|-------------------|
| AmazonEC2 | USE1-BoxUsage:m5.large, USE1-BoxUsage:m5.xlarge, USE1-BoxUsage:c5.xlarge, USE1-BoxUsage:r5.2xlarge, USW2-BoxUsage:m5.2xlarge, EUW1-BoxUsage:c5.2xlarge |
| AmazonRDS | USE1-InstanceUsage:db.r5.large, USE1-InstanceUsage:db.r5.xlarge |
| AmazonS3 | USE1-TimedStorage-ByteHrs, USE1-Requests-Tier1 |
| AmazonEKS | USE1-AmazonEKS-Hours:perCluster |
| AWSLambda | USE1-Lambda-GB-Second |
| AmazonCloudFront | USE1-DataTransfer-Out-Bytes |

### Regions
- us-east-1 (USE1)
- us-west-2 (USW2)
- eu-west-1 (EUW1)

### Instance Types + Normalization Factors
| instance_type | family | norm_factor |
|---------------|--------|-------------|
| m5.large | m5 | 4.0 |
| m5.xlarge | m5 | 8.0 |
| m5.2xlarge | m5 | 16.0 |
| c5.xlarge | c5 | 8.0 |
| c5.2xlarge | c5 | 16.0 |
| r5.large | r5 | 4.0 |
| r5.2xlarge | r5 | 16.0 |
| t3.medium | t3 | 2.0 |

### On-Demand Hourly Rates (USD)
| instance_type | us-east-1 | us-west-2 | eu-west-1 |
|--------------|-----------|-----------|-----------|
| m5.large | 0.0960 | 0.1040 | 0.1070 |
| m5.xlarge | 0.1920 | 0.2080 | 0.2140 |
| m5.2xlarge | 0.3840 | 0.4160 | 0.4280 |
| c5.xlarge | 0.1700 | 0.1810 | 0.1940 |
| c5.2xlarge | 0.3400 | 0.3620 | 0.3880 |
| r5.large | 0.1260 | 0.1340 | 0.1450 |
| r5.2xlarge | 0.5040 | 0.5360 | 0.5800 |
| t3.medium | 0.0416 | 0.0464 | 0.0520 |

### Reserved Instance ARNs (active in Jan 2025)
| arn | instance_type | region | offering_class | count | start | end |
|-----|--------------|--------|---------------|-------|-------|-----|
| arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-0a1b2c3d4e5f6789a | m5.large | us-east-1 | standard | 10 | 2024-01-01 | 2027-01-01 |
| arn:aws:ec2:us-east-1:123456789012:reserved-instances/ri-0b2c3d4e5f6789ab | c5.xlarge | us-east-1 | convertible | 5 | 2024-06-01 | 2027-06-01 |
| arn:aws:ec2:us-west-2:123456789012:reserved-instances/ri-0c3d4e5f6789abc | m5.2xlarge | us-west-2 | convertible | 3 | 2023-12-01 | 2026-12-01 |
| arn:aws:ec2:eu-west-1:123456789012:reserved-instances/ri-0d4e5f6789abcd | r5.large | eu-west-1 | standard | 4 | 2024-03-01 | 2027-03-01 |

### Savings Plan ARNs
| arn | type | commitment_hourly | region | start | end |
|-----|------|-----------------|--------|-------|-----|
| arn:aws:savingsplans::123456789012:savingsplan/sp-abc123def456 | ComputeSavingsPlan | 2.50 | us-east-1 | 2024-07-01 | 2025-07-01 |

### Resource Tags (rotate through these)
```
{"user:team": "backend", "user:env": "prod", "user:app": "api-server"}
{"user:team": "frontend", "user:env": "prod", "user:app": "web-app"}
{"user:team": "data", "user:env": "prod", "user:app": "spark-cluster"}
{"user:team": "backend", "user:env": "staging", "user:app": "api-server"}
{"user:team": "platform", "user:env": "prod", "user:app": "k8s-system"}
```

---

## CSV Structure

Write the header row first, then data rows.
Use the exact column names from the CUR schema:

```
identity_line_item_id,identity_time_interval,bill_bill_type,bill_billing_entity,
bill_billing_period_start_date,bill_billing_period_end_date,bill_invoice_id,
bill_payer_account_id,bill_payer_account_name,line_item_usage_account_id,
line_item_usage_account_name,line_item_usage_start_date,line_item_usage_end_date,
line_item_line_item_type,line_item_product_code,line_item_usage_type,
line_item_operation,line_item_resource_id,line_item_availability_zone,
line_item_usage_amount,line_item_unblended_cost,line_item_blended_cost,
line_item_net_unblended_cost,line_item_normalization_factor,
line_item_normalized_usage_amount,line_item_line_item_description,
line_item_currency_code,pricing_term,pricing_unit,pricing_public_on_demand_cost,
pricing_public_on_demand_rate,pricing_offering_class,pricing_purchase_option,
pricing_lease_contract_length,product_region_code,product_instance_type,
product_instance_family,product_product_family,product_servicecode,product_sku,
reservation_reservation_a_r_n,reservation_effective_cost,
reservation_amortized_upfront_cost_for_usage,reservation_recurring_fee_for_usage,
reservation_unused_quantity,reservation_unused_recurring_fee,
reservation_normalized_units_per_reservation,reservation_number_of_reservations,
reservation_start_time,reservation_end_time,reservation_subscription_id,
savings_plan_savings_plan_a_r_n,savings_plan_savings_plan_effective_cost,
savings_plan_offering_type,savings_plan_payment_option,savings_plan_purchase_term,
savings_plan_region,savings_plan_used_commitment,savings_plan_total_commitment_to_date,
split_line_item_split_cost,split_line_item_actual_usage,
split_line_item_split_usage_ratio,split_line_item_parent_resource_id,
resource_tags,cost_category,discount_total_discount
```

---

## Data Patterns to Encode

Build rows for January 2025 (2025-01-01 through 2025-01-31), hourly intervals.
To hit 1 MB, write rows for every hour across multiple resources.

### Pattern A — On-Demand EC2 (line_item_type = "Usage", pricing_term = "OnDemand")
- Account 234567890123 (dev) runs 3× m5.large in us-east-1 around the clock
- Account 345678901234 (staging) runs 2× c5.xlarge in us-west-2 9am–6pm weekdays only (lower usage 0.0–0.1 units overnight)
- Account 123456789012 (prod) runs 8× m5.xlarge in us-east-1 on-demand (overflow above RI capacity)

### Pattern B — RI-Covered EC2 (line_item_type = "DiscountedUsage")
- 10× m5.large in us-east-1 under ri-0a1b2c3d... (RI covers them fully)
  - reservation_effective_cost = usage_amount × 0.0624 (35% discount vs OD 0.0960)
  - reservation_recurring_fee = 0.0624 per hour per instance
  - reservation_unused_quantity = 0 when fully utilized
- 5× c5.xlarge in us-east-1 under ri-0b2c3d... (convertible)
  - Only 3 of 5 are utilized Mon–Fri; 2 unused on weekends
  - reservation_unused_quantity = 2.0 on Sat/Sun hours
  - reservation_unused_recurring_fee = 2 × 0.0935 on those hours

### Pattern C — RI Fee rows (line_item_type = "RIFee")
- One RIFee row per hour per RI ARN (represents the purchased capacity cost)
  - account 123456789012, linked to the RI ARN
  - reservation_number_of_reservations = purchased count
  - reservation_normalized_units_per_reservation = norm_factor for instance type
  - line_item_unblended_cost = total hourly fee for all reserved instances

### Pattern D — Savings Plan (line_item_type = "SavingsPlanCoveredUsage")
- Some EC2 usage in us-east-1 account 123456789012 covered by Compute SP
  - savings_plan_savings_plan_a_r_n = sp-abc123def456
  - savings_plan_savings_plan_effective_cost = usage × sp_rate (e.g. 0.80 × OD rate)
  - savings_plan_used_commitment = hourly used portion

### Pattern E — RDS (line_item_type = "Usage")
- Account 123456789012: 2× db.r5.large in us-east-1 always on
- Account 234567890123: 1× db.r5.large in us-east-1 always on

### Pattern F — S3 (line_item_type = "Usage")
- Storage bytes charged daily (1 row per day, not hourly)
- Requests charged per hour

### Pattern G — Lambda + EKS
- Lambda: AWSLambda GB-seconds, vary by hour
- EKS cluster fee: $0.10/hour, always on

### ANOMALY: Week of 2025-01-13 (Mon) through 2025-01-17 (Fri)
- EC2 usage in us-east-1 for account 123456789012 is 3× normal (incident simulation)
- Add extra m5.xlarge rows with higher usage_amount (e.g. 16 instead of 5)
- This will be detected by the anomaly engine in Part 7

### COST SPLITTING TARGET: EKS cluster
- EKS cluster resource_id: i-0eks-cluster-prod-001
- Tag: {"user:app": "k8s-system", "user:team": "platform"}
- Multiple sub-pods represented by split_line_item_* columns
  - split_line_item_parent_resource_id = i-0eks-cluster-prod-001
  - Various child resource_ids with split ratios (0.4 backend, 0.35 frontend, 0.25 data)

---

## identity_line_item_id Format

Use deterministic IDs:
`li-{YYYYMMDD}-{HH}-{account}-{service_abbrev}-{resource_abbrev}-{seq:04d}`

Example: `li-20250101-00-123456789012-ec2-m5lg-0001`

---

## Supporting Fixture Files

### `edp_discounts.csv`
```csv
service,region,discount_pct
AmazonEC2,us-east-1,5.0
AmazonEC2,us-west-2,5.0
AmazonEC2,eu-west-1,4.0
AmazonRDS,us-east-1,3.0
AmazonRDS,us-west-2,3.0
AmazonS3,us-east-1,2.0
AmazonS3,us-west-2,2.0
AWSLambda,us-east-1,1.0
AmazonEKS,us-east-1,3.0
AmazonCloudFront,us-east-1,2.0
```

### `spot_price_history.csv`
```csv
region,instance_type,availability_zone,timestamp,spot_price_usd
us-east-1,m5.large,us-east-1a,2025-01-01T00:00:00Z,0.0312
us-east-1,m5.large,us-east-1b,2025-01-01T00:00:00Z,0.0298
... (write 200+ rows covering Jan 2025, with minor hourly variation)
```

Spot prices should be ~30-40% of OD rates, with occasional spikes to 70% of OD.

### `instance_pricing.csv`
```csv
region,instance_type,od_hourly,convertible_1yr_hourly,convertible_3yr_hourly,standard_1yr_hourly,standard_3yr_hourly
us-east-1,m5.large,0.0960,0.0680,0.0520,0.0624,0.0480
us-east-1,m5.xlarge,0.1920,0.1360,0.1040,0.1248,0.0960
us-east-1,m5.2xlarge,0.3840,0.2720,0.2080,0.2496,0.1920
us-east-1,c5.xlarge,0.1700,0.1190,0.0910,0.1105,0.0850
us-east-1,c5.2xlarge,0.3400,0.2380,0.1820,0.2210,0.1700
us-east-1,r5.large,0.1260,0.0882,0.0672,0.0819,0.0630
us-east-1,r5.2xlarge,0.5040,0.3528,0.2688,0.3276,0.2520
us-east-1,t3.medium,0.0416,0.0291,0.0222,0.0270,0.0208
us-west-2,m5.large,0.1040,0.0728,0.0556,0.0676,0.0520
us-west-2,m5.xlarge,0.2080,0.1456,0.1112,0.1352,0.1040
us-west-2,m5.2xlarge,0.4160,0.2912,0.2224,0.2704,0.2080
us-west-2,c5.xlarge,0.1810,0.1267,0.0968,0.1177,0.0905
us-west-2,c5.2xlarge,0.3620,0.2534,0.1936,0.2353,0.1810
us-west-2,r5.large,0.1340,0.0938,0.0716,0.0871,0.0670
us-west-2,r5.2xlarge,0.5360,0.3752,0.2864,0.3484,0.2680
eu-west-1,m5.large,0.1070,0.0749,0.0572,0.0696,0.0535
eu-west-1,m5.xlarge,0.2140,0.1498,0.1144,0.1391,0.1070
eu-west-1,c5.xlarge,0.1940,0.1358,0.1037,0.1261,0.0970
eu-west-1,c5.2xlarge,0.3880,0.2716,0.2074,0.2522,0.1940
eu-west-1,r5.large,0.1450,0.1015,0.0775,0.0943,0.0725
```

---

## Implementation Instructions

Write the files **directly** — do not use Python's `random` module or numpy random functions.
Instead, construct rows by iterating over the universe of values above using Python loops
with deterministic arithmetic (multiply usage by hour patterns, scale by weekday/weekend).

Use this pattern for usage scaling (do not use random):
```python
# Weekday daytime (hour 8-18, Mon-Fri): scale = 1.0
# Weekday night (hour 19-7, Mon-Fri):   scale = 0.7
# Weekend:                               scale = 0.4
# Anomaly week (Jan 13-17, all hours):  scale = 3.0 (for EC2 in us-east-1, acct 123456789012)
```

The CSV should be written to:
`/Users/mfeldman/Documents/python/aws_ecs_biller/tests/fixtures/cur_sample_2025_01.csv`

After writing, verify:
```bash
wc -c tests/fixtures/cur_sample_2025_01.csv   # should be >= 1000000 bytes
wc -l tests/fixtures/cur_sample_2025_01.csv   # show row count
head -2 tests/fixtures/cur_sample_2025_01.csv # verify header + first row
```

Also write a manifest JSON:
`/Users/mfeldman/Documents/python/aws_ecs_biller/tests/fixtures/cur_manifest_2025_01.json`

```json
{
  "assemblyId": "cost-and-usage-report-2025-01",
  "account": "123456789012",
  "columns": [...all column names...],
  "charset": "UTF-8",
  "compression": "GZIP",
  "contentType": "text/csv",
  "reportId": "acme-cur",
  "reportName": "acme-cur",
  "billingPeriod": {"start": "20250101T000000.000Z", "end": "20250201T000000.000Z"},
  "bucket": "acme-cur-bucket",
  "reportKeys": ["acme-cur/20250101-20250201/acme-cur-1.csv.gz"],
  "additionalArtifactKeys": []
}
```

---

## NEXT

After completing Part 0, run:
**`/Users/mfeldman/.claude/plans/PART_1_scaffold.md`**
