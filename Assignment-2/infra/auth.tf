resource "aws_cognito_user_pool" "main" {
  name = "${var.project}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = { Name = "${var.project}-user-pool" }
}

resource "aws_cognito_user_group" "student" {
  name         = "student"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Sits timed exams, uploads assignments"
  precedence   = 30
}

resource "aws_cognito_user_group" "tutor" {
  name         = "tutor"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Creates exams, marks and releases results"
  precedence   = 20
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Manages users and schedules"
  precedence   = 10
}

resource "aws_cognito_user_pool_client" "spa" {
  name         = "${var.project}-spa-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret               = false # SPA (public client): browser can't keep a secret
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  access_token_validity         = 1
  id_token_validity             = 1
  refresh_token_validity        = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project}-${local.account_suffix}"
  user_pool_id = aws_cognito_user_pool.main.id
}
