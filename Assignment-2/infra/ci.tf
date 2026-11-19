# GitHub Actions deploys via OIDC federation — no long-lived AWS access keys
# stored in GitHub. This creates the trust relationship; .github/workflows/
# deploy.yml assumes aws_iam_role.github_actions.arn.

data "tls_certificate" "github" {
  count = var.github_repo != "" ? 1 : 0
  url   = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.github_repo != "" ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github[0].certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "github_actions" {
  count = var.github_repo != "" ? 1 : 0
  name  = "${var.project}-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github[0].arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })

  tags = { Name = "${var.project}-github-actions-role" }
}

# Scoped to what the pipeline actually needs to do: run Terraform, push
# Lambda code, sync the frontend bucket, invalidate CloudFront. Not
# AdministratorAccess.
resource "aws_iam_role_policy" "github_actions" {
  count = var.github_repo != "" ? 1 : 0
  name  = "${var.project}-github-actions-deploy"
  role  = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "TerraformState"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = ["*"] # scope to your remote state bucket/key once backend.tf is switched from local
      },
      {
        Sid    = "DeployBroad"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:UpdateFunctionConfiguration",
          "s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject",
          "cloudfront:CreateInvalidation", "cloudfront:GetInvalidation",
        ]
        Resource = ["*"]
      },
      {
        Sid      = "TerraformManage"
        Effect   = "Allow"
        Action   = ["ec2:*", "rds:*", "apigateway:*", "iam:*", "kms:*", "secretsmanager:*", "sqs:*", "events:*", "cloudwatch:*", "cloudfront:*", "wafv2:*", "route53:*", "acm:*", "cognito-idp:*", "cloudtrail:*", "logs:*", "sns:*", "s3:*"]
        Resource = ["*"]
      }
    ]
  })
}
