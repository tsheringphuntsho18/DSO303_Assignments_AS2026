#!/usr/bin/env python3
"""Generates evidence/lab-import.json — a file for the Cloud Architecture Lab's
Export > Upload JSON feature that builds the full EduExam architecture in one
step, instead of dragging ~36 nodes and ~33 connections by hand.

Schema notes (reverse-engineered from the lab app's own JS bundle, not
guessed): the wrapper is {"format": "aws-architecture-lab", "version": 2,
"state": {...}} per the app's strict import validator. Node/edge field
conventions below were copied from the app's own bundled reference diagram
(a "usms-vpc" two-AZ VPC scenario it ships and renders itself), which is the
most authoritative sample available:
  - Every node uses an ABSOLUTE canvas position. There is no parentId-based
    nesting in this app's canonical v2 format — a service "sits inside" a
    subnet purely because its bounding box geometrically overlaps the
    subnet boundary node's box.
  - Every node carries an explicit top-level "zIndex", plus "style" and
    "measured" both set to the same {width, height}. Boundary nodes use
    deeply negative zIndex (-4 for the VPC, -3 for subnets) so they always
    paint behind service nodes (zIndex 10) and edges (default) — omitting
    this is what made connections invisible (hidden behind opaque subnet
    boxes) in the first generated version of this file.
  - Edges are plain: {id, source, target, type:"custom", data:{protocol,
    interactionType, isCriticalDependency, timeoutMs, isSimulating,
    isFailing}} — no sourceHandle/targetHandle/markerEnd needed.

Usage:
    python3 architecture/generate_lab_import.py
    # then in the lab: Export -> Upload JSON -> select evidence/lab-import.json
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_FILE = HERE.parent / "evidence" / "lab-import.json"

SERVICE_W, SERVICE_H = 140, 99

# Default "service operation" templates, copied verbatim from the lab app's
# own built-in defaults (its n0 lookup table) for each serviceId, plus the
# `action` each one requires. Without data.customConfig.operationLab =
# {action, resource, request, callerId} populated, the Simulate engine can
# trace a request as far as these nodes but then reports "Service operation
# failed" at the final hop, since it has no response to construct from and
# no caller to authorize. callerId is assigned per-node below (whichever
# upstream node actually calls it on the simulated request path).
SERVICE_OPERATIONS = {
    "rds_proxy": {"action": "Connect", "resource": {"engineFamily": "POSTGRESQL", "port": 5432, "status": "available", "credentialsValid": True}, "request": {}},
    "aurora_serverless": {"action": "Connect", "resource": {"engine": "aurora-postgresql", "port": 5432, "status": "available", "minCapacityAcu": 0.5, "paused": False, "credentialsValid": True}, "request": {}},
    "secrets_manager": {"action": "secretsmanager:GetSecretValue", "resource": {"SecretId": "eduexam-db-credentials", "versions": [{"VersionId": "00000000000000000000000000000001", "VersionStages": ["AWSCURRENT"], "SecretString": "synthetic-training-value"}]}, "request": {}},
    "cloudwatch": {"action": "cloudwatch:PutMetricData", "resource": {}, "request": {"Namespace": "EduExam/Api", "MetricData": [{"MetricName": "Requests", "Value": 1}]}},
    "eventbridge": {"action": "events:PutEvents", "resource": {"exists": True}, "request": {"Entries": [{"Source": "eduexam.submissions", "DetailType": "Object Created", "Detail": '{"bucket":"eduexam-submissions"}'}]}},
    "kms": {"action": "kms:DescribeKey", "resource": {"KeyId": "eduexam-key", "KeyState": "Enabled", "KeyUsage": "ENCRYPT_DECRYPT"}, "request": {}},
}


def operation_lab(service_id, caller_id):
    op = dict(SERVICE_OPERATIONS[service_id])
    op["callerId"] = caller_id
    return {"operationLab": op}


def iam_role(role_id, trusted_service, grants):
    """grants: list of (actions, resource_arns) tuples. Resource ARN format
    was found empirically per-service by reading the simulator's own denial
    messages (e.g. Secrets Manager wants the full
    arn:aws:secretsmanager:us-east-1:000000000000:secret:<node-id> form, not
    a simplified one) rather than guessed from a single template."""
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
        # Omitted (not just null) on purpose for the one edge that needs
        # protocol strictly undefined for the engine's "find managed
        # resource" lookup (see RDS Proxy -> Aurora below) - it reconstructs
        # the real SQL protocol internally for the actual connection check.
        data["protocol"] = protocol
    if dependency:
        data["traversal"] = "dependency"
    if relationship:
        # Overrides the derived "dependency"/"request" meaning. The Simulate
        # engine's per-service operation checks (e.g. RDS Proxy looking for
        # its Secrets Manager credential source) specifically require
        # relationship == "manages" on the edge from the dependant *to* the
        # config/credential store it reads, not just a generic dependency.
        data["relationship"] = relationship
    edges.append({"id": f"{source}__{target}", "source": source, "target": target, "type": "custom", "data": data})


# ---------------------------------------------------------------------------
# Edge / global tier (top row) — not inside the VPC, matching real AWS: these
# are regional/global managed services, not subnet-bound resources.
# ---------------------------------------------------------------------------
service("eduexam-dns", "route53", "Route 53", "Networking & Content Delivery", 40, 40)
service("eduexam-waf", "waf", "AWS WAF", "Security, Identity & Compliance", 220, 40)
service("eduexam-cdn", "cloudfront", "CloudFront", "Networking & Content Delivery", 400, 40)
service("eduexam-cert", "acm", "ACM Certificate", "Security, Identity & Compliance", 580, 40)
service("eduexam-auth", "cognito", "Cognito", "Security, Identity & Compliance", 760, 40)
service("eduexam-api", "api_gateway", "API Gateway", "Networking & Content Delivery", 940, 40)
service("eduexam-frontend", "s3", "S3: eduexam-frontend", "Storage", 1120, 40)

# ---------------------------------------------------------------------------
# VPC — 2 Availability Zones, public + private subnets
# ---------------------------------------------------------------------------
boundary("eduexam-vpc", "eduexam-vpc", "vpc", 40, 200, 1360, 700, -4, cidr="10.0.0.0/16")
boundary("public-subnet-a", "public-subnet-a · AZ-A", "public_subnet", 80, 340, 560, 220, -3, az="AZ-A")
boundary("public-subnet-b", "public-subnet-b · AZ-B", "public_subnet", 680, 340, 560, 220, -3, az="AZ-B")
boundary("private-subnet-a", "private-subnet-a · AZ-A", "private_subnet", 80, 600, 560, 260, -3, az="AZ-A")
boundary("private-subnet-b", "private-subnet-b · AZ-B", "private_subnet", 680, 600, 560, 260, -3, az="AZ-B")

service("eduexam-igw", "internet_gateway", "Internet Gateway", "Networking & Content Delivery",
        680, 210, az="Edge / Global", subnet="global")

service("nat-a", "nat_gateway", "NAT Gateway A", "Networking & Content Delivery",
        120, 380, az="AZ-A", subnet="public")
service("nat-b", "nat_gateway", "NAT Gateway B", "Networking & Content Delivery",
        720, 380, az="AZ-B", subnet="public")

service("lambda-api-a", "lambda", "Lambda (API handlers, AZ-A)", "Compute",
        120, 640, az="AZ-A", subnet="private")
service("eduexam-rds-proxy", "rds_proxy", "RDS Proxy", "Databases",
        # Not tagged AZ-A/AZ-B: RDS Proxy is an AWS-managed, inherently
        # Multi-AZ endpoint (the Terraform passes both private subnets to
        # aws_db_proxy.main), so a single AZ outage must not take it down.
        300, 640, az="Multi-AZ", subnet="private", custom_config=operation_lab("rds_proxy", "lambda-api-a"),
        role=iam_role("eduexam-rds-proxy-role", "rds.amazonaws.com", [
            (["secretsmanager:GetSecretValue"], ["arn:aws:secretsmanager:us-east-1:000000000000:secret:eduexam-secrets"]),
            (["kms:Decrypt"], ["arn:aws:kms:us-east-1:000000000000:key:eduexam-kms"]),
        ]))
service("aurora-writer", "aurora_serverless", "Aurora Serverless v2 (writer)", "Databases",
        480, 640, az="AZ-A", subnet="private", multi_az=True,
        custom_config=operation_lab("aurora_serverless", "eduexam-rds-proxy"))
service("s3-endpoint", "s3_gateway_endpoint", "S3 Gateway Endpoint", "Networking & Content Delivery",
        120, 760, az="AZ-A", subnet="private")

service("lambda-api-b", "lambda", "Lambda (API handlers, AZ-B)", "Compute",
        720, 640, az="AZ-B", subnet="private")
service("aurora-reader", "aurora_serverless", "Aurora Serverless v2 (reader)", "Databases",
        900, 640, az="AZ-B", subnet="private", multi_az=True,
        custom_config=operation_lab("aurora_serverless", "aurora-writer"))

# ---------------------------------------------------------------------------
# Storage + asynchronous processing tier (right column)
# ---------------------------------------------------------------------------
service("eduexam-submissions", "s3", "S3: eduexam-submissions", "Storage", 1480, 200)
service("eduexam-events", "eventbridge", "EventBridge", "Integration & Messaging", 1480, 310,
        custom_config=operation_lab("eventbridge", "eduexam-submissions"))
service("marking-queue", "sqs", "SQS: marking-queue", "Integration & Messaging", 1480, 420)
service("marking-dlq", "sqs_dlq", "DLQ: marking-dlq", "Integration & Messaging", 1680, 420)
service("email-queue", "sqs", "SQS: email-queue", "Integration & Messaging", 1480, 530)
service("email-dlq", "sqs_dlq", "DLQ: email-dlq", "Integration & Messaging", 1680, 530)
service("lambda-automark", "lambda", "Lambda: automark", "Compute", 1480, 640)
service("lambda-notify-tutor", "lambda", "Lambda: notify-tutor", "Compute", 1680, 640)
service("lambda-send-email", "lambda", "Lambda: send-email", "Compute", 1480, 750)
service("eduexam-ses", "ses", "Amazon SES", "Business Applications", 1680, 750)

# ---------------------------------------------------------------------------
# Secrets, monitoring & audit tier (bottom row)
# ---------------------------------------------------------------------------
service("eduexam-secrets", "secrets_manager", "Secrets Manager", "Security, Identity & Compliance", 40, 960,
        custom_config=operation_lab("secrets_manager", "eduexam-rds-proxy"))
service("eduexam-kms", "kms", "AWS KMS", "Security, Identity & Compliance", 220, 960,
        custom_config=operation_lab("kms", "eduexam-secrets"))
service("eduexam-monitoring", "cloudwatch", "CloudWatch", "Management & Governance", 400, 960,
        custom_config=operation_lab("cloudwatch", "eduexam-api"))
service("eduexam-audit", "cloudtrail", "CloudTrail", "Management & Governance", 580, 960)
service("eduexam-iam", "iam", "AWS IAM", "Security, Identity & Compliance", 760, 960)

# ---------------------------------------------------------------------------
# Connections — mirrors evidence/LAB_BUILD_GUIDE.md section 3
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
edge("eduexam-rds-proxy", "aurora-writer", None)  # protocol left undefined: required by the Simulate engine's
# "find target database" lookup for RDS Proxy; it reconstructs protocol:"SQL" internally for the actual check.
edge("eduexam-rds-proxy", "aurora-reader", None)  # second candidate target, same reason as above - without this
# the redundancy/cascading-failure analysis sees the proxy's only DB path as a single point of failure in AZ-A.
edge("aurora-writer", "aurora-reader", "Replication", dependency=True)
edge("lambda-api-a", "eduexam-submissions", "HTTPS")
edge("lambda-api-b", "eduexam-submissions", "HTTPS")
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
edge("eduexam-secrets", "eduexam-kms", "All", dependency=True, critical=False)
edge("nat-a", "eduexam-igw", "All", dependency=True, critical=False)
edge("nat-b", "eduexam-igw", "All", dependency=True, critical=False)
edge("eduexam-api", "eduexam-audit", "All", interaction="asynchronous", dependency=True, critical=False)

# ---------------------------------------------------------------------------
# Assemble the draft file
# ---------------------------------------------------------------------------
draft = {
    "format": "aws-architecture-lab",
    "version": 2,
    "exportedAt": "generated-by-generate_lab_import.py",
    "state": {
        "draftName": "EduExam Architecture",
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
    """Sanity check: every node with a boundaryType should geometrically
    contain any service node whose (az, subnet) marks it as belonging there.
    Not required by the app, just a build-time self-check."""
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
        ("lambda-api-b", "private-subnet-b"), ("aurora-reader", "private-subnet-b"),
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
