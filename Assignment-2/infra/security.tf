resource "aws_security_group" "lambda" {
  name_prefix = "${var.project}-lambda-"
  description = "Lambda functions running in the VPC (API handlers + async workers)"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "All outbound (RDS Proxy, S3 endpoint, Secrets Manager endpoint, NAT for SES/Cognito)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-lambda-sg" }
}

resource "aws_security_group" "rds_proxy" {
  name_prefix = "${var.project}-rds-proxy-"
  description = "RDS Proxy sitting between Lambda and Aurora"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Lambda -> RDS Proxy"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-rds-proxy-sg" }
}

resource "aws_security_group" "aurora" {
  name_prefix = "${var.project}-aurora-"
  description = "Aurora Serverless v2 cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "RDS Proxy -> Aurora"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.rds_proxy.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-aurora-sg" }
}
