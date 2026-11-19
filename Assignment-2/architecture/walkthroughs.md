# Request Walkthroughs

Reference: component names match [`diagram.mmd`](diagram.mmd) and [`../docs/services.md`](../docs/services.md).

## Walkthrough 1 — Student opens an exam and answers autosave

1. **DNS & edge.** Student's browser resolves `eduexam.example.com` via **Route 53**, which returns the **CloudFront** distribution.
2. **Auth check.** The SPA (already loaded from CloudFront/S3) calls `POST /api/exams/{examId}/start`. **WAF** inspects the request at the edge, then CloudFront forwards `/api/*` to **API Gateway**.
3. **Authorization.** API Gateway's Cognito JWT authorizer validates the access token issued by **Cognito** at login and extracts the `student` group claim.
4. **Compute.** API Gateway invokes the `open-exam` **Lambda** function (running in a private subnet, picked from either AZ).
5. **Data read.** The Lambda reads the exam definition and creates an "attempt" row through **RDS Proxy** against **Aurora Serverless v2** (whichever AZ holds the current writer). The timer starts server-side so a client clock can't extend it.
6. **Response.** The exam JSON (questions, time remaining) returns to the browser through API Gateway → CloudFront → student.
7. **Autosave loop (every 30 seconds).** The SPA calls `PUT /api/attempts/{attemptId}/answers` on a timer. Each call repeats steps 2–5: WAF → API Gateway → Cognito authorizer → `autosave` Lambda → RDS Proxy → Aurora. A write only needs to reach Aurora's durable, Multi-AZ storage to be acknowledged, so at most one 30-second interval (well under the 5-minute RPO target) of answers can ever be at risk.
8. **Submission.** On submit or timeout, the same path marks the attempt `submitted`, which enqueues a message onto the **SQS `marking-queue`** for Walkthrough-style async auto-marking of MCQs (not re-diagrammed here — same pattern as Walkthrough 2's notification step).

## Walkthrough 2 — Student uploads a 40 MB assignment and the tutor is notified

1. **Request an upload slot.** The SPA calls `POST /api/assignments/{id}/upload-url`. Request passes WAF → CloudFront → API Gateway → Cognito authorizer → `presign-upload` **Lambda**.
2. **Presigned URL.** The Lambda validates the declared file type (PDF/ZIP) and size (≤ 50 MB) against the assignment's rules, then calls the S3 API (via the **S3 Gateway Endpoint**, staying inside the VPC) to generate a time-limited presigned `PUT` URL for the **`eduexam-submissions`** bucket. No file bytes touch Lambda or API Gateway.
3. **Direct upload.** The browser `PUT`s the 40 MB file straight to **S3** using the presigned URL, over TLS. This keeps the large payload off API Gateway's 10 MB limit and off the Lambda execution path entirely.
4. **Event trigger.** S3's `Object Created` event (EventBridge notifications enabled on the bucket) publishes to **EventBridge**.
5. **Notification.** An EventBridge rule matches the upload and invokes the `notify-tutor` **Lambda**, which writes a submission-received record via RDS Proxy to **Aurora** and enqueues a message on the **SQS `email-queue`**.
6. **Async email.** The `send-email` Lambda, triggered by the SQS queue, calls **Amazon SES** to email the tutor ("New submission from student X"). If SES fails transiently, SQS retries the message up to 5 times before routing it to the **DLQ**, where a CloudWatch alarm flags it for investigation — so a notification is never silently lost.
7. **Tutor view.** When the tutor opens their dashboard, a separate authenticated API call reads the submission list straight from Aurora — the notification step never blocks or depends on the tutor being online.

## Peak & Resilience Explanation (≤ 300 words)

> Word count: **294 / 300**

At exam-week peak, 3,000 students open one exam within five minutes. Every request hits CloudFront, then API Gateway, then stateless Lambda — all three scale automatically, with no fleet to pre-warm and no capacity plan to size in advance. Lambda's burst concurrency absorbs the spike; a per-function reserved-concurrency limit caps how many executions hit the database at once, throttling the surge smoothly instead of crashing it. RDS Proxy pools those bursty connections into a small, stable set against Aurora, preventing connection exhaustion — the usual failure mode when thousands of short-lived functions open direct database connections together. Autosave writes use this same pooled path every 30 seconds, so the 5-minute RPO holds under load. Static exam assets are served from CloudFront's edge cache, so the spike never reaches the origin for anything that doesn't change per student.

For AZ resilience, every component is deployed across two Availability Zones. The VPC has public and private subnets in each AZ, each private subnet with its own NAT Gateway so neither AZ depends on the other for egress. Lambda runs with ENIs in both private subnets. Aurora Serverless v2 is Multi-AZ: the writer and a reader sit in different AZs, and Aurora's storage layer already replicates across three AZs beneath that, so a single AZ failure triggers automatic failover typically under 30 seconds — well inside the 1-hour RTO. S3, SQS, EventBridge, Cognito and API Gateway are regional, multi-AZ services by default, so they need no extra redundancy work. Route 53 health checks on the API and CloudFront's multi-origin failover mean DNS and the edge never point at a dead path. No single AZ loss removes compute, database write capacity, or the student-facing entry point, which keeps the design inside the 99.9% availability target during exam week.
