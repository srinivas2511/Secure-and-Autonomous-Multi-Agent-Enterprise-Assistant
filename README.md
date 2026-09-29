# Secure and Autonomous Multi-Agent Enterprise Assistant

A full-stack, multi-agent AI platform that decomposes complex enterprise requests into subtasks, routes them to specialized agents, grounds responses in a RAG knowledge base, enforces Zero-Trust RBAC, explains every decision with confidence scores, gates sensitive operations through Human-in-the-Loop approval, and ships a built-in observability dashboard with trace spans, LLM token metrics, and a live events feed.

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Setup](#setup)
6. [Usage](#usage)
7. [API Reference](#api-reference)
8. [Observability](#observability)
9. [Running Tests](#running-tests)
10. [Configuration](#configuration)

---

## Features

| Requirement | What's implemented |
|---|---|
| **FR-1** Auth & request intake | JWT login/register; authenticated `POST /api/requests` |
| **FR-2** Orchestration & decomposition | Keyword-based decomposer → sequential agent dispatch loop |
| **FR-3** RAG pipeline | ChromaDB vector store + `sentence-transformers` embeddings + Ollama LLM grounding |
| **FR-4** RBAC | Per-role, per-agent-type permission matrix; admin-toggleable at runtime |
| **FR-5** Zero-Trust | `verify_continuous_access` re-checked before every subtask, not just at login |
| **FR-6** Explainable AI | Every `AgentResult` carries `confidence` (0–1) + human-readable `explanation` |
| **FR-7** Human-in-the-Loop | Sensitive or low-confidence subtasks → `pending_approval`; admin approve/reject UI |
| **FR-8** Audit logging | Append-only `AuditLog` table (DB-level trigger blocks UPDATE/DELETE); every action logged |
| **FR-9** Workflow automation | Keyword-planned multi-step execution over simulated enterprise functions |
| **FR-10** Transparent results | Frontend shows result, explanation, confidence, sources, workflow steps per subtask |
| **FR-11** Admin console | Users, permissions, audit logs, metrics, RAG evaluation, system health, settings |
| **FR-12** Evaluation metrics | Accuracy, timing, security, HITL, and explainability reports via `GET /api/admin/metrics` |
| **Observability** | TraceSpan model · LLM token counts · Gantt timeline · SVG agent graph · events feed |

---

## Architecture

```
User (browser)
      │
      ▼
React Frontend (Vite)
      │  REST/JSON (JWT bearer)
      ▼
FastAPI Backend ──► Workflow Orchestrator
                          │
              ┌───────────┼────────────────────────┐
              ▼           ▼           ▼             ▼
         RAG Agent  Analytics   Workflow      Security / Validation
              │        Agent      Agent           Agents
              ▼           ▼           ▼
          ChromaDB    Mock ERP    Function       (stub)
          (vectors)    data       Registry
              │
              ▼
           Ollama (local LLM — llama3.2 by default)
              │
      ┌───────┴──────────────────────┐
      │       Observability Layer    │
      │  TRACES · METRICS · EVENTS   │
      │    TraceSpan (Postgres)      │
      └──────────────────────────────┘
              │
              ▼
     Admin Observability Dashboard
   Timeline · Agent Graph · Trace Details
```

### Backend packages (`backend/app/`)

| Package | Responsibility |
|---|---|
| `agents/` | One file per specialized agent; all implement `BaseAgent.run()`. `registry.py` is the single wiring point. |
| `orchestrator/` | `decomposer.py` routes keywords → agent types; `orchestrator.py` runs the sequential dispatch loop, emits `TraceSpan` rows, persists subtask results. |
| `rag/` | `pipeline.py` — retrieval + LLM call; `llm.py` — Ollama wrapper returning `LLMResult` (text + timing + token counts); `vector_store.py` — ChromaDB client; `embeddings.py` + `ingest.py` — document ingestion. |
| `rbac/` | `roles.py` — `can_use_agent`, `require_admin`; `zero_trust.py` — `verify_continuous_access`. |
| `hitl/` | `gate.py` — `requires_approval` (checks agent type, confidence threshold, sensitive flag). |
| `audit/` | `logger.py` — `log_event`, session-scoped, commits atomically with the caller's transaction. |
| `workflow/` | `planner.py` — keyword → step list; `functions.py` — simulated ERP/HRMS functions + mock data. |
| `metrics/` | `evaluator.py` — on-demand aggregate accuracy, timing, security, HITL, and explainability metrics from DB. |
| `models/` | SQLAlchemy ORM: `User`, `EnterpriseRequest`, `SubTask`, `WorkflowExecution`, `AuditLog`, `TraceSpan`, `RolePermission`, `RagEvaluationRun`. |
| `schemas/` | Pydantic request/response shapes, kept separate from ORM models. |
| `core/` | `config.py` — single `Settings` object; `database.py` — engine/session; `security.py` — JWT + bcrypt helpers. |
| `api/routes/` | Thin FastAPI handlers that delegate to the packages above. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite, React Router, Axios |
| Backend | FastAPI, Uvicorn, SQLAlchemy 2, Pydantic v2 |
| Database | PostgreSQL 16 (via Docker) |
| Vector store | ChromaDB 1.0 (via Docker) |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| LLM | Ollama (local) — `llama3.2` by default |
| Auth | JWT (`python-jose`) + bcrypt (`passlib`) |
| Testing | pytest + SQLite in-memory |

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── agents/          # BaseAgent, 5 specialized agents, registry
│   │   ├── api/routes/      # auth, requests, approvals, admin
│   │   ├── audit/           # append-only event logger
│   │   ├── core/            # config, database, security helpers
│   │   ├── hitl/            # HITL approval gate
│   │   ├── metrics/         # evaluation report computation
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── orchestrator/    # decomposer + dispatch loop
│   │   ├── rag/             # pipeline, LLM wrapper, vector store, ingest
│   │   ├── rbac/            # roles, zero-trust, seed
│   │   ├── schemas/         # Pydantic response shapes
│   │   └── workflow/        # planner + simulated enterprise functions
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── api/             # admin.js, auth.js, requests.js, observability.js
│       ├── components/      # NavBar, ProtectedRoute
│       ├── context/         # AuthContext
│       └── pages/           # Login, Register, Requests, RequestDetail,
│                            #   Approvals, Admin, Observability
├── docker-compose.yml       # Postgres + ChromaDB
└── REQUIREMENTS.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop (for Postgres + ChromaDB)
- [Ollama](https://ollama.com) with a model pulled (`ollama pull llama3.2`)

### 1 — Start infrastructure

```bash
docker compose up -d
```

This starts Postgres on **port 5439** and ChromaDB on **port 8025**.

### 2 — Backend

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env      # defaults match the Docker services above
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8123
```

**Linux / macOS:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8123
```

On first startup the backend:
- Creates all DB tables (including `trace_spans`) via `Base.metadata.create_all()`
- Seeds default RBAC permissions
- Ingests sample enterprise documents into ChromaDB

Interactive API docs: **http://localhost:8123/docs**

### 3 — Local LLM

```bash
ollama serve          # if not already running as a service
ollama pull llama3.2  # ~2 GB download; only needed once
```

### 4 — Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_URL=http://localhost:8123
npm run dev
```

App: **http://localhost:5173**

---

## Usage

### Roles

| Role | Capabilities |
|---|---|
| `employee` | Submit requests, view own results |
| `manager` | All employee capabilities + additional agent permissions (configurable) |
| `admin` | All capabilities + admin console, approvals, observability |

The first registered user should be promoted to `admin` via the script:
```bash
.venv/Scripts/python -m app.scripts.set_user_role <email> admin
```

### Submitting a request

1. Log in at `/login` (or register at `/register`)
2. On `/requests`, type a natural-language request and submit
3. The orchestrator decomposes it, dispatches agents, and streams back results
4. Each subtask shows its agent type, status, confidence score, and explanation
5. Workflow steps are expandable; RAG sources are cited inline

**Example requests:**
- `"What is the leave policy for senior employees?"` → RAG agent
- `"Show me the headcount and expenses for Engineering"` → Analytics agent
- `"Schedule approval for the Q4 budget submission"` → Workflow agent
- `"Who has access to financial reports?"` → Security + RAG agents

### Admin console (`/admin`, admin only)

| Section | What it shows |
|---|---|
| Metrics | Accuracy, timing, security, HITL, and explainability aggregate tables |
| Audit logs | Filterable append-only event log (event type, user, action, context) |
| Decision trace | Full causal trail for any subtask: result + explanation + every audit event |
| RBAC | Role × agent-type permission matrix, toggle with one click |
| Users | List all users, change role or active status |
| System health | DB counts, ChromaDB document count, agent registry, HITL threshold |
| Settings | Adjust `hitl_confidence_threshold` at runtime |
| RAG evaluation | On-demand hallucination-rate comparison: RAG vs. baseline (≈12 LLM calls) |

### Approvals (`/approvals`, admin only)

Lists subtasks gated for human review (sensitive data or confidence below threshold). Approve or reject each with an optional reason — decision is logged and the parent request status recomputes automatically.

---

## API Reference

All endpoints require `Authorization: Bearer <token>` (except `/api/auth/*`).

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register a new user |
| `POST` | `/api/auth/login` | Obtain a JWT access token |
| `GET` | `/api/auth/me` | Current user profile |

### Requests

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/requests` | Submit a new enterprise request (triggers orchestration) |
| `GET` | `/api/requests` | List own requests |
| `GET` | `/api/requests/{id}` | Get one request with subtask details |

### Approvals (admin)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/approvals` | List pending HITL subtasks |
| `GET` | `/api/approvals/count` | Count of pending approvals (used by nav badge) |
| `POST` | `/api/approvals/{id}/approve` | Approve a subtask |
| `POST` | `/api/approvals/{id}/reject` | Reject a subtask |

### Admin

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/requests` | All requests across all users |
| `GET` | `/api/admin/users` | All users |
| `PATCH` | `/api/admin/users/{id}` | Update role / active status |
| `GET` | `/api/admin/permissions` | RBAC matrix |
| `POST` | `/api/admin/permissions/toggle` | Grant or revoke a role+agent permission |
| `GET` | `/api/admin/audit-logs` | Filterable audit log |
| `GET` | `/api/admin/metrics` | Full evaluation report |
| `GET` | `/api/admin/trace/{subtask_id}` | Decision trace for one subtask |
| `GET` | `/api/admin/traces?request_id=` | Flat list of trace spans for a request |
| `GET` | `/api/admin/traces/{request_id}/tree` | Nested span tree (Agent Graph data) |
| `GET` | `/api/admin/system-health` | DB, RAG, agent registry status |
| `GET` | `/api/admin/settings` | Runtime settings |
| `PATCH` | `/api/admin/settings` | Update HITL threshold |
| `POST` | `/api/admin/rag-evaluation/run` | Trigger RAG vs. baseline evaluation |
| `GET` | `/api/admin/rag-evaluation` | Latest RAG evaluation result |

---

## Observability

The observability layer sits between the backend and the admin dashboard, providing three pillars:

### TRACES — `TraceSpan` model

Every unit of work during orchestration is recorded as a `TraceSpan` row in Postgres:

| `span_type` | What it represents |
|---|---|
| `agent` | One subtask execution (root-level span per agent) |
| `llm_call` | A `generate()` call to Ollama — carries `input_tokens`, `output_tokens`, `duration_ms` |
| `rag_retrieve` | ChromaDB vector-store query |
| `workflow_step` | One function step executed by WorkflowAgent |
| `hitl_gate` | A HITL approval trigger event |

Spans are linked via `parent_span_id` (self-referential FK), forming a tree per request:
```
EnterpriseRequest
  └─ [agent] rag           (confidence, duration_ms)
       └─ [llm_call]        (input_tokens, output_tokens, duration_ms)
  └─ [agent] analytics
       └─ [llm_call]
  └─ [agent] workflow
       └─ [workflow_step] retrieve_data
       └─ [workflow_step] generate_report
  └─ [agent] validation
```

### METRICS captured

- **Latency** — per-agent `duration_ms` (agent span), LLM call `duration_ms` (from Ollama's `eval_duration`)
- **Tokens** — `input_tokens` (`prompt_eval_count`) and `output_tokens` (`eval_count`) per LLM call
- **Confidence** — stored on each subtask and surfaced in span metadata
- **HITL turnaround** — `approved_at - created_at` per subtask (existing `SubTask` fields)

### EVENTS — live audit feed

The `/observability` page polls `GET /api/admin/audit-logs` every 10 seconds, color-coding events by type:
- `agent_action` — agent ran, was denied, or failed
- `data_access` — RAG retrieval, analytics data access, workflow data reads
- `admin` — permission changes, user updates, settings changes

### Dashboard (`/observability`, admin only)

| Panel | Description |
|---|---|
| **Metrics row** | Total duration, agent span count, LLM call count, total tokens, request status |
| **Timeline** | Pure-CSS Gantt chart — one bar per agent span, width ∝ `duration_ms`, offset ∝ start time; click to open Trace Details |
| **Agent Graph** | SVG top-down tree showing parent → child spans with status colors and duration labels |
| **Trace Details** | Side panel showing full span metadata: type, status, timing, tokens, confidence, explanation, sources, error |
| **Events feed** | Rolling 50-entry table of audit log events, auto-refreshed every 10 s |

---

## Running Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Tests run against an **in-memory SQLite database** — no Docker, Postgres, ChromaDB, or Ollama required. The suite covers RBAC, orchestration, agent selection, HITL gating, and audit logging in isolation. See `tests/conftest.py` for the fixture setup.

---

## Configuration

All backend settings are read from `backend/.env` (see `.env.example` for defaults):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://enterprise:enterprise@localhost:5439/enterprise_assistant` | Postgres connection string |
| `JWT_SECRET_KEY` | `change-me-in-production` | **Must be changed before any real deployment** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token lifetime |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed frontend origins |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Model name passed to Ollama |
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8025` | ChromaDB port |

Frontend settings (`frontend/.env`):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8123` | Backend base URL |

---

## Notes

- `Base.metadata.create_all()` runs on every backend startup — no Alembic migrations yet. Adding the `trace_spans` table on an existing DB is safe; it creates the table if absent.
- The `metadata` column on `TraceSpan` is stored as `metadata_` in the ORM to avoid collision with SQLAlchemy's reserved `.metadata` attribute; the API exposes it as `metadata`.
- `WorkflowAgent` and `AnalyticsAgent` use simulated mock data (not real ERP/HRMS integrations), per the project scope.
- Cost tracking is not implemented because Ollama is a free local runtime; the `TraceSpan` metadata field is available to add per-token cost if the LLM provider changes.
