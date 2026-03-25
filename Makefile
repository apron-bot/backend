.PHONY: setup run dev test lint webhook help

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PORT ?= 8000

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Full setup: venv, deps, env file
	@echo "Creating virtual environment..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — fill in your API keys"; \
	else \
		echo ".env already exists, skipping"; \
	fi
	@echo ""
	@echo "Done! Next steps:"
	@echo "  1. Edit .env with your API keys (at minimum TELEGRAM_BOT_TOKEN and one LLM key)"
	@echo "  2. Run: make dev"
	@echo "  3. Set up Telegram webhook: make webhook PUBLIC_URL=https://your-url.com"

run: ## Start production server
	$(PYTHON) -m uvicorn apron.main:app --host 0.0.0.0 --port $(PORT)

dev: ## Start dev server with auto-reload
	$(PYTHON) -m uvicorn apron.main:app --reload --host 0.0.0.0 --port $(PORT)

test: ## Run tests
	$(PYTHON) -m pytest -v

lint: ## Run linter
	$(PYTHON) -m ruff check src/ tests/

webhook: ## Set Telegram webhook (requires PUBLIC_URL env var or arg)
ifndef PUBLIC_URL
	$(error PUBLIC_URL is required. Usage: make webhook PUBLIC_URL=https://your-domain.com)
endif
	@curl -s "https://api.telegram.org/bot$$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)/setWebhook?url=$(PUBLIC_URL)/webhook/telegram" | python3 -m json.tool
	@echo ""
	@echo "Webhook set to $(PUBLIC_URL)/webhook/telegram"

webhook-info: ## Check current Telegram webhook status
	@curl -s "https://api.telegram.org/bot$$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)/getWebhookInfo" | python3 -m json.tool

webhook-delete: ## Remove Telegram webhook (for local polling)
	@curl -s "https://api.telegram.org/bot$$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)/deleteWebhook" | python3 -m json.tool
