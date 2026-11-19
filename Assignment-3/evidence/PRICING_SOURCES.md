# Pricing sources and confidence

Date checked: **2026-11-20**. This is the provenance table for every unit price in `evidence/cost_model.py`'s `PRICING` dict, which feeds `docs/cost-report.md`.

**Why this exists instead of a pure AWS Pricing Calculator export:** the AWS Pricing Calculator (`calculator.aws`) is a JavaScript application; this assistant can fetch and read static pages but cannot drive an interactive web app. The AWS pricing *pages* were fetched directly, but most of them render their region-specific rate tables client-side and show only a US East (N. Virginia) example in static HTML — confirmed by direct fetch, not assumed. Where a page didn't expose a Singapore/Mumbai-specific number, the figure below is a documented regional differential instead, clearly marked. **Before submitting, replicate the configuration in `PRICING_CALCULATOR_WORKSHEET.md` at calculator.aws and treat that export as authoritative** — update this table and `cost_model.py` if the real numbers diverge meaningfully, and note the delta in `docs/cost-report.md`.

## Confirmed by direct fetch (2026-11-20)

| Service | Metric | Value | Region as shown | Source |
|---|---|---|---|---|
| Lambda | Requests | $0.20 / 1M | us-east-1 (example) | aws.amazon.com/lambda/pricing/ |
| Lambda | Compute | $0.0000166667 / GB-s | us-east-1 (example) | aws.amazon.com/lambda/pricing/ |
| Lambda | Free tier | 1M requests + 400,000 GB-s/mo | global | aws.amazon.com/lambda/pricing/ |
| Aurora PostgreSQL Serverless v2 | ACU-hour (Standard) | $0.12 | us-east-1 (example) | aws.amazon.com/rds/aurora/pricing/ |
| Aurora | Storage (Standard) | $0.10/GB-mo | us-east-1 (example) | aws.amazon.com/rds/aurora/pricing/ |
| Aurora | I/O (Standard) | $0.20/1M requests | us-east-1 (example) | aws.amazon.com/rds/aurora/pricing/ |
| Aurora | Backup storage | free up to 100% of cluster size | global | aws.amazon.com/rds/aurora/pricing/ |
| RDS Proxy | Billing basis | "priced per Aurora Capacity Unit (ACU) per hour consumed" for Aurora Serverless | — | aws.amazon.com/rds/proxy/pricing/ |
| CloudFront | Data transfer out, APAC group incl. Singapore (next 9TB tier) | $0.120/GB | labeled: "Hong Kong, Indonesia, Philippines, Singapore, South Korea, Taiwan, Thailand, Malaysia, Vietnam" | aws.amazon.com/cloudfront/pricing/pay-as-you-go/ |
| CloudFront | First 1TB/mo data transfer out | free | all groups | same |
| CloudFront | HTTPS requests, APAC group | $0.0120/10,000 | same APAC group | same |
| NAT Gateway | Hourly | $0.045/hr | US East (Ohio), example | aws.amazon.com/vpc/pricing/ |
| NAT Gateway | Data processing | $0.045/GB | US East (Ohio), example | aws.amazon.com/vpc/pricing/ |
| VPC Gateway Endpoint (S3) | Hourly + per-GB | $0 / $0 (free) | global | aws.amazon.com/vpc/pricing/ |
| Cognito | Essentials MAU (above free tier) | $0.015/MAU | unlabeled (appears global/flat) | aws.amazon.com/cognito/pricing/ |
| Cognito | Free tier | 10,000 MAU/mo | global | aws.amazon.com/cognito/pricing/ |
| SES | À la carte outbound email | $0.10/1,000 emails | unlabeled | aws.amazon.com/ses/pricing/ |
| KMS | Customer-managed key | $1.00/key/mo | unlabeled | aws.amazon.com/kms/pricing/ |
| KMS | Free tier | 20,000 requests/mo | "across all Regions" | aws.amazon.com/kms/pricing/ |
| Secrets Manager | Per secret | $0.40/mo | unlabeled | aws.amazon.com/secrets-manager/pricing/ |
| Secrets Manager | Per 10,000 API calls | $0.05 | unlabeled | aws.amazon.com/secrets-manager/pricing/ |
| WAF | Web ACL | $5.00/mo | unlabeled | aws.amazon.com/waf/pricing/ |
| WAF | Rule / managed rule group | $1.00/mo each | unlabeled | aws.amazon.com/waf/pricing/ |
| WAF | Requests | $0.60/1M | unlabeled | aws.amazon.com/waf/pricing/ |
| Route 53 | Hosted zone | $0.50/mo (first 25) | unlabeled | aws.amazon.com/route53/pricing/ |
| Route 53 | Standard queries | $0.40/1M (first 1B) | unlabeled | aws.amazon.com/route53/pricing/ |
| CloudTrail | First management-events trail | free | unlabeled | aws.amazon.com/cloudtrail/pricing/ |
| S3 | GET request (Standard) | $0.0004/1,000 | "US East (N. Virginia)", from an Object Lambda example | aws.amazon.com/s3/pricing/ |

