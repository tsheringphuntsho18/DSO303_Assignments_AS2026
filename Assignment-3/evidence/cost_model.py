#!/usr/bin/env python3
"""
EduExam cost model - Assignment 3.

Computes monthly cost per service for a "normal" month and an "exam" month,
in ap-southeast-1 (Singapore) and ap-south-1 (Mumbai), from:
  (a) a usage-assumptions block (traffic/data volumes derived from the
      8,000-student / 400-staff population and the brief's load profiles)
  (b) a pricing table sourced from AWS's public pricing pages (checked
      2026-11-20) plus documented regional differentials where the static
      pages did not expose a Singapore/Mumbai-specific figure. See
      PRICING_SOURCES.md for the per-line provenance.

This is the worked estimate behind docs/cost-report.md. It is NOT a
substitute for the official AWS Pricing Calculator export required as
evidence - see PRICING_CALCULATOR_WORKSHEET.md for the exact line items
to re-enter at https://calculator.aws/.

Run: python3 cost_model.py   (writes cost_model_output.json alongside it)
"""
import json
import os

STUDENTS = 8000
STAFF = 400
USERS = STUDENTS + STAFF

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cost_model_output.json")

# ---------------------------------------------------------------------------
# Pricing table: service -> region -> {metric: unit_price_usd}
# ---------------------------------------------------------------------------
PRICING = {
    "ap-southeast-1": {  # Singapore
        "lambda_per_1m_req": 0.20,
        "lambda_per_gbs": 0.0000208854,
        "apigw_per_1m_req": 1.00,
        "aurora_per_acu_hr": 0.16,
        "aurora_storage_per_gb_mo": 0.12,
        "aurora_io_per_1m": 0.24,
        "rds_proxy_per_acu_hr": 0.020,
        "s3_standard_per_gb_mo": 0.025,
        "s3_ia_per_gb_mo": 0.0138,
        "s3_deep_archive_per_gb_mo": 0.00114,
        "s3_put_per_1k": 0.0055,
        "s3_get_per_1k": 0.00044,
        "nat_per_hr": 0.059,
        "nat_per_gb": 0.059,
        "cloudfront_dto_per_gb": 0.120,
        "cloudfront_https_per_10k": 0.0120,
        "cognito_per_mau": 0.015,
        "cognito_free_mau": 10000,
        "sqs_per_1m_req": 0.45,
        "ses_per_1k_email": 0.10,
        "kms_per_key_mo": 1.00,
        "kms_per_10k_req": 0.03,
        "cw_logs_ingest_per_gb": 0.57,
        "cw_logs_storage_per_gb_mo": 0.033,
        "cw_alarm_per_mo": 0.10,
        "secrets_per_secret_mo": 0.40,
        "secrets_per_10k_api": 0.05,
        "waf_acl_per_mo": 5.00,
        "waf_rule_per_mo": 1.00,
        "waf_per_1m_req": 0.60,
        "route53_zone_per_mo": 0.50,
        "route53_per_1m_queries": 0.40,
        "dto_internet_per_gb": 0.12,
    },
    "ap-south-1": {  # Mumbai
        "lambda_per_1m_req": 0.20,
        "lambda_per_gbs": 0.0000166667,
        "apigw_per_1m_req": 1.00,
        "aurora_per_acu_hr": 0.131,
        "aurora_storage_per_gb_mo": 0.11,
        "aurora_io_per_1m": 0.22,
        "rds_proxy_per_acu_hr": 0.0165,
        "s3_standard_per_gb_mo": 0.023,
        "s3_ia_per_gb_mo": 0.0125,
        "s3_deep_archive_per_gb_mo": 0.00099,
        "s3_put_per_1k": 0.005,
        "s3_get_per_1k": 0.0004,
        "nat_per_hr": 0.059,
        "nat_per_gb": 0.059,
        "cloudfront_dto_per_gb": 0.120,
        "cloudfront_https_per_10k": 0.0120,
        "cognito_per_mau": 0.015,
        "cognito_free_mau": 10000,
        "sqs_per_1m_req": 0.45,
        "ses_per_1k_email": 0.10,
        "kms_per_key_mo": 1.00,
        "kms_per_10k_req": 0.03,
        "cw_logs_ingest_per_gb": 0.53,
        "cw_logs_storage_per_gb_mo": 0.0315,
        "cw_alarm_per_mo": 0.10,
        "secrets_per_secret_mo": 0.40,
        "secrets_per_10k_api": 0.05,
        "waf_acl_per_mo": 5.00,
        "waf_rule_per_mo": 1.00,
        "waf_per_1m_req": 0.60,
        "route53_zone_per_mo": 0.50,
        "route53_per_1m_queries": 0.40,
        "dto_internet_per_gb": 0.109,
    },
}

