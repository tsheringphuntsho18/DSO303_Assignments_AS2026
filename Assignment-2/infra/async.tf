# --- Marking queue: decouples MCQ auto-marking from the submit request ---
resource "aws_sqs_queue" "marking_dlq" {
  name                      = "${var.project}-marking-dlq"
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = aws_kms_key.main.id
  tags                      = { Name = "${var.project}-marking-dlq" }
}

resource "aws_sqs_queue" "marking" {
  name                       = "${var.project}-marking-queue"
  visibility_timeout_seconds = 60
  kms_master_key_id          = aws_kms_key.main.id

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.marking_dlq.arn
    maxReceiveCount     = 5
  })

  tags = { Name = "${var.project}-marking-queue" }
}

# --- Email queue: decouples "results released" / "submission received" emails ---
resource "aws_sqs_queue" "email_dlq" {
  name                      = "${var.project}-email-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.main.id
  tags                      = { Name = "${var.project}-email-dlq" }
}

resource "aws_sqs_queue" "email" {
  name                       = "${var.project}-email-queue"
  visibility_timeout_seconds = 60
  kms_master_key_id          = aws_kms_key.main.id

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.email_dlq.arn
    maxReceiveCount     = 5
  })

  tags = { Name = "${var.project}-email-queue" }
}

resource "aws_lambda_event_source_mapping" "marking" {
  event_source_arn = aws_sqs_queue.marking.arn
  function_name    = aws_lambda_function.fn["automark"].arn
  batch_size       = 5
}

resource "aws_lambda_event_source_mapping" "email" {
  event_source_arn = aws_sqs_queue.email.arn
  function_name    = aws_lambda_function.fn["send-email"].arn
  batch_size       = 5
}

# --- EventBridge: S3 "new submission" -> notify-tutor Lambda ---
resource "aws_cloudwatch_event_rule" "new_submission" {
  name = "${var.project}-new-submission"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.submissions.bucket] }
    }
  })

  tags = { Name = "${var.project}-new-submission-rule" }
}

resource "aws_cloudwatch_event_target" "notify_tutor" {
  rule      = aws_cloudwatch_event_rule.new_submission.name
  target_id = "notify-tutor-lambda"
  arn       = aws_lambda_function.fn["notify-tutor"].arn
}

resource "aws_lambda_permission" "eventbridge_notify_tutor" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn["notify-tutor"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.new_submission.arn
}
