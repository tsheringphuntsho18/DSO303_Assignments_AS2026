#!/usr/bin/env python3
"""Exercises the two Task-1 walkthroughs against a deployed EduExam stack.

Use this to produce the live AWS deployment video required by the rubric:
record your screen while this script runs against the real API, then show
the matching CloudWatch logs / dashboard and the file landing in S3.

Usage:
    pip install -r requirements.txt
    python3 simulate.py walkthrough1 --api-url https://... --exam-id exam-101 \
        --user-pool-id us-east-1_xxx --client-id xxx --email s@example.com --password '...'

    python3 simulate.py walkthrough2 --api-url https://... --assignment-id assign-55 \
        --user-pool-id us-east-1_xxx --client-id xxx --email s@example.com --password '...' \
        --file-size-mb 40

    python3 simulate.py az-load-test --api-url https://... --exam-id exam-101 \
        --concurrency 100 --requests 3000   # approximates the exam-week spike
"""
import argparse
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    from pycognito import Cognito
except ImportError:
    Cognito = None


def get_token(args) -> str:
    if not all([args.user_pool_id, args.client_id, args.email, args.password]):
        print("warning: no Cognito credentials given, calling the API unauthenticated", file=sys.stderr)
        return ""
    if Cognito is None:
        print("error: pip install -r requirements.txt (missing pycognito)", file=sys.stderr)
        sys.exit(1)
    user = Cognito(args.user_pool_id, args.client_id, username=args.email)
    user.authenticate(password=args.password)
    return user.id_token


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def walkthrough1(args):
    """Student opens an exam and answers autosave every 30 seconds."""
    token = get_token(args)
    base = args.api_url.rstrip("/")

    t0 = time.time()
    r = requests.get(f"{base}/exams/{args.exam_id}/start", headers=headers(token), timeout=10)
    r.raise_for_status()
    attempt = r.json()
    print(f"[open-exam] {r.status_code} in {time.time()-t0:.2f}s -> attemptId={attempt['attemptId']}")

    for i in range(args.autosave_count):
        time.sleep(args.autosave_interval)
        t0 = time.time()
        r = requests.put(
            f"{base}/attempts/{attempt['attemptId']}/answers",
            json={"answers": {"q1": "A", "q2": "C"}},
            headers=headers(token),
            timeout=10,
        )
        r.raise_for_status()
        print(f"[autosave {i+1}/{args.autosave_count}] {r.status_code} in {time.time()-t0:.2f}s")

    r = requests.post(f"{base}/attempts/{attempt['attemptId']}/submit", headers=headers(token), timeout=10)
    print(f"[submit] {r.status_code}")


def walkthrough2(args):
    """Student uploads an N MB assignment; tutor notification is async (check SES/CloudWatch)."""
    token = get_token(args)
    base = args.api_url.rstrip("/")
    size_bytes = args.file_size_mb * 1024 * 1024
    file_name = f"assignment-{int(time.time())}.zip"

    t0 = time.time()
    r = requests.post(
        f"{base}/assignments/{args.assignment_id}/upload-url",
        json={"fileName": file_name, "contentType": "application/zip", "fileSizeBytes": size_bytes},
        headers=headers(token),
        timeout=10,
    )
    r.raise_for_status()
    presign = r.json()
    print(f"[presign-upload] {r.status_code} in {time.time()-t0:.2f}s -> key={presign['key']}")

    payload = io.BytesIO(b"\0" * size_bytes)  # synthetic file content, real bytes don't matter for the test
    t0 = time.time()
    r = requests.put(presign["uploadUrl"], data=payload, headers={"Content-Type": "application/zip"}, timeout=120)
    r.raise_for_status()
    elapsed = time.time() - t0
    print(f"[s3-put] {r.status_code} — {args.file_size_mb}MB in {elapsed:.2f}s ({args.file_size_mb/elapsed:.1f} MB/s)")
    print("Tutor notification is async: check the email-queue consumer's CloudWatch logs or the tutor's inbox/SES sandbox.")


def az_load_test(args):
    """Approximates '3,000 students start one exam within 5 minutes' by firing concurrent open-exam calls."""
    token = get_token(args)
    base = args.api_url.rstrip("/")

    def one_request(i):
        t0 = time.time()
        try:
            r = requests.get(f"{base}/exams/{args.exam_id}/start", headers=headers(token), timeout=15)
            return i, r.status_code, time.time() - t0
        except requests.RequestException as e:
            return i, f"error: {e}", time.time() - t0

    print(f"Firing {args.requests} requests at concurrency {args.concurrency}...")
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(one_request, i) for i in range(args.requests)]
        for f in as_completed(futures):
            results.append(f.result())

    ok = sum(1 for _, status, _ in results if status == 200)
    latencies = sorted(d for _, status, d in results if status == 200)
    p50 = latencies[len(latencies) // 2] if latencies else float("nan")
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else float("nan")
    print(f"Success: {ok}/{args.requests}  p50={p50:.2f}s  p99={p99:.2f}s")
    print("Cross-check against the CloudWatch dashboard (ApiGateway 5xx, Lambda throttles, Aurora connections).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-url", required=True, help="API base, e.g. https://<cloudfront>/api or the raw api_invoke_url")
    common.add_argument("--user-pool-id", default="")
    common.add_argument("--client-id", default="")
    common.add_argument("--email", default="")
    common.add_argument("--password", default="")

    p1 = sub.add_parser("walkthrough1", parents=[common])
    p1.add_argument("--exam-id", required=True)
    p1.add_argument("--autosave-count", type=int, default=3)
    p1.add_argument("--autosave-interval", type=float, default=30.0)
    p1.set_defaults(func=walkthrough1)

    p2 = sub.add_parser("walkthrough2", parents=[common])
    p2.add_argument("--assignment-id", required=True)
    p2.add_argument("--file-size-mb", type=int, default=40)
    p2.set_defaults(func=walkthrough2)

    p3 = sub.add_parser("az-load-test", parents=[common])
    p3.add_argument("--exam-id", required=True)
    p3.add_argument("--concurrency", type=int, default=50)
    p3.add_argument("--requests", type=int, default=300)
    p3.set_defaults(func=az_load_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