# ---------------------------------------------------------------------------
# Usage assumptions
# ---------------------------------------------------------------------------
USAGE = {
    "normal": {
        "api_requests": 500_000,
        "lambda_invocations": 550_000,
        "lambda_avg_gb": 0.25,         # 256 MB
        "lambda_avg_duration_s": 0.3,
        "aurora_writer_avg_acu": 1.0,
        "aurora_reader_avg_acu": 0.5,
        "aurora_storage_gb": 25,
        "aurora_io_millions": 1.0,
        "s3_new_gb": 29,
        "s3_put_k": 3,
        "s3_get_k": 6,
        "s3_standard_resident_gb": 90,   # steady-state blended Standard-tier footprint
        "s3_ia_resident_gb": 140,        # blended Standard-IA footprint (90d-365d band)
        "s3_deep_resident_gb": 900,      # blended Deep Archive footprint (>365d, 5yr retention)
        "nat_gb": 20,
        "nat_hours": 2 * 730,            # 2 NAT GWs, full month
        "cloudfront_gb": 80,
        "cloudfront_https_10k": 50,
        "cw_logs_gb": 3,
        "cw_logs_storage_gb": 40,        # cumulative retained (14-day retention, 8 log groups)
        "cw_alarms": 6,
        "kms_req_10k": 15,
        "secrets_count": 1,
        "secrets_api_10k": 0.5,
        "sqs_req_1m": 0.025,
        "ses_emails_k": 22,
        "waf_req_1m": 0.5,
        "waf_rules": 3,
        "route53_queries_1m": 0.2,
        "dto_internet_gb": 10,           # non-CloudFront egress (presigned S3 PUT/GET acks etc.)
    },
    "exam": {
        "api_requests": 2_700_000,
        "lambda_invocations": 2_800_000,
        "lambda_avg_gb": 0.25,
        "lambda_avg_duration_s": 0.3,
        "aurora_writer_avg_acu": 2.2,
        "aurora_reader_avg_acu": 1.1,
        "aurora_storage_gb": 27,
        "aurora_io_millions": 4.5,
        "s3_new_gb": 32,
        "s3_put_k": 2.2,
        "s3_get_k": 60,
        "s3_standard_resident_gb": 95,
        "s3_ia_resident_gb": 145,
        "s3_deep_resident_gb": 900,
        "nat_gb": 60,
        "nat_hours": 2 * 730,
        "cloudfront_gb": 400,
        "cloudfront_https_10k": 270,
        "cw_logs_gb": 14,
        "cw_logs_storage_gb": 45,
        "cw_alarms": 6,
        "kms_req_10k": 70,
        "secrets_count": 1,
        "secrets_api_10k": 0.5,
        "sqs_req_1m": 0.12,
        "ses_emails_k": 45,
        "waf_req_1m": 2.7,
        "waf_rules": 3,
        "route53_queries_1m": 0.9,
        "dto_internet_gb": 25,
    },
}


