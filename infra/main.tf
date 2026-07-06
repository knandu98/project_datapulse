terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

locals {
  # When targeting LocalStack we use dummy credentials and skip every online
  # validation so `terraform apply` runs fully offline and free.
  endpoints = var.use_localstack ? { s3 = var.localstack_endpoint } : {}
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = var.use_localstack ? "test" : null
  secret_key                  = var.use_localstack ? "test" : null
  skip_credentials_validation = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_region_validation      = var.use_localstack
  # LocalStack needs path-style addressing (bucket in the path, not the host).
  s3_use_path_style = var.use_localstack

  dynamic "endpoints" {
    for_each = local.endpoints
    content {
      s3 = endpoints.value
    }
  }
}
