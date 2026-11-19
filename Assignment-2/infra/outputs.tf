output "cloudfront_domain" {
  description = "Default CloudFront URL (use this if domain_name was left blank)"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "site_url" {
  description = "Public URL of the platform"
  value       = local.use_custom_domain ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "api_invoke_url" {
  description = "Direct API Gateway URL (bypasses CloudFront — useful for debugging / health checks)"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_app_client_id" {
  value = aws_cognito_user_pool_client.spa.id
}

output "aurora_cluster_endpoint" {
  value = aws_rds_cluster.main.endpoint
}

output "rds_proxy_endpoint" {
  value = aws_db_proxy.main.endpoint
}

output "submissions_bucket" {
  value = aws_s3_bucket.submissions.bucket
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "github_actions_role_arn" {
  description = "Set this as the AWS_ROLE_ARN GitHub Actions secret/variable"
  value       = var.github_repo != "" ? aws_iam_role.github_actions[0].arn : "set var.github_repo to create this role"
}

output "dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}