## Not exposed in static HTML (JS-rendered tables) — modelled from documented regional differentials

AWS's published regional pricing pattern is that Singapore and Mumbai both sit above `us-east-1` on compute/storage metered services, with Singapore typically the higher of the two; request-based and flat-fee services (API Gateway HTTP API, Cognito, WAF, Route 53, Secrets Manager, KMS, SES) are commonly priced the same or very close across regions. The figures used reflect that pattern:

| Service | Metric | us-east-1 (confirmed) | ap-southeast-1 used | ap-south-1 used | Confidence |
|---|---|---|---|---|---|
| Lambda | Compute $/GB-s | 0.0000166667 | 0.0000208854 (+25%) | 0.0000166667 (same tier as us-east-1) | Medium |
| Aurora Serverless v2 | $/ACU-hr | 0.12 | 0.16 (+33%) | 0.131 (+9%) | Medium |
| Aurora | Storage $/GB-mo | 0.10 | 0.12 (+20%) | 0.11 (+10%) | Medium |
| Aurora | I/O $/1M | 0.20 | 0.24 (+20%) | 0.22 (+10%) | Medium |
| RDS Proxy | $/ACU-hr | not published | 0.020 | 0.0165 | **Low** — scaled off Aurora's differential, not independently confirmed |
| S3 Standard | $/GB-mo | 0.023 (well-known published rate, not refetched this session) | 0.025 (+9%) | 0.023 (same) | Medium |
| S3 Standard-IA | $/GB-mo | 0.0125 | 0.0138 (+10%) | 0.0125 (same) | Medium |
| S3 Deep Archive | $/GB-mo | 0.00099 | 0.00114 (+15%) | 0.00099 (same) | Medium |
| S3 PUT/1,000 | — | 0.005 | 0.0055 | 0.005 | Medium |
| NAT Gateway | $/hr, $/GB | 0.045 (Ohio example) | 0.059 (+31%) | 0.059 (+31%) | Medium — Singapore/Mumbai NAT commonly share a higher non-US tier |
| Data transfer out (non-CDN) | $/GB | ~0.09 (general internet egress, well-known) | 0.12 | 0.109 | Medium |
| SQS | $/1M requests | 0.40 (well-known published rate; not confirmed this session — page's rate table didn't render) | 0.45 | 0.45 | Low-Medium |
| CloudWatch Logs | Ingestion $/GB | 0.50 (page states "varies by Region"; verbatim table truncated in fetch) | 0.57 (+15%) | 0.53 (+6%) | Low — see note below |
| CloudWatch Logs | Storage $/GB-mo | 0.03 (model summary, not verbatim) | 0.033 | 0.0315 | Low |
| CloudWatch | Alarm $/mo | 0.10 (model summary, not verbatim) | 0.10 (assumed flat) | 0.10 (assumed flat) | Low-Medium |

**Lowest-confidence lines, flag for extra scrutiny when replicating in the real calculator:** RDS Proxy $/ACU-hr, CloudWatch Logs ingestion/storage/alarm pricing (the fetch of `aws.amazon.com/cloudwatch/pricing/` was truncated — only ~40K of 156K characters were read, and the cited figures came from a model summary of the unread remainder, not verbatim text), and SQS's per-million-request rate (the page's rate table didn't render in the static fetch at all). These three services are individually small cost lines (CloudWatch Logs ≤$10/mo, RDS Proxy ≤$48/mo, SQS ≤$0.05/mo) so even a 2x error in one of them would not change the feasibility verdict, but they're the ones most worth double-checking against the real calculator output.
