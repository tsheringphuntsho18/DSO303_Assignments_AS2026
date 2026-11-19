# Load Test Plan — exam-start burst (3,000 students / 5 minutes)

## Important: two tracks, pick one honestly

The rubric's full marks for this item require a bottleneck **proven with real CloudWatch metrics**, fixed, and **re-tested**. The brief's own budget-friendly instinct (and this assignment's chosen test approach for the failure scenarios, § `infra/failure-tests.md`) is to avoid standing up a real paid AWS deployment. Those two things are in genuine tension — the Cloud Architecture Lab simulator used for the failure tests does not emit real CloudWatch metrics, so it cannot by itself produce "proven with CloudWatch" evidence. Be upfront about which track you actually ran:

- **Track 1 (recommended, full marks): a short-lived real deployment.** Assignment 2's `infra/` is already region-parameterised — deploying it to `ap-southeast-1` with this assignment's optimizations (§ `architecture/CHANGE_LOG.md`) for the ~30–60 minutes it takes to run the load test and capture CloudWatch screenshots costs a small fraction of a dollar at this traffic level (Lambda/API Gateway/Aurora Serverless v2 min-capacity for under an hour), then `terraform destroy` tears it down. This re-uses Assignment 2's own `scripts/simulate.py az-load-test` unmodified — the autosave backend change (Aurora → DynamoDB) doesn't change the HTTP contract the script calls.
- **Track 2 (fallback, partial marks): reasoned analysis only.** If you don't deploy, say so explicitly next to whatever you submit, and rely on the capacity reasoning in `infra/failure-tests.md` scenario 3 plus this document's bottleneck analysis — this is an **asserted**, not **proven**, bottleneck per the rubric's own partial-credit language, and should be labelled that way rather than presented as measured.

This document gives the exact commands/metrics for Track 1, and the reasoning for Track 2, for all three bottlenecks below. **This assistant has not run Track 1** — it requires your AWS credentials and a real `terraform apply`, which is a cost-incurring, account-affecting action that needs your explicit go-ahead to run, separate from writing this plan.

## Bottleneck 1 (to prove): RDS Proxy / Aurora connection pressure on `open-exam` + `submit-exam`

**Hypothesis:** at the 3,000-in-5-minute peak, the `open-exam` Lambda (every student calls this once, in a tight window, each opening an Aurora connection via RDS Proxy to create an "attempt" row) drives RDS Proxy's pool utilization high enough to queue connections, raising p99 latency on exam start specifically — the single worst moment for a student to experience a slow page.

**How to run it (Track 1):**
```bash
cd Assignment-2/infra
terraform apply -var="aws_region=ap-southeast-1" -var="availability_zones=[\"ap-southeast-1a\",\"ap-southeast-1b\"]"
# load schema, deploy frontend per Assignment-2/README.md "Deploy to AWS" section

cd ../scripts
pip install -r requirements.txt
python3 simulate.py az-load-test \
    --api-url "$(terraform -chdir=../infra output -raw api_invoke_url)/api" \
    --exam-id exam-101 --concurrency 100 --requests 3000
```
`--concurrency 100 --requests 3000` approximates 3,000 students arriving within the 5-minute window (the brief's actual peak); raise `--concurrency` toward 300–500 for a sharper approximation of "all at once" if the test environment's client machine can sustain it.

**CloudWatch to capture (before the fix):**
- RDS Proxy dashboard → `DatabaseConnectionsCurrentlyInUse` / `ClientConnections` — look for the value approaching `max_connections_percent` (90%, per `infra/database.tf`) of Aurora's connection ceiling at the current ACU level.
- API Gateway → `Latency` (p99) and `5xxError` count on `/api/exams/{examId}/start`, during the test window.
- Aurora → `ServerlessDatabaseCapacity` (ACU) climbing toward `aurora_max_capacity` (4).
- Lambda (`open-exam`) → `Duration` (p99) and `Throttles`.

**Expected finding:** p99 latency on `open-exam` rises sharply in roughly the last third of the burst, correlated with RDS Proxy connection pool utilization crossing ~80-90%, not with Lambda throttling (Lambda itself scales fine) or NAT (not on this path).

**Fix:** two independent levers, both config-only:
1. Raise `open-exam`'s Lambda reserved concurrency (currently shared/default) so it isn't starved relative to other functions during the burst — a `compute.tf` Terraform value, not a code change.
2. Tune RDS Proxy's `max_connections_percent` / `max_idle_connections_percent` (`infra/database.tf`) — raising the ceiling slightly, or lowering idle-connection retention so the pool recycles faster under burst load.

**Re-test:** re-run the identical `az-load-test` command after applying the fix; compare the same four CloudWatch metrics before/after. Expect p99 `open-exam` latency to flatten and RDS Proxy utilization to peak lower for the same input load. Record both runs' screenshots in `evidence/` as `load-test-before.png` / `load-test-after.png` (or equivalent CloudWatch Logs Insights query exports).

## Bottleneck 2 (reasoned): Lambda reserved-concurrency ceiling at the exact peak instant

**Reasoning (not run):** `compute.tf` sets a flat `lambda_memory_mb`/timeout per function but reserved concurrency isn't explicitly pinned per function in Assignment 2's Terraform — it falls back to the account's shared unreserved pool. If several other functions (autosave's old path, before it moved to DynamoDB; `automark`; `notify-tutor`) are mid-burst at the same moment `open-exam` needs to scale, they compete for the same shared concurrency ceiling. At 3,000 near-simultaneous `open-exam` invocations this is unlikely to actually throttle (Lambda's default regional concurrency limit is 1,000 and can be raised via support ticket well beyond the few thousand this platform needs), but it's the kind of ceiling that fails silently (a 429/"TooManyRequestsException" rather than a slow response) if account limits were ever left at new-account defaults.

**Fix (reasoned):** set explicit reserved concurrency per function in `compute.tf`, sized to each function's share of the 3,000-in-5-min peak, and request an account-level concurrency limit increase ahead of the first real exam week so the shared pool has headroom. This is a one-time Terraform + AWS Support request, not an architecture change.

## Bottleneck 3 (reasoned): CDN cache-miss stampede at the exact exam-start second

**Reasoning (not run):** CloudFront caches the SPA's static assets, but if an exam's specific question-set JSON or a freshly-deployed frontend build hasn't been fetched yet when the exam opens, the first wave of the 3,000 students all miss cache simultaneously and hit the S3 origin (or, for the proxied `/api/*` path, API Gateway directly — which is never cached by design) within the same few seconds. CloudFront absorbs this reasonably well (origin fetch coalescing means concurrent cache misses for the *same* object collapse into one origin request), but a cold deploy right before a scheduled exam start is the one scenario where this protection is weakest.

**Fix (reasoned):** a pre-warm step in the deploy pipeline — after `aws s3 sync` + `cloudfront create-invalidation` (already in `.github/workflows/deploy.yml`), issue one request per static asset path before the exam window opens, so the cache is warm before the 3,000 students arrive. This is an operational runbook addition, not an architecture change, and costs nothing beyond a handful of CloudFront requests.

## Summary for the report

| Bottleneck | Status | Fixed? | Re-tested? |
|---|---|---|---|
| 1. RDS Proxy / Aurora connection pressure on exam-start | **Proven** (Track 1) or **asserted** (Track 2 — label accordingly) | Yes — reserved concurrency + proxy pool tuning | Yes, if Track 1 was run |
| 2. Lambda shared-pool concurrency ceiling | Reasoned | Fix proposed (explicit reserved concurrency + limit increase) | Not run |
| 3. CDN cache-miss stampede at exam open | Reasoned | Fix proposed (pre-warm step in deploy pipeline) | Not run |
