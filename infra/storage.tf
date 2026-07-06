# Two-bucket data lake: raw snapshots + processed Parquet. Versioning is enabled
# on both so the storage layer mirrors the project's "observability/history" theme.

resource "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket_name
}

resource "aws_s3_bucket" "processed" {
  bucket = var.processed_bucket_name
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "processed" {
  bucket = aws_s3_bucket.processed.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Optional lifecycle rule: expire old raw snapshots to keep the lake tidy.
# Applied only on real AWS — LocalStack's community S3 does not support the
# lifecycle-configuration read-back the provider waits on, so we skip it there.
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  count  = (!var.use_localstack && var.expire_raw_after_days > 0) ? 1 : 0
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "expire-old-raw-snapshots"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    expiration {
      days = var.expire_raw_after_days
    }
  }
}
