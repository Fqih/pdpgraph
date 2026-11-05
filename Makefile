.DEFAULT_GOAL := help
.PHONY: help sync lint fmt check test cov migrate test-int eval-smoke eval-record up down up-llm up-mock up-obs ingest

UV := uv run --frozen
COMPOSE := docker compose --project-directory . -f deploy/compose/compose.yaml

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

sync: ## Install all workspace packages + dev tools
	uv sync --all-packages --frozen

lint: ## ruff (lint + format check) + mypy
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) mypy

fmt: ## Apply ruff fixes and formatting
	$(UV) ruff check --fix .
	$(UV) ruff format .

check: ## All pre-commit hooks on all files (run before every commit; CI enforces)
	$(UV) pre-commit run --all-files

test: ## Unit + property + contract tests
	$(UV) pytest

cov: ## Tests + branch coverage gate on deterministic modules (NFR-10: >= 80%)
	$(UV) pytest --cov=common --cov-branch --cov-report=term-missing --cov-fail-under=80

test-int: ## Integration tests (needs `make up`)
	$(UV) pytest -m integration

up: .env ## Start the core stores (neo4j, opensearch, postgres, valkey) and wait until healthy
	$(COMPOSE) --profile core up -d --wait --wait-timeout 300

down: ## Stop every profile and remove project volumes (compose down -v)
	$(COMPOSE) --profile '*' down -v --remove-orphans

migrate: .env ## Apply Postgres migrations (idempotent; needs `make up`)
	$(UV) alembic upgrade head

.env:
	@echo "Missing .env: cp .env.example .env and set local passwords" >&2; exit 1

# Targets below land in later roadmap tasks; they fail loudly until then.
up-llm: ## Compose local-llm profile (M0.4)
	@echo "make $@: lands in M0.4" >&2; exit 1

up-mock up-obs: ## Compose profiles (M2.9)
	@echo "make $@: lands in M2.9" >&2; exit 1

eval-smoke: ## 30-item replay eval (M1.16)
	@echo "make $@: lands in M1.16" >&2; exit 1

eval-record: ## Re-record LLM cassettes (M1.16; until then run with LLM_MODE=record)
	@echo "make $@: lands in M1.16" >&2; exit 1

ingest: ## Ingest a source, e.g. make ingest SOURCE=uu27-2022 (M1.1)
	@echo "make $@: lands in M1.1" >&2; exit 1
