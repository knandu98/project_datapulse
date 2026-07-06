# OPTIONAL: manage GitHub repository settings as code. Disabled by default; flip
# enable_github_provider = true and provide a token to use it. Tokens must come
# from the environment (TF_VAR_github_token) or tfvars that are never committed.

provider "github" {
  token = var.enable_github_provider ? var.github_token : null
  owner = var.enable_github_provider ? var.github_owner : null
}

# Example: ensure GitHub Actions stays enabled and the default branch is protected.
resource "github_actions_repository_permissions" "this" {
  count           = var.enable_github_provider ? 1 : 0
  repository      = var.github_repository
  enabled         = true
  allowed_actions = "all"
}
