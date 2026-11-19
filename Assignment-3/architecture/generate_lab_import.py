#!/usr/bin/env python3
"""Generates evidence/lab-import.json for the Cloud Architecture Lab's
Export > Upload JSON feature — the Assignment 3 revised architecture,
adapted from Assignment 2's generate_lab_import.py (which built and
verified the schema against the live app). See that file's docstring for
the full schema notes; this file only documents what's NEW here.

CHANGED vs Assignment 2's generator:
  - region label updated to ap-southeast-1 throughout node notes
  - NAT Gateway B relabelled "exam-months only" (architecture/CHANGE_LOG.md #4)
  - 4 new VPC interface endpoints added: SQS, Cognito IDP, KMS, SES
    (CHANGE_LOG #5) — alongside a Secrets Manager endpoint node that A2's
    generator omitted even though the Terraform already had one
  - New DynamoDB table (exam-answers, autosave writes) added (CHANGE_LOG #6)

UPDATE: the serviceId guesses below (DynamoDB "dynamodb", and the 4
interface endpoints as "vpc_endpoint_interface") have since been confirmed
working — see evidence/s1.png, a screenshot of this exact lab-import.json
loaded into the live app with every node, including those 5, rendering
correctly and no "unknown service" boxes. Left the guess/caution framing
below for anyone regenerating this after an app update changes the catalog.

CAUTION (historical, now resolved per the above) — serviceId guesses not
independently verified at the time this was written: A2's generator's
serviceIds (route53, waf, cloudfront, lambda, aurora_serverless, sqs, kms,
s3_gateway_endpoint, etc.) were confirmed working against the live app.
This file ADDS serviceIds for DynamoDB ("dynamodb") and for 4 interface
endpoints (reusing the "vpc_endpoint_interface" pattern, analogous to
A2's working "s3_gateway_endpoint"). If a future app update rejects one of
these nodes, open its "Add Service" search palette, find the correct
serviceId string for that service, and substitute it into the SERVICE_ID_*
constants below.

Usage:
    python3 architecture/generate_lab_import.py
    # then in the lab: Export -> Upload JSON -> select evidence/lab-import.json
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_FILE = HERE.parent / "evidence" / "lab-import.json"

SERVICE_W, SERVICE_H = 140, 99

# Best-effort serviceIds not verified against the live app — see CAUTION above.
SERVICE_ID_DYNAMODB = "dynamodb"
SERVICE_ID_VPC_ENDPOINT_INTERFACE = "vpc_endpoint_interface"

SERVICE_OPERATIONS = {
    "rds_proxy": {"action": "Connect", "resource": {"engineFamily": "POSTGRESQL", "port": 5432, "status": "available", "credentialsValid": True}, "request": {}},
    "aurora_serverless": {"action": "Connect", "resource": {"engine": "aurora-postgresql", "port": 5432, "status": "available", "minCapacityAcu": 0.5, "paused": False, "credentialsValid": True}, "request": {}},
    "secrets_manager": {"action": "secretsmanager:GetSecretValue", "resource": {"SecretId": "eduexam-db-credentials", "versions": [{"VersionId": "00000000000000000000000000000001", "VersionStages": ["AWSCURRENT"], "SecretString": "synthetic-training-value"}]}, "request": {}},
    "cloudwatch": {"action": "cloudwatch:PutMetricData", "resource": {}, "request": {"Namespace": "EduExam/Api", "MetricData": [{"MetricName": "Requests", "Value": 1}]}},
    "eventbridge": {"action": "events:PutEvents", "resource": {"exists": True}, "request": {"Entries": [{"Source": "eduexam.submissions", "DetailType": "Object Created", "Detail": '{"bucket":"eduexam-submissions"}'}]}},
    "kms": {"action": "kms:DescribeKey", "resource": {"KeyId": "eduexam-key", "KeyState": "Enabled", "KeyUsage": "ENCRYPT_DECRYPT"}, "request": {}},
    "dynamodb": {"action": "dynamodb:PutItem", "resource": {"TableName": "exam-answers", "status": "ACTIVE"}, "request": {"TableName": "exam-answers", "Item": {"attemptId": {"S": "synthetic"}, "questionId": {"S": "synthetic"}}}},
}


def operation_lab(service_id, caller_id):
    op = dict(SERVICE_OPERATIONS[service_id])
    op["callerId"] = caller_id
    return {"operationLab": op}


def iam_role(role_id, trusted_service, grants):
    statements = [
        {"effect": "Allow", "actions": actions, "resources": resources}
        for actions, resources in grants
    ]
    return {
        "id": role_id,
        "trustPolicy": {
            "id": f"{role_id}-trust", "kind": "trust",
            "statements": [{"effect": "Allow", "actions": ["sts:AssumeRole"], "resources": [], "principals": [trusted_service]}],
        },
        "identityPolicies": [{"id": f"{role_id}-permissions", "kind": "identity", "statements": statements}],
    }


nodes = []
edges = []


def boundary(id_, label, boundary_type, x, y, w, h, z, az=None, cidr=None):
    data = {"label": label, "boundaryType": boundary_type, "width": w, "height": h}
    if az:
        data["az"] = az
    if cidr:
        data["cidr"] = cidr
    nodes.append({
        "id": id_, "type": "boundaryNode", "position": {"x": x, "y": y},
        "style": {"width": w, "height": h}, "measured": {"width": w, "height": h},
        "zIndex": z, "data": data,
    })
    return id_


def service(id_, service_id, label, category, x, y, az="Edge / Global", subnet="global", multi_az=False,
            notes=None, custom_config=None, role=None):
    data = {
        "serviceId": service_id, "label": label, "category": category,
        "health": "healthy", "az": az, "subnet": subnet, "replicas": 1, "multiAz": multi_az,
        "width": SERVICE_W, "height": SERVICE_H,
    }
    if notes:
        data["notes"] = notes
    if custom_config:
        data["customConfig"] = custom_config
    if role:
        data["iamRole"] = role
    nodes.append({
        "id": id_, "type": "serviceNode", "position": {"x": x, "y": y},
        "style": {"width": SERVICE_W, "height": SERVICE_H},
        "measured": {"width": SERVICE_W, "height": SERVICE_H},
        "zIndex": 10, "data": data,
    })
    return id_


def edge(source, target, protocol, interaction="synchronous", dependency=False, critical=True, relationship=None):
    data = {
        "interactionType": interaction, "isCriticalDependency": critical,
        "timeoutMs": 1500, "isSimulating": False, "isFailing": False,
    }
    if protocol is not None:
        data["protocol"] = protocol
    if dependency:
        data["traversal"] = "dependency"
    if relationship:
        data["relationship"] = relationship
    edges.append({"id": f"{source}__{target}", "source": source, "target": target, "type": "custom", "data": data})


# ---------------------------------------------------------------------------
# Edge / global tier (top row) — region: ap-southeast-1
# ---------------------------------------------------------------------------
service("eduexam-dns", "route53", "Route 53", "Networking & Content Delivery", 40, 40)
service("eduexam-waf", "waf", "AWS WAF", "Security, Identity & Compliance", 220, 40)
service("eduexam-cdn", "cloudfront", "CloudFront (Price Class 200)", "Networking & Content Delivery", 400, 40,
        notes="CHANGED vs A2: Price Class 100 -> 200 for APAC edge coverage; compression on")
service("eduexam-cert", "acm", "ACM Certificate (us-east-1 — AWS requirement)", "Security, Identity & Compliance", 580, 40)
service("eduexam-auth", "cognito", "Cognito", "Security, Identity & Compliance", 760, 40)
service("eduexam-api", "api_gateway", "API Gateway", "Networking & Content Delivery", 940, 40)
service("eduexam-frontend", "s3", "S3: eduexam-frontend", "Storage", 1120, 40)

# ---------------------------------------------------------------------------
# VPC — ap-southeast-1, 2 Availability Zones
# ---------------------------------------------------------------------------
boundary("eduexam-vpc", "eduexam-vpc (ap-southeast-1)", "vpc", 40, 200, 1360, 820, -4, cidr="10.0.0.0/16")
boundary("public-subnet-a", "public-subnet-a · AZ-A", "public_subnet", 80, 340, 560, 220, -3, az="AZ-A")
boundary("public-subnet-b", "public-subnet-b · AZ-B", "public_subnet", 680, 340, 560, 220, -3, az="AZ-B")
boundary("private-subnet-a", "private-subnet-a · AZ-A", "private_subnet", 80, 600, 560, 380, -3, az="AZ-A")
boundary("private-subnet-b", "private-subnet-b · AZ-B", "private_subnet", 680, 600, 560, 380, -3, az="AZ-B")

service("eduexam-igw", "internet_gateway", "Internet Gateway", "Networking & Content Delivery",
        680, 210, az="Edge / Global", subnet="global")

service("nat-a", "nat_gateway", "NAT Gateway A — ALWAYS ON", "Networking & Content Delivery",
        120, 380, az="AZ-A", subnet="public")
service("nat-b", "nat_gateway", "NAT Gateway B — EXAM MONTHS ONLY (SPOF 10mo/yr)", "Networking & Content Delivery",
        720, 380, az="AZ-B", subnet="public",
        notes="CHANGED vs A2: removed in the 10 normal months (single_nat_gateway=true); "
              "restored for the 2 exam months. See architecture/CHANGE_LOG.md #4.")

service("lambda-api-a", "lambda", "Lambda (API handlers, AZ-A)", "Compute",
        120, 640, az="AZ-A", subnet="private")
service("eduexam-rds-proxy", "rds_proxy", "RDS Proxy", "Databases",
        300, 640, az="Multi-AZ", subnet="private", custom_config=operation_lab("rds_proxy", "lambda-api-a"),
        role=iam_role("eduexam-rds-proxy-role", "rds.amazonaws.com", [
            (["secretsmanager:GetSecretValue"], ["arn:aws:secretsmanager:ap-southeast-1:000000000000:secret:eduexam-secrets"]),
            (["kms:Decrypt"], ["arn:aws:kms:ap-southeast-1:000000000000:key:eduexam-kms"]),
        ]))
service("aurora-writer", "aurora_serverless", "Aurora Serverless v2 (writer)", "Databases",
        480, 640, az="AZ-A", subnet="private", multi_az=True,
        custom_config=operation_lab("aurora_serverless", "eduexam-rds-proxy"))

service("lambda-api-b", "lambda", "Lambda (API handlers, AZ-B)", "Compute",
        720, 640, az="AZ-B", subnet="private")
service("aurora-reader", "aurora_serverless", "Aurora Serverless v2 (reader)", "Databases",
        900, 640, az="AZ-B", subnet="private", multi_az=True,
        custom_config=operation_lab("aurora_serverless", "aurora-writer"))

# --- VPC Endpoints — NEW/expanded: only s3-endpoint existed as a node in A2's
# generator (Secrets Manager had a real Terraform endpoint but no lab node).
# Both AZs' private subnets reach all 6 via the endpoint, shown once each for
# clarity rather than duplicated per-AZ.
service("s3-endpoint", "s3_gateway_endpoint", "S3 Gateway Endpoint", "Networking & Content Delivery",
        120, 760, az="AZ-A", subnet="private")
service("secrets-endpoint", SERVICE_ID_VPC_ENDPOINT_INTERFACE, "Secrets Manager Interface Endpoint",
        "Networking & Content Delivery", 300, 760, az="Multi-AZ", subnet="private")
service("sqs-endpoint", SERVICE_ID_VPC_ENDPOINT_INTERFACE, "SQS Interface Endpoint — NEW",
        "Networking & Content Delivery", 480, 760, az="Multi-AZ", subnet="private")
service("cognito-endpoint", SERVICE_ID_VPC_ENDPOINT_INTERFACE, "Cognito IDP Interface Endpoint — NEW",
        "Networking & Content Delivery", 120, 860, az="Multi-AZ", subnet="private")
service("kms-endpoint", SERVICE_ID_VPC_ENDPOINT_INTERFACE, "KMS Interface Endpoint — NEW",
        "Networking & Content Delivery", 300, 860, az="Multi-AZ", subnet="private")
service("ses-endpoint", SERVICE_ID_VPC_ENDPOINT_INTERFACE, "SES Interface Endpoint — NEW",
        "Networking & Content Delivery", 480, 860, az="Multi-AZ", subnet="private")

# ---------------------------------------------------------------------------
# Storage + asynchronous processing tier (right column)
# ---------------------------------------------------------------------------
service("eduexam-submissions", "s3", "S3: eduexam-submissions", "Storage", 1480, 200)
service("eduexam-answers", SERVICE_ID_DYNAMODB, "DynamoDB: exam-answers — NEW (On-Demand, PITR)",
        "Databases", 1480, 310,
        notes="NEW in Assignment 3 (CHANGE_LOG #6): autosave writes move here from Aurora. "
              "On-Demand capacity — no ACU-style ceiling during the exam-start burst.",
        custom_config=operation_lab("dynamodb", "lambda-api-a"))
service("eduexam-events", "eventbridge", "EventBridge", "Integration & Messaging", 1480, 420,
        custom_config=operation_lab("eventbridge", "eduexam-submissions"))
service("marking-queue", "sqs", "SQS: marking-queue", "Integration & Messaging", 1480, 530)
service("marking-dlq", "sqs_dlq", "DLQ: marking-dlq", "Integration & Messaging", 1680, 530)
service("email-queue", "sqs", "SQS: email-queue", "Integration & Messaging", 1480, 640)
service("email-dlq", "sqs_dlq", "DLQ: email-dlq", "Integration & Messaging", 1680, 640)
service("lambda-automark", "lambda", "Lambda: automark", "Compute", 1480, 750)
service("lambda-notify-tutor", "lambda", "Lambda: notify-tutor", "Compute", 1680, 750)
service("lambda-send-email", "lambda", "Lambda: send-email", "Compute", 1480, 860)
service("eduexam-ses", "ses", "Amazon SES", "Business Applications", 1680, 860)

# ---------------------------------------------------------------------------
# Secrets, monitoring & audit tier (bottom row)
# ---------------------------------------------------------------------------
service("eduexam-secrets", "secrets_manager", "Secrets Manager", "Security, Identity & Compliance", 40, 1100,
        custom_config=operation_lab("secrets_manager", "eduexam-rds-proxy"))
service("eduexam-kms", "kms", "AWS KMS", "Security, Identity & Compliance", 220, 1100,
        custom_config=operation_lab("kms", "eduexam-secrets"))
service("eduexam-monitoring", "cloudwatch", "CloudWatch", "Management & Governance", 400, 1100,
        custom_config=operation_lab("cloudwatch", "eduexam-api"))
service("eduexam-audit", "cloudtrail", "CloudTrail", "Management & Governance", 580, 1100)
service("eduexam-iam", "iam", "AWS IAM", "Security, Identity & Compliance", 760, 1100)

# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
edge("eduexam-dns", "eduexam-cdn", "HTTPS")
edge("eduexam-waf", "eduexam-cdn", "HTTPS", dependency=True, critical=False)
edge("eduexam-cert", "eduexam-cdn", "TLS", dependency=True, critical=False)
edge("eduexam-cdn", "eduexam-frontend", "HTTPS")
edge("eduexam-cdn", "eduexam-api", "HTTPS")
edge("eduexam-api", "eduexam-auth", "HTTPS", dependency=True)
edge("eduexam-api", "lambda-api-a", "HTTPS")
edge("eduexam-api", "lambda-api-b", "HTTPS")
edge("lambda-api-a", "eduexam-rds-proxy", "SQL")
edge("lambda-api-b", "eduexam-rds-proxy", "SQL")
edge("eduexam-rds-proxy", "aurora-writer", None)
edge("eduexam-rds-proxy", "aurora-reader", None)
edge("aurora-writer", "aurora-reader", "Replication", dependency=True)
edge("lambda-api-a", "eduexam-submissions", "HTTPS")
edge("lambda-api-b", "eduexam-submissions", "HTTPS")
# NEW: autosave answer-writes go to DynamoDB, not Aurora (CHANGE_LOG #6)
edge("lambda-api-a", "eduexam-answers", "HTTPS", dependency=True)
edge("lambda-api-b", "eduexam-answers", "HTTPS", dependency=True)
edge("lambda-automark", "eduexam-answers", "HTTPS", dependency=True, critical=False)
edge("eduexam-submissions", "eduexam-events", "Event", interaction="asynchronous", dependency=True)
edge("eduexam-events", "lambda-notify-tutor", "Event", interaction="asynchronous", dependency=True)
edge("lambda-notify-tutor", "email-queue", "Message", interaction="asynchronous", dependency=True)
edge("email-queue", "lambda-send-email", "Message", interaction="asynchronous", dependency=True)
edge("email-queue", "email-dlq", "Message", interaction="asynchronous", dependency=True, critical=False)
edge("lambda-send-email", "eduexam-ses", "HTTPS", dependency=True)
edge("lambda-api-a", "marking-queue", "Message", interaction="asynchronous", dependency=True)
edge("marking-queue", "lambda-automark", "Message", interaction="asynchronous", dependency=True)
edge("marking-queue", "marking-dlq", "Message", interaction="asynchronous", dependency=True, critical=False)
edge("lambda-api-a", "eduexam-secrets", "HTTPS", dependency=True, critical=False)
edge("lambda-api-b", "eduexam-secrets", "HTTPS", dependency=True, critical=False)
edge("eduexam-rds-proxy", "eduexam-secrets", "HTTPS", relationship="manages", critical=False)
edge("eduexam-submissions", "eduexam-kms", "All", dependency=True, critical=False)
edge("aurora-writer", "eduexam-kms", "All", dependency=True, critical=False)
edge("eduexam-answers", "eduexam-kms", "All", dependency=True, critical=False)
edge("eduexam-secrets", "eduexam-kms", "All", dependency=True, critical=False)
edge("nat-a", "eduexam-igw", "All", dependency=True, critical=False)
edge("nat-b", "eduexam-igw", "All", dependency=True, critical=False)
edge("eduexam-api", "eduexam-audit", "All", interaction="asynchronous", dependency=True, critical=False)
# NEW: the 4 added interface endpoints + the previously-undiagrammed Secrets
# Manager endpoint, wired to whichever Lambda is the realistic caller
edge("lambda-api-a", "sqs-endpoint", "All", dependency=True, critical=False)
edge("lambda-api-a", "cognito-endpoint", "All", dependency=True, critical=False)
edge("lambda-api-a", "kms-endpoint", "All", dependency=True, critical=False)
edge("lambda-send-email", "ses-endpoint", "All", dependency=True, critical=False)
edge("lambda-api-b", "secrets-endpoint", "All", dependency=True, critical=False)

# ---------------------------------------------------------------------------
draft = {
    "format": "aws-architecture-lab",
    "version": 2,
    "exportedAt": "generated-by-generate_lab_import.py",
    "state": {
        "draftName": "EduExam Architecture — Assignment 3 (ap-southeast-1, cost-optimized)",
        "nodes": nodes,
        "edges": edges,
        "scenario": {
            "id": "eduexam-walkthrough-1",
            "name": "Student opens an exam",
            "method": "GET",
            "path": "/api/exams/{examId}/start",
            "startNodeId": "eduexam-dns",
            "trafficLevel": "normal",
        },
        "simulationResult": None,
        "activeFailures": [],
        "activeLabReference": None,
        "activeChallengeId": None,
        "challengeResult": None,
        "appMode": "design",
        "selectedNodeId": None,
        "selectedEdgeId": None,
        "playbackSpeed": 1,
        "highlightTaskFlow": False,
        "showNaclSideColumn": False,
        "activeStepIndex": None,
        "viewport": None,
    },
}


def check_bounds():
    by_id = {n["id"]: n for n in nodes}
    boxes = {}
    for n in nodes:
        if n["type"] == "boundaryNode":
            x, y = n["position"]["x"], n["position"]["y"]
            w, h = n["style"]["width"], n["style"]["height"]
            boxes[n["id"]] = (x, y, x + w, y + h)

    def inside(child, parent_id):
        cx, cy = child["position"]["x"], child["position"]["y"]
        cw, ch = child["style"]["width"], child["style"]["height"]
        px0, py0, px1, py1 = boxes[parent_id]
        return px0 <= cx and py0 <= cy and cx + cw <= px1 and cy + ch <= py1

    pairs = [
        ("nat-a", "public-subnet-a"), ("nat-b", "public-subnet-b"),
        ("lambda-api-a", "private-subnet-a"), ("eduexam-rds-proxy", "private-subnet-a"),
        ("aurora-writer", "private-subnet-a"), ("s3-endpoint", "private-subnet-a"),
        ("secrets-endpoint", "private-subnet-a"), ("sqs-endpoint", "private-subnet-a"),
        ("cognito-endpoint", "private-subnet-a"), ("kms-endpoint", "private-subnet-a"),
        ("lambda-api-b", "private-subnet-b"), ("aurora-reader", "private-subnet-b"),
        ("ses-endpoint", "private-subnet-a"),
        ("public-subnet-a", "eduexam-vpc"), ("public-subnet-b", "eduexam-vpc"),
        ("private-subnet-a", "eduexam-vpc"), ("private-subnet-b", "eduexam-vpc"),
        ("eduexam-igw", "eduexam-vpc"),
    ]
    for child_id, parent_id in pairs:
        assert inside(by_id[child_id], parent_id), f"{child_id} is not visually inside {parent_id}"


def main():
    node_ids = {n["id"] for n in nodes}
    assert len(node_ids) == len(nodes), "duplicate node ids"
    for e in edges:
        assert e["source"] in node_ids, f"edge source missing: {e['source']}"
        assert e["target"] in node_ids, f"edge target missing: {e['target']}"
    check_bounds()

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(draft, indent=2))
    print(f"Wrote {OUT_FILE} — {len(nodes)} nodes, {len(edges)} edges")


if __name__ == "__main__":
    main()
