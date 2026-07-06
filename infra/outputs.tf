output "raw_bucket" {
  description = "Name of the raw snapshot bucket."
  value       = aws_s3_bucket.raw.id
}

output "processed_bucket" {
  description = "Name of the processed Parquet data lake bucket."
  value       = aws_s3_bucket.processed.id
}

output "s3_endpoint" {
  description = "S3 endpoint the pipeline should use (LocalStack or real AWS)."
  value       = var.use_localstack ? var.localstack_endpoint : ""
}

output "aws_region" {
  description = "Region for the buckets."
  value       = var.aws_region
}

output "use_localstack" {
  description = "Whether the lake is backed by LocalStack."
  value       = var.use_localstack
}