def compute(region, profile):
    p = PRICING[region]
    u = USAGE[profile]
    out = {}

    out["API Gateway (HTTP API)"] = (u["api_requests"] / 1_000_000) * p["apigw_per_1m_req"]

    gbs = u["lambda_invocations"] * u["lambda_avg_gb"] * u["lambda_avg_duration_s"]
    out["Lambda"] = (u["lambda_invocations"] / 1_000_000) * p["lambda_per_1m_req"] + gbs * p["lambda_per_gbs"]

    aurora_compute = (u["aurora_writer_avg_acu"] + u["aurora_reader_avg_acu"]) * 730 * p["aurora_per_acu_hr"]
    aurora_storage = u["aurora_storage_gb"] * p["aurora_storage_per_gb_mo"]
    aurora_io = u["aurora_io_millions"] * p["aurora_io_per_1m"]
    out["Aurora Serverless v2 (compute)"] = aurora_compute
    out["Aurora Serverless v2 (storage + I/O)"] = aurora_storage + aurora_io

    rds_proxy_acu_hrs = (u["aurora_writer_avg_acu"] + u["aurora_reader_avg_acu"]) * 730
    out["RDS Proxy"] = rds_proxy_acu_hrs * p["rds_proxy_per_acu_hr"]

    s3_storage = (
        u["s3_standard_resident_gb"] * p["s3_standard_per_gb_mo"]
        + u["s3_ia_resident_gb"] * p["s3_ia_per_gb_mo"]
        + u["s3_deep_resident_gb"] * p["s3_deep_archive_per_gb_mo"]
    )
    s3_requests = u["s3_put_k"] * p["s3_put_per_1k"] + u["s3_get_k"] * p["s3_get_per_1k"]
    out["S3 (submissions + frontend, storage)"] = s3_storage
    out["S3 (requests)"] = s3_requests

    out["NAT Gateway (hourly + processing) [hidden]"] = (
        u["nat_hours"] * p["nat_per_hr"] + u["nat_gb"] * p["nat_per_gb"]
    )

    out["CloudFront"] = u["cloudfront_gb"] * p["cloudfront_dto_per_gb"] + (
        u["cloudfront_https_10k"] * p["cloudfront_https_per_10k"]
    )

    billable_mau = max(0, USERS - p["cognito_free_mau"])
    out["Cognito"] = billable_mau * p["cognito_per_mau"]

    out["SQS"] = u["sqs_req_1m"] * p["sqs_per_1m_req"]
    out["SES"] = u["ses_emails_k"] * p["ses_per_1k_email"]

    out["KMS [hidden]"] = p["kms_per_key_mo"] + u["kms_req_10k"] * p["kms_per_10k_req"]

    out["CloudWatch Logs [hidden]"] = (
        u["cw_logs_gb"] * p["cw_logs_ingest_per_gb"]
        + u["cw_logs_storage_gb"] * p["cw_logs_storage_per_gb_mo"]
        + u["cw_alarms"] * p["cw_alarm_per_mo"]
    )

    out["Secrets Manager [hidden - backups/rotation]"] = (
        u["secrets_count"] * p["secrets_per_secret_mo"] + u["secrets_api_10k"] * p["secrets_per_10k_api"]
    )

    out["WAF"] = (
        p["waf_acl_per_mo"] + u["waf_rules"] * p["waf_rule_per_mo"] + u["waf_req_1m"] * p["waf_per_1m_req"]
    )

    out["Route 53"] = p["route53_zone_per_mo"] + u["route53_queries_1m"] * p["route53_per_1m_queries"]

    out["Data transfer OUT (non-CDN) [hidden]"] = u["dto_internet_gb"] * p["dto_internet_per_gb"]

    out["Aurora backups (35-day PITR, within 100% free allowance)"] = 0.0

    return out


# ---------------------------------------------------------------------------
# Optimizations - applied as deltas on top of the baseline compute() output.
# See architecture/CHANGE_LOG.md and docs/cost-report.md Section 6 for the
# narrative behind each of these.
# ---------------------------------------------------------------------------
def apply_optimizations(region, profile, baseline):
    p = PRICING[region]
    u = USAGE[profile]
    opt = dict(baseline)
    notes = []

    # Optimization A: NAT Gateway consolidation (1 in normal months, 2 in
    # exam months - uses the existing single_nat_gateway tfvar) + 4 more
    # VPC interface endpoints (SQS, Cognito IDP, KMS, SES) added alongside
    # the S3 gateway + Secrets Manager interface endpoints A2 already had.
    if profile == "normal":
        nat_hours, nat_gb = 1 * 730, 3
    else:
        nat_hours, nat_gb = 2 * 730, 8
    new_nat = nat_hours * p["nat_per_hr"] + nat_gb * p["nat_per_gb"]
    saved_a = opt["NAT Gateway (hourly + processing) [hidden]"] - new_nat
    opt["NAT Gateway (hourly + processing) [hidden]"] = new_nat
    notes.append(("A: NAT consolidation + VPC endpoints", saved_a))

    # Optimization B: autosave answer-writes move from Aurora to DynamoDB
    # on-demand, cutting average ACU need (and RDS Proxy, billed per the
    # same ACU-hours) since autosave dominates write volume, especially in
    # exam months.
    acu_factor = 1.25 / 1.5 if profile == "normal" else 2.0 / 3.3
    new_aurora_compute = opt["Aurora Serverless v2 (compute)"] * acu_factor
    new_rds_proxy = opt["RDS Proxy"] * acu_factor
    dynamo_writes_m = 0.1 if profile == "normal" else 2.16
    dynamo_cost = dynamo_writes_m * 1.50
    saved_b = (
        (opt["Aurora Serverless v2 (compute)"] - new_aurora_compute)
        + (opt["RDS Proxy"] - new_rds_proxy)
        - dynamo_cost
    )
    opt["Aurora Serverless v2 (compute)"] = new_aurora_compute
    opt["RDS Proxy"] = new_rds_proxy
    opt["DynamoDB (autosave answers, on-demand)"] = dynamo_cost
    notes.append(("B: autosave -> DynamoDB on-demand", saved_b))

    # Optimization C: CloudFront compression (Brotli/gzip) + longer
    # static-asset cache TTLs cut billable data-transfer-out ~30% blended.
    old_dto_cost = u["cloudfront_gb"] * p["cloudfront_dto_per_gb"]
    new_dto_cost = old_dto_cost * 0.70
    saved_c = old_dto_cost - new_dto_cost
    opt["CloudFront"] = new_dto_cost + u["cloudfront_https_10k"] * p["cloudfront_https_per_10k"]
    notes.append(("C: CloudFront compression + cache TTLs", saved_c))

    return opt, notes


