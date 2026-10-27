# E-commerce Backend API

A learning project: an e-commerce backend (API and database only, no frontend) built step by step with FastAPI, PostgreSQL and Redis.

## Current status

- In-memory products API (data resets when the server restarts)
- Planned next: PostgreSQL, authentication, orders, Redis caching, tests, Docker, CI/CD

## Tech stack

- Python 3.14, FastAPI, Uvicorn, Pydantic
- Later: PostgreSQL, SQLAlchemy, Alembic, Redis, Docker, pytest

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Then open:

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Features so far

- CRUD for products (`/v1/products`)
- Search, price filter, sorting and pagination
- Request validation with a consistent error format
- Idempotency-Key support on product creation
- In-memory rate limiting (20 requests per 10 seconds per IP)

See [API_DESIGN.md](API_DESIGN.md) for the endpoint list and error codes.
