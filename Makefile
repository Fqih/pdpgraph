.DEFAULT_GOAL := help
.PHONY: help sync lint fmt test test-int eval-smoke up down up-llm up-mock up-obs ingest

UV := uv run --frozen

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

test: ## Unit + property + contract tests
	$(UV) pytest

test-int: ## Integration tests (needs `make up`)
	$(UV) pytest -m integration

# Targets below land in later roadmap tasks; they fail loudly until then.
up down up-llm: ## Compose profiles (M0.2 / M0.4)
	@echo "make $@: lands in M0.2 (core) / M0.4 (local-llm)" >&2; exit 1

up-mock up-obs: ## Compose profiles (M2.9)
	@echo "make $@: lands in M2.9" >&2; exit 1

eval-smoke: ## 30-item replay eval (M1.16)
	@echo "make $@: lands in M1.16" >&2; exit 1

ingest: ## Ingest a source, e.g. make ingest SOURCE=uu27-2022 (M1.1)
	@echo "make $@: lands in M1.1" >&2; exit 1