def _print_table(title, normal, exam):
    services = sorted(set(normal) | set(exam))
    total_normal = total_exam = 0.0
    print(f"\n{title}")
    print(f"{'Service':<48}{'Normal $/mo':>12}{'Exam $/mo':>12}")
    for s in services:
        n, e = normal.get(s, 0.0), exam.get(s, 0.0)
        total_normal += n
        total_exam += e
        print(f"{s:<48}{n:>12.2f}{e:>12.2f}")
    print("-" * 72)
    print(f"{'TOTAL':<48}{total_normal:>12.2f}{total_exam:>12.2f}")
    return total_normal, total_exam


def main():
    results, optimized, opt_notes = {}, {}, {}
    for region in PRICING:
        results[region], optimized[region], opt_notes[region] = {}, {}, {}
        for profile in USAGE:
            base = compute(region, profile)
            results[region][profile] = base
            opt, notes = apply_optimizations(region, profile, base)
            optimized[region][profile] = opt
            opt_notes[region][profile] = notes

    for region in results:
        print(f"\n{'=' * 70}\nRegion: {region}\n{'=' * 70}")
        tn, te = _print_table("BASELINE", results[region]["normal"], results[region]["exam"])
        annual = tn * 10 + te * 2
        print(f"\nAnnual total: ${annual:,.2f}  |  Avg $/mo: ${annual / 12:,.2f}  |  "
              f"$/student/yr: ${annual / STUDENTS:,.2f}  |  "
              f"Budget: {'PASS' if annual / 12 <= 1000 else 'FAIL'}")

        otn, ote = _print_table("OPTIMIZED", optimized[region]["normal"], optimized[region]["exam"])
        oannual = otn * 10 + ote * 2
        print(f"\nOptimized annual total: ${oannual:,.2f}  |  Avg $/mo: ${oannual / 12:,.2f}  |  "
              f"$/student/yr: ${oannual / STUDENTS:,.2f}")
        print(f"Annual savings vs baseline: ${annual - oannual:,.2f} ({(annual - oannual) / annual * 100:.1f}%)")

        print("\nPer-optimization annual savings:")
        for label, _ in opt_notes[region]["normal"]:
            sn = dict(opt_notes[region]["normal"])[label]
            se = dict(opt_notes[region]["exam"])[label]
            print(f"  {label:<45} ${10 * sn + 2 * se:,.2f}/yr  (normal ${sn:,.2f}/mo, exam ${se:,.2f}/mo)")

    # Per-optimization annual savings, keyed by region -> label -> $/yr, so
    # downstream consumers (generate_charts.py) use these verified figures
    # instead of re-deriving them (and risking a sign error) from the
    # baseline/optimized totals.
    savings_annual = {}
    for region in opt_notes:
        savings_annual[region] = {}
        for label, _ in opt_notes[region]["normal"]:
            sn = dict(opt_notes[region]["normal"])[label]
            se = dict(opt_notes[region]["exam"])[label]
            savings_annual[region][label] = round(10 * sn + 2 * se, 2)

    with open(OUTPUT_PATH, "w") as f:
        json.dump({"baseline": results, "optimized": optimized, "savings_annual": savings_annual}, f, indent=2)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
