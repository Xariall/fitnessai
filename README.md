# FitAgent — AI Fitness Trainer

An AI-powered fitness and nutrition assistant built with LangGraph, Gemini 2.5, and a React frontend.

---

## Architecture

```
Browser
  └── fitagentfront  (React 19 + tRPC, port 3000)
        └── FastAPI  (port 8000)
              ├── Google OAuth 2.0
              ├── LangGraph Agent + Gemini Flash
              ├── MCP Servers  (fitness_mcp · nutrition_mcp)
              └── PostgreSQL   (users · conversations · workouts · nutrition)
```

### Services (Docker Compose)

| Service | Image | Port | Role |
|---------|-------|------|------|
| `db` | `pgvector/pgvector:pg16` | 5433 | PostgreSQL 16 |
| `api` | Python 3.11 | 8000 | FastAPI — agent + auth + data API |
| `frontend` | Node 20 | 3000 | React SPA + Express BFF |

---

## Quick Start (Docker)

### 1. Prerequisites

- Docker Desktop ≥ 4.x
- A Google Cloud project with OAuth 2.0 credentials
- A Gemini API key — [aistudio.google.com](https://aistudio.google.com/apikey)

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in GEMINI_API_KEY, GOOGLE_CLIENT_ID,
#   GOOGLE_CLIENT_SECRET, JWT_SECRET
```

**Required `.env` values:**

| Variable | Where to get it |
|----------|----------------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GOOGLE_CLIENT_ID` | [GCP Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials) |
| `GOOGLE_CLIENT_SECRET` | Same as above |
| `JWT_SECRET` | `openssl rand -hex 32` |

**Google OAuth callback URI** (add to your GCP OAuth client):
```
http://localhost:8000/api/auth/callback
```

### 3. Build and run

```bash
docker compose up --build -d
```

### 4. Verify

```bash
docker compose ps          # all three services Up
curl http://localhost:8000/api/health   # {"status":"ok"}
```

Open **http://localhost:3000** in your browser.

---

## Deploy to Vercel (Frontend)

> **Why only the frontend?**
> The FastAPI backend runs a stateful LangGraph agent with MCP server connections and ChromaDB.
> Vercel's serverless functions have a 60 s timeout and no persistent process — not suitable
> for long-running AI calls. Deploy FastAPI separately (Railway, Render, or fly.io).

### Architecture on Vercel

```
Vercel CDN  →  dist/public/     (React SPA — static)
Vercel Fn   →  api/index.ts     (Express: tRPC + OAuth routes)
                   ↓
          FastAPI on Railway / Render / fly.io
                   ↓
             PostgreSQL (Neon / Supabase / Railway)
```

### 1. Deploy FastAPI first

Choose a platform that supports Docker or Python:

```bash
# Example: Railway
railway up          # from the project root (uses Dockerfile + entrypoint.sh)

# After deploy, note your service URL, e.g.:
# https://fitnessai-api.railway.app
```

Update your **Google OAuth credentials** — add the new callback URI:
```
https://fitnessai-api.railway.app/api/auth/callback
```

### 2. Import fitagentfront to Vercel

```bash
# Install Vercel CLI (once)
npm i -g vercel

cd fitagentfront
vercel
```

Or connect via [vercel.com/new](https://vercel.com/new) → import the repo,
set **Root Directory** to `fitagentfront`.

Vercel auto-detects `vercel.json` and runs `pnpm run build:client`.

### 3. Set environment variables in Vercel dashboard

Go to **Project → Settings → Environment Variables** and add:

| Variable | Value |
|----------|-------|
| `FASTAPI_URL` | `https://your-api.railway.app` |
| `FASTAPI_BASE_URL` | `https://your-api.railway.app` |
| `JWT_SECRET` | same value as the FastAPI `JWT_SECRET` |
| `FRONTEND_URL` | `https://your-app.vercel.app` |

> `NODE_ENV` is set to `production` automatically by Vercel.

### 4. Update FastAPI environment

Add to your backend deployment (Railway/Render):

```
FRONTEND_URL=https://your-app.vercel.app
ALLOWED_ORIGINS=https://your-app.vercel.app
```

Also add the Google OAuth callback:
```
https://your-api.railway.app/api/auth/callback
```

---

## Local Development (without Docker)

### FastAPI

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL separately (e.g. via Docker):
docker run -d --name pg -p 5433:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=changeme \
  -e POSTGRES_DB=fitness_ai pgvector/pgvector:pg16

# Apply migrations and start
alembic upgrade head
fastapi dev api/main.py
```

### Frontend

```bash
cd fitagentfront
pnpm install
pnpm dev          # http://localhost:3000
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash-lite` | Model name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASS` | `changeme` | PostgreSQL password |
| `DB_NAME` | `fitness_ai` | Database name |
| `DATABASE_URL` | — | Full asyncpg connection string |
| `GOOGLE_CLIENT_ID` | — | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | — | OAuth 2.0 client secret |
| `JWT_SECRET` | — | HS256 signing secret (min 32 chars) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | CORS allowed origins |
| `FASTAPI_URL` | `http://localhost:8000` | Internal server→server URL |
| `FASTAPI_BASE_URL` | `http://localhost:8000` | Public URL for OAuth redirects |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL (OAuth final redirect) |

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/auth/google` | Start Google OAuth flow |
| `GET` | `/api/auth/callback` | OAuth callback → sets JWT cookie |
| `GET` | `/api/auth/me` | Get current user |
| `POST` | `/api/auth/logout` | Clear session cookie |

### Conversations & Chat
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/conversations` | Create new conversation |
| `GET` | `/api/conversations` | List user's conversations |
| `GET` | `/api/conversations/{id}/messages` | Get messages |
| `POST` | `/api/conversations/{id}/chat` | Send text message to agent |
| `POST` | `/api/conversations/{id}/chat/image` | Send food photo to agent |

### Profile & Waitlist
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/profile` | Get user profile |
| `PUT` | `/api/profile` | Update fitness profile |
| `POST` | `/api/waitlist` | Join waitlist |
| `GET` | `/api/health` | Health check |

---

## Project Structure

```
fitnessai/
├── api/                  # FastAPI routes
│   ├── auth.py           # Google OAuth + JWT
│   ├── main.py           # App factory + all endpoints
│   └── schemas.py        # Pydantic request/response models
├── agent/                # LangGraph agent
│   ├── graph.py          # Compiled graph with memory
│   └── prompts.py        # System prompt
├── database/             # SQLAlchemy ORM
│   ├── models.py         # All table models
│   ├── engine.py         # Async engine + session factory
│   ├── db.py             # CRUD helpers
│   └── seed.py           # Initial exercises & food products
├── migrations/           # Alembic migrations
├── mcp_servers/          # FastMCP tool servers
│   ├── fitness_mcp.py    # Workout & weight tools
│   └── nutrition_mcp.py  # Food diary & nutrition tools
├── scripts/
│   └── migrate.py        # Smart migration runner
├── fitagentfront/        # React + tRPC frontend
│   ├── client/src/       # React SPA
│   └── server/           # Express BFF + tRPC router
├── Dockerfile            # Python image (api)
├── entrypoint.sh         # migrate → fastapi run
├── docker-compose.yml
└── .env.example
```

---

## Useful Commands

```bash
# Logs
docker compose logs -f api
docker compose logs -f frontend

# Restart a single service
docker compose restart api

# Full reset (wipes DB volume)
docker compose down -v && docker compose up --build -d

# Run migrations manually
docker compose exec api alembic upgrade head

# Open DB shell
docker compose exec db psql -U postgres -d fitness_ai
```
