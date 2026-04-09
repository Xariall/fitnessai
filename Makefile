.PHONY: help install dev dev-api dev-frontend build up down logs migrate seed

# ── Default target ─────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "FitAgent — available commands"
	@echo ""
	@echo "  Local development"
	@echo "  -----------------"
	@echo "  make install       Install all dependencies (Python + Node)"
	@echo "  make dev           Start both servers concurrently"
	@echo "  make dev-api       Start only the Python FastAPI backend  (port 8000)"
	@echo "  make dev-frontend  Start only the React/tRPC frontend     (port 3000)"
	@echo "  make migrate       Run Alembic DB migrations"
	@echo "  make seed          Seed exercises + food products"
	@echo ""
	@echo "  Docker"
	@echo "  ------"
	@echo "  make build         Build all Docker images"
	@echo "  make up            Start all services with Docker Compose"
	@echo "  make down          Stop all services"
	@echo "  make logs          Follow logs for all services"
	@echo ""

# ── Local development ──────────────────────────────────────────────────────────
install:
	@echo "→ Installing Python dependencies…"
	pip install -r requirements.txt
	@echo "→ Installing Node dependencies (fitagentfront)…"
	cd fitagentfront && pnpm install

dev:
	@command -v concurrently >/dev/null 2>&1 || npm install -g concurrently
	concurrently \
		--names "api,frontend" \
		--prefix-colors "cyan,magenta" \
		"make dev-api" \
		"make dev-frontend"

dev-api:
	fastapi dev api/main.py --port 8000

dev-frontend:
	cd fitagentfront && pnpm dev

migrate:
	alembic upgrade head

seed:
	python -m database.seed

# ── Docker ─────────────────────────────────────────────────────────────────────
build:
	docker compose build

up:
	docker compose up -d
	@echo ""
	@echo "  FastAPI  → http://localhost:8000"
	@echo "  Frontend → http://localhost:3000"
	@echo ""

down:
	docker compose down

logs:
	docker compose logs -f
