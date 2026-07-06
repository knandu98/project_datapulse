# DataPulse Infrastructure (Terraform)

This module provisions the S3-compatible **data lake** for DataPulse using a single
codebase that targets **LocalStack** (free, offline) by default or **real AWS**
when you flip one flag. The Python pipeline never hardcodes bucket names or
endpoints — it reads them from `terraform output -json`.

## Resources

- `aws_s3_bucket.raw` — raw API snapshots (`raw/<timestamp>.json`)
- `aws_s3_bucket.processed` — processed Parquet data lake (`processed/...`)
- `aws_s3_bucket_versioning` on both (history/observability theme)
- `aws_s3_bucket_lifecycle_configuration.raw` — optional expiry of old snapshots
- `infra/github.tf` — optional GitHub repo management (disabled by default)

## Outputs

| output | meaning |
|---|---|
| `raw_bucket` | raw snapshot bucket name |
| `processed_bucket` | processed Parquet bucket name |
| `s3_endpoint` | endpoint the pipeline uses (empty = default AWS) |
| `aws_region` | bucket region |
| `use_localstack` | whether LocalStack backs the lake |

## Usage — LocalStack (default, free)

Start LocalStack first (from the repo root):

```bash
docker compose up -d localstack
```

Then plan/apply:

```bash
terraform -chdir=infra init
terraform -chdir=infra plan
terraform -chdir=infra apply -auto-approve
terraform -chdir=infra output
```

`make infra-up` does all of the above for you.

## Usage — real AWS (opt-in, may incur cost)

Set `use_localstack=false` and supply real credentials via the standard AWS
environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`):

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
terraform -chdir=infra apply -auto-approve -var "use_localstack=false"
```

> ⚠️ Real AWS S3 buckets and stored objects can incur charges. The LocalStack
> path is recommended for development and CI.

## Optional: manage GitHub settings with Terraform

```bash
export TF_VAR_github_token=ghp_xxx
terraform -chdir=infra apply \
  -var "enable_github_provider=true" \
  -var "github_owner=your-user" \
  -var "github_repository=project_datapulse"
```

## Formatting & validation

```bash
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
```
