resource "aws_kms_key" "main" {
  description             = "${var.project} customer-managed key for S3, Aurora, Secrets Manager, CloudWatch Logs"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = { Name = "${var.project}-key" }
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.project}-key"
  target_key_id = aws_kms_key.main.key_id
}

resource "random_password" "db_master" {
  length  = 32
  special = false # Aurora username/password secret must avoid '/', '@', '"', space; keep it simple
}

resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.project}/${var.environment}/db-credentials"
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = 7
  tags                    = { Name = "${var.project}-db-secret" }
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_master_username
    password = random_password.db_master.result
    engine   = "postgres"
    host     = aws_rds_cluster.main.endpoint
    port     = 5432
    dbname   = var.db_name
  })
}


# Automatic 30-day rotation is enabled by deploying AWS's maintained rotation
# function from the Serverless Application Repository, rather than hand-
# rolling rotation logic here:
#   aws serverlessrepo create-cloud-formation-change-set \
#     --application-id arn:aws:serverlessrepo:us-east-1:297356227824:applications/SecretsManagerRDSPostgreSQLRotationSingleUser \
#     --stack-name eduexam-db-rotation \
#     --parameter-overrides Name=endpoint,Value=secretsmanager.${var.aws_region}.amazonaws.com Name=functionName,Value=${var.project}-db-rotation Name=vpcSubnetIds=... Name=vpcSecurityGroupIds=...
# then point aws_secretsmanager_secret_rotation.db.rotation_lambda_arn at
# the deployed function's ARN. Left as a documented manual step so this
# module stays self-contained for `terraform apply` without SAR access.
