# AWS Pricing Calculator worksheet

This is the exact set of line items to enter at **[calculator.aws](https://calculator.aws/)** to produce the official calculator export this assignment requires as evidence (Task 3's "Costed estimate" deliverable, and the rubric's "AWS architecture... calculator links" item). The numbers match `evidence/cost_model.py`'s `USAGE` dict, so the calculator's output can be directly compared against `docs/cost-report.md`.

**Build two estimates** (calculator.aws lets you name and save multiple "Estimates" under one "Group"):
1. `EduExam-Singapore-Normal` — region **Asia Pacific (Singapore)**, normal-month load.
2. `EduExam-Singapore-Exam` — region **Asia Pacific (Singapore)**, exam-month load.

Then, for Task 2.4's region comparison, duplicate both as:
3. `EduExam-Mumbai-Normal` — same line items, region **Asia Pacific (Mumbai)**.
4. `EduExam-Mumbai-Exam` — same line items, region **Asia Pacific (Mumbai)**.

Use the **"My Estimates" → "Share"** function on each to generate the public read-only link required for `README.md`, and use **"Export" → "Download as CSV"** on each, saved into this `evidence/` folder (e.g. `calculator-export-singapore-normal.csv`).

For every service below, add it via **"Add service"** in the calculator and search by name. Figures shown are *normal month / exam month* — enter the matching one per estimate.

## Compute

**Lambda** (search "Lambda")
- Architecture: x86
- Number of requests: **550,000** / **2,800,000** per month
- Amount of memory allocated: 256 MB
- Average duration of each request: 300 ms
- Amount of ephemeral storage allocated: 512 MB (default)

**Amazon API Gateway** (search "API Gateway") → choose **HTTP API**, not REST API
- Number of requests: **500,000** / **2,700,000** per month
- Average message size: leave default (not applicable to HTTP API's per-request pricing)

## Database

**Amazon Aurora** (search "Aurora") → PostgreSQL-compatible, Serverless v2
- Number of Aurora Serverless v2 instances: 2 (1 writer + 1 reader)
- Average Aurora Capacity Units (ACU): **1.5** / **3.3** (combined writer+reader average — if the calculator asks per-instance, use writer **1.0/2.2** and reader **0.5/1.1**)
- Storage amount: **25 GB** / **27 GB**
- I/O requests: **1,000,000** / **4,500,000** per month
- Backup storage: 0 GB additional (within the free 100%-of-cluster-size allowance — note this explicitly in the estimate's description field)

**Amazon RDS Proxy** (search "RDS Proxy" — if not listed as a standalone add-on in your calculator view, note this gap in the estimate's description and rely on `docs/cost-report.md`'s modelled RDS Proxy line instead)
- Associate with the Aurora cluster above; ACU-hours should auto-match Aurora's

**Amazon DynamoDB** (search "DynamoDB") — **exam-answers table, new in this assignment**
- Capacity mode: On-Demand
- Average item size: 1 KB
- Monthly writes: **100,000** / **2,160,000**
- Monthly reads: 50,000 / 500,000 (eventually-consistent, for `automark` reading answers at submit time)
- Storage: 5 GB (small — answer rows are tiny and expire via TTL after marking)

## Storage

**Amazon S3** (search "S3") — add once for `eduexam-submissions`, once for `eduexam-frontend`
- Region: Asia Pacific (Singapore)
- S3 Standard storage: **90 GB** / **95 GB** (blended resident footprint, 0-90 day band)
- S3 Standard-IA storage: **140 GB** / **145 GB** (90-365 day band)
- S3 Glacier Deep Archive storage: **900 GB** (both profiles — 5-year cumulative cold tier, grows slowly month to month)
- PUT/COPY/POST/LIST requests: **3,000** / **2,200** per month
- GET/SELECT requests: **6,000** / **60,000** per month
- Data retrieval: 0 GB (Deep Archive objects are not expected to be retrieved routinely)
- Lifecycle transitions: Standard → Standard-IA at 90 days, Standard-IA → Glacier Deep Archive at 365 days, expire at 1,825 days (enter as the bucket's lifecycle configuration if the calculator offers that field; otherwise it's reflected in the blended storage-tier GB figures above)

## Networking

**Amazon VPC — NAT Gateway** (search "NAT Gateway", usually under "Amazon VPC")
- Number of NAT Gateways: **1** (normal month) / **2** (exam month)
- NAT Gateway hours: 730 per gateway (full month)
- Data processed: **3 GB** / **8 GB** (post-optimization — see note below)
  - *To also price the baseline (pre-optimization) architecture, run this line again with 2 NAT Gateways and 20 GB / 60 GB data processed instead, for both profiles, and save as separate `-baseline` estimates.*

**Amazon VPC — Interface/Gateway Endpoints**: S3 Gateway Endpoint is free (don't add a line). For the 5 interface endpoints (Secrets Manager, SQS, Cognito IDP, KMS, SES), search "PrivateLink" / "VPC Endpoint" and add 5 instances at the default hourly rate with minimal data processed (~1 GB/mo each) — their combined cost is small (a few dollars/month) and already folded into `docs/cost-report.md`'s totals via the NAT-processing reduction rather than broken out as a separate line; add them explicitly in the calculator for completeness.

**Amazon CloudFront** (search "CloudFront")
- Price class: **Use Edge Locations in North America, Europe, Asia, Middle East, and Africa** (Price Class 200 — matches `architecture/CHANGE_LOG.md` change #2)
- Data transfer out to internet: **80 GB** / **400 GB** per month
- Number of HTTPS requests: **500,000** / **2,700,000** per month

**Data transfer out (non-CDN, general internet egress)**: usually appears automatically as part of each service's own data-transfer section (Lambda/API Gateway) rather than a standalone line — enter **10 GB** / **25 GB** wherever the calculator asks for "data transfer out to internet" outside of CloudFront/S3.

## Auth, messaging, security, ops

**Amazon Cognito** (search "Cognito") → User Pools
- Monthly active users: **8,400** (both profiles — stays inside the 10,000 free-tier MAU ceiling, so this should price at $0)

**Amazon SQS** (search "SQS")
- Number of requests: **25,000** / **120,000** per month (marking-queue + email-queue combined)

**Amazon SES** (search "SES")
- Number of outgoing messages: **22,000** / **45,000** per month
- Average message size: 10 KB

**AWS KMS** (search "KMS")
- Number of customer-managed keys: 1
- Number of requests: **150,000** / **700,000** per month

**Amazon CloudWatch** (search "CloudWatch")
- Number of custom metrics: ~15 (alarm-backing metrics)
- Number of alarms: **6** (standard resolution)
- GB of log data ingested: **3 GB** / **14 GB** per month
- GB of log data archived (storage): **40 GB** / **45 GB** (cumulative, 14-day retention × 8 log groups)

**AWS Secrets Manager** (search "Secrets Manager")
- Number of secrets: 1
- Number of API calls: **5,000** per month (both profiles)

**AWS WAF** (search "WAF")
- Number of Web ACLs: 1
- Number of rules: 3 (2 AWS Managed Rule Groups + 1 custom rate-based rule)
- Number of requests: **500,000** / **2,700,000** per month

**Amazon Route 53** (search "Route 53")
- Number of hosted zones: 1
- Number of standard queries: **200,000** / **900,000** per month

**AWS CloudTrail** (search "CloudTrail") — one management-events trail, free tier; no data events configured, so this should price at $0.


