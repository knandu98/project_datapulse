variable "use_localstack" {
  description = "Target LocalStack (true, free/offline) or real AWS (false, may cost money)."
  type        = bool
  default     = true
}

variable "aws_region" {
  description = "AWS region for the data lake buckets."
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "S3 endpoint used when use_localstack = true."
  type        = string
  default     = "http://localhost:4566"
}

variable "raw_bucket_name" {
  description = "Bucket holding raw API snapshots."
  type        = string
  default     = "datapulse-raw"
}

variable "processed_bucket_name" {
  description = "Bucket holding the processed Parquet data lake."
  type        = string
  default     = "datapulse-processed"
}

variable "expire_raw_after_days" {
  description = "Expire raw snapshots after this many days (0 disables the rule)."
  type        = number
  default     = 30
}

# --- Optional GitHub provider (IaC beyond cloud), gated + off by default --------
variable "enable_github_provider" {
  description = "Manage GitHub repo settings via Terraform. Requires github_token + github_owner."
  type        = bool
  default     = false
}

variable "github_token" {
  description = "GitHub token (only used when enable_github_provider = true)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_owner" {
  description = "GitHub owner/org (only used when enable_github_provider = true)."
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "Repository name to manage (only used when enable_github_provider = true)."
  type        = string
  default     = ""
}
