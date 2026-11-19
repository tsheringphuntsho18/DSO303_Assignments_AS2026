variable "project" {
  description = "Short name prefixed onto every resource"
  type        = string
  default     = "eduexam"
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "Primary AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Two AZs the architecture spans"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "single_nat_gateway" {
  description = "Use 1 NAT Gateway instead of 2 (cheaper for dev/testing; breaks AZ-independent egress — keep false for grading the AZ-failure scenario)"
  type        = bool
  default     = false
}

variable "domain_name" {
  description = "Public domain name for the platform, e.g. eduexam.example.com. Leave blank to skip Route 53 + ACM + custom domain and use the default CloudFront/API Gateway URLs instead."
  type        = string
  default     = ""
}

variable "hosted_zone_id" {
  description = "Existing Route 53 hosted zone ID for domain_name (required only if domain_name is set)"
  type        = string
  default     = ""
}

variable "aurora_min_capacity" {
  description = "Aurora Serverless v2 minimum ACUs"
  type        = number
  default     = 0.5
}

variable "aurora_max_capacity" {
  description = "Aurora Serverless v2 maximum ACUs"
  type        = number
  default     = 4
}

variable "db_name" {
  type    = string
  default = "eduexam"
}

variable "db_master_username" {
  type    = string
  default = "eduexam_admin"
}

variable "lambda_memory_mb" {
  type    = number
  default = 256
}

variable "lambda_timeout_s" {
  type    = number
  default = 15
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "submission_retention_days" {
  description = "How long assignment submissions are kept before expiry (5 years = 1825 days, per records-retention target)"
  type        = number
  default     = 1825
}

variable "alarm_email" {
  description = "Email address subscribed to CloudWatch/operational alarms (optional)"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repo in 'org/name' form, used to scope the OIDC deploy role trust policy"
  type        = string
  default     = ""
}
