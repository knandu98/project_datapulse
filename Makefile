.DEFAULT_GOAL := help
SHELL := /bin/bash

# Allow `make infra-up` etc. to target real AWS by exporting USE_LOCALSTACK=false
USE_LOCALSTACK ?= true
PY ?= python

.PHONY: help setup infra-up infra-down run dashboard test lint fmt clean

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python deps and verify Terraform + Docker are available.
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	@command -v terraform >/dev/null 2>&1 && terraform version | head -1 || \
		echo "WARNING: terraform not found on PATH (needed for 'make infra-up')."
	@command -v docker >/dev/null 2>&1 && docker --version || \
		echo "WARNING: docker not found on PATH (needed for LocalStack)."
	@echo "Setup complete."

infra-up: ## Start LocalStack (if needed) and apply Terraform to create the lake.
	@if [ "$(USE_LOCALSTACK)" = "true" ]; then \
		echo "Starting LocalStack..."; \
		docker compose up -d localstack; \
		echo "Waiting for LocalStack to be ready..."; \
		for i in $$(seq 1 30); do \
			curl -sf http://localhost:4566/_localstack/health >/dev/null && break; \
			sleep 2; \
		done; \
	fi
	terraform -chdir=infra init -input=false
	terraform -chdir=infra apply -auto-approve -input=false -var "use_localstack=$(USE_LOCALSTACK)"
	@echo "Infrastructure ready. Outputs:"
	@terraform -chdir=infra output

infra-down: ## Destroy Terraform resources and stop LocalStack.
	-terraform -chdir=infra destroy -auto-approve -input=false -var "use_localstack=$(USE_LOCALSTACK)"
	@if [ "$(USE_LOCALSTACK)" = "true" ]; then docker compose down -v; fi

run: ## Execute the full pipeline once (idempotent).
	$(PY) -m datapulse.pipeline run

dashboard: ## Launch the Streamlit dashboard.
	streamlit run dashboard/app.py

test: ## Run the test suite.
	$(PY) -m pytest

lint: ## Lint with ruff.
	ruff check .

fmt: ## Auto-format with ruff and terraform fmt.
	ruff check --fix .
	ruff format .
	terraform -chdir=infra fmt

clean: ## Remove caches and local data artifacts.
	rm -rf .pytest_cache .ruff_cache **/__pycache__
	rm -f data/datapulse.duckdb
	find data/raw data/processed -type f ! -name '.gitkeep' -delete 2>/dev/null || true
