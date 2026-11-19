locals {
  # One Lambda per responsibility, each with its own IAM role (least
  # privilege) per docs/services.md. api/* are invoked by API Gateway;
  # workers/* are invoked by SQS or EventBridge (wired up in async.tf).
  lambda_functions = {
    open-exam = {
      source_dir = "${path.module}/../app/api/open_exam"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["secretsmanager:GetSecretValue"], resources = [aws_secretsmanager_secret.db.arn] },
      ]
    }
    autosave = {
      source_dir = "${path.module}/../app/api/autosave"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["secretsmanager:GetSecretValue"], resources = [aws_secretsmanager_secret.db.arn] },
      ]
    }
    presign-upload = {
      source_dir = "${path.module}/../app/api/presign_upload"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["s3:PutObject"], resources = ["${aws_s3_bucket.submissions.arn}/*"] },
      ]
    }
    release-results = {
      source_dir = "${path.module}/../app/api/release_results"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["secretsmanager:GetSecretValue"], resources = [aws_secretsmanager_secret.db.arn] },
        { actions = ["sqs:SendMessage"], resources = [aws_sqs_queue.email.arn] },
      ]
    }
    submit-exam = {
      source_dir = "${path.module}/../app/api/submit_exam"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["secretsmanager:GetSecretValue"], resources = [aws_secretsmanager_secret.db.arn] },
        { actions = ["sqs:SendMessage"], resources = [aws_sqs_queue.marking.arn] },
      ]
    }
    automark = {
      source_dir = "${path.module}/../app/workers/automark"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["secretsmanager:GetSecretValue"], resources = [aws_secretsmanager_secret.db.arn] },
      ]
    }
    notify-tutor = {
      source_dir = "${path.module}/../app/workers/notify_tutor"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["secretsmanager:GetSecretValue"], resources = [aws_secretsmanager_secret.db.arn] },
        { actions = ["sqs:SendMessage"], resources = [aws_sqs_queue.email.arn] },
        { actions = ["s3:GetObject"], resources = ["${aws_s3_bucket.submissions.arn}/*"] },
      ]
    }
    send-email = {
      source_dir = "${path.module}/../app/workers/send_email"
      handler    = "index.handler"
      extra_statements = [
        { actions = ["ses:SendEmail", "ses:SendRawEmail"], resources = ["*"] },
      ]
    }
  }
}

data "archive_file" "lambda" {
  for_each    = local.lambda_functions
  type        = "zip"
  source_dir  = each.value.source_dir
  output_path = "${path.module}/.build/${each.key}.zip"
}

resource "aws_iam_role" "lambda" {
  for_each = local.lambda_functions
  name     = "${var.project}-${each.key}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  for_each   = local.lambda_functions
  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "lambda_rds_proxy_connect" {
  for_each = local.lambda_functions
  name     = "${var.project}-${each.key}-rds-connect"
  role     = aws_iam_role.lambda[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["rds-db:connect"]
      Resource = ["${aws_db_proxy.main.arn}/*"]
    }]
  })
}

resource "aws_iam_role_policy" "lambda_extra" {
  for_each = local.lambda_functions
  name     = "${var.project}-${each.key}-extra"
  role     = aws_iam_role.lambda[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [for s in each.value.extra_statements : {
      Effect   = "Allow"
      Action   = s.actions
      Resource = s.resources
    }]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambda_functions
  name              = "/aws/lambda/${var.project}-${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_lambda_function" "fn" {
  for_each         = local.lambda_functions
  function_name    = "${var.project}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  handler          = each.value.handler
  runtime          = "nodejs20.x"
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_s

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      DB_SECRET_ARN      = aws_secretsmanager_secret.db.arn
      DB_PROXY_ENDPOINT  = aws_db_proxy.main.endpoint
      SUBMISSIONS_BUCKET = aws_s3_bucket.submissions.bucket
      EMAIL_QUEUE_URL    = aws_sqs_queue.email.url
      MARKING_QUEUE_URL  = aws_sqs_queue.marking.url
      SES_FROM_ADDRESS   = "no-reply@${var.domain_name != "" ? var.domain_name : "example.com"}"
    }
  }

  tags = { Name = "${var.project}-${each.key}" }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# Convenience references used elsewhere (async.tf, api.tf) so those files
# don't need to know about the for_each map directly.
locals {
  lambda_arn = { for k, f in aws_lambda_function.fn : k => f.arn }
}

output "lambda_function_names" {
  value = { for k, f in aws_lambda_function.fn : k => f.function_name }
}
