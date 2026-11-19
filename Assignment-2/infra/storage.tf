locals {
  account_suffix = data.aws_caller_identity.current.account_id
}

# --- Frontend bucket: built SPA, served only through CloudFront (OAC) ---
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project}-frontend-${local.account_suffix}"
  tags   = { Name = "${var.project}-frontend" }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.main.arn }
      }
    }]
  })
}

# --- Submissions bucket: PDF/ZIP uploads up to 50 MB, 5-year retention ---
resource "aws_s3_bucket" "submissions" {
  bucket = "${var.project}-submissions-${local.account_suffix}"
  tags   = { Name = "${var.project}-submissions" }
}

resource "aws_s3_bucket_public_access_block" "submissions" {
  bucket                  = aws_s3_bucket.submissions.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "submissions" {
  bucket = aws_s3_bucket.submissions.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "submissions" {
  bucket = aws_s3_bucket.submissions.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_cors_configuration" "submissions" {
  bucket = aws_s3_bucket.submissions.id
  cors_rule {
    allowed_methods = ["PUT", "GET"]
    allowed_origins = var.domain_name != "" ? ["https://${var.domain_name}"] : ["*"]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

# Lifecycle: Standard -> Standard-IA (90d) -> Glacier Deep Archive (365d)
# -> expire at 1825d (5 years), matching the records-retention target.
resource "aws_s3_bucket_lifecycle_configuration" "submissions" {
  bucket = aws_s3_bucket.submissions.id

  rule {
    id     = "submission-retention"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }

    expiration {
      days = var.submission_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 180
    }
  }
}

# Submissions bucket emits ObjectCreated events to EventBridge, which drives
# the tutor-notification Lambda (see async.tf).
resource "aws_s3_bucket_notification" "submissions" {
  bucket      = aws_s3_bucket.submissions.id
  eventbridge = true
}
