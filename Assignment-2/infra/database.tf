resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${var.project}-db-subnets" }
}

# Aurora Serverless v2 cluster: writer in AZ-A, reader in AZ-B. Aurora's
# storage layer itself replicates across (up to) 3 AZs beneath this, so a
# single-AZ loss triggers automatic failover to the surviving instance.
resource "aws_rds_cluster" "main" {
  cluster_identifier     = "${var.project}-${var.environment}"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  engine_version         = "15.4"
  database_name          = var.db_name
  master_username        = var.db_master_username
  master_password        = random_password.db_master.result
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  storage_encrypted = true
  kms_key_id        = aws_kms_key.main.arn

  backup_retention_period   = 35
  preferred_backup_window   = "03:00-04:00"
  copy_tags_to_snapshot     = true
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.project}-final-snapshot" : null

  enabled_cloudwatch_logs_exports = ["postgresql"]

  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_capacity
    max_capacity = var.aurora_max_capacity
  }

  tags = { Name = "${var.project}-aurora" }
}

# Writer instance — Availability Zone A
resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.project}-${var.environment}-writer"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version
  availability_zone  = var.availability_zones[0]
  promotion_tier     = 0

  tags = { Name = "${var.project}-aurora-writer", AZ = "AZ-A" }
}

# Reader instance — Availability Zone B. Aurora promotes this automatically
# if the writer's AZ is lost.
resource "aws_rds_cluster_instance" "reader" {
  identifier         = "${var.project}-${var.environment}-reader"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version
  availability_zone  = var.availability_zones[1]
  promotion_tier     = 1

  tags = { Name = "${var.project}-aurora-reader", AZ = "AZ-B" }
}

resource "aws_iam_role" "rds_proxy" {
  name = "${var.project}-rds-proxy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "rds.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "rds_proxy_secrets" {
  name = "${var.project}-rds-proxy-secrets"
  role = aws_iam_role.rds_proxy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.db.arn]
    }]
  })
}

# RDS Proxy pools bursty Lambda connections into a small, stable set against
# Aurora — without this, thousands of concurrent exam-start Lambda
# executions would exhaust max_connections directly against the database.
resource "aws_db_proxy" "main" {
  name                   = "${var.project}-rds-proxy"
  engine_family          = "POSTGRESQL"
  role_arn               = aws_iam_role.rds_proxy.arn
  vpc_subnet_ids         = aws_subnet.private[*].id
  vpc_security_group_ids = [aws_security_group.rds_proxy.id]
  require_tls            = true

  auth {
    auth_scheme = "SECRETS"
    secret_arn  = aws_secretsmanager_secret.db.arn
    iam_auth    = "DISABLED"
  }

  tags = { Name = "${var.project}-rds-proxy" }
}

resource "aws_db_proxy_default_target_group" "main" {
  db_proxy_name = aws_db_proxy.main.name

  connection_pool_config {
    max_connections_percent      = 90
    max_idle_connections_percent = 50
  }
}

resource "aws_db_proxy_target" "main" {
  db_proxy_name         = aws_db_proxy.main.name
  target_group_name     = aws_db_proxy_default_target_group.main.name
  db_cluster_identifier = aws_rds_cluster.main.id
}
