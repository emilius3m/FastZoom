# FastZoom

<p align="center">
  <img src="app/static/img/logo/logo.jpg" width="350" alt="FastZoom logo">
</p>

FastZoom is a FastAPI web platform for archaeological documentation and site operations. It combines site management, stratigraphy workflows, photo/deep zoom handling, ICCD-aligned records, and team-based permissions in one application.

## Main Features

- Multi-site and multi-tenant access control
- US/USM stratigraphic records and Harris Matrix workflows
- Archaeological cataloging and documentation
- Photo upload, thumbnails, and Deep Zoom tile generation
- ICCD data entry and hierarchy support
- Site dashboards, mapping, and administrative tools
- Voice assistant integration (Pipecat-based modules in `app/services`)

## Tech Stack

- FastAPI, Uvicorn
- SQLAlchemy + Alembic
- Jinja2 + HTMX + Alpine.js + Tailwind/Flowbite
- MinIO object storage
- SQLite (default local dev DB) with async driver

## Prerequisites

- Python `3.12+` (project targets Python 3.12)
- MinIO (local or remote profile)
- Optional: Poetry
- Optional: Docker + Docker Compose

## Quick Start (Docker Compose)

1. Copy environment file:
   ```bash
   cp .env.example .env
   ```
2. Start services:
   ```bash
   docker compose up --build
   ```
3. Open:
   - App: `http://localhost:8000`
   - MinIO Console: `http://localhost:9001`
4. Stop services:
   ```bash
   docker compose down
   ```

## Local Setup (Without Docker)

1. Create and activate virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
   Or with Poetry:
   ```powershell
   poetry install
   ```
3. Create env file:
   ```powershell
   Copy-Item .env.example .env
   ```
4. Run migrations:
   ```powershell
   alembic upgrade head
   ```
5. Start the app:
   ```powershell
   uvicorn app.app:app --reload --host 127.0.0.1 --port 8000
   ```

## PowerShell Setup Script

Windows users can use `setup.ps1`:

```powershell
.\setup.ps1 help
.\setup.ps1 setup
.\setup.ps1 run-dev
```

Useful commands include:
- `setup`, `install`, `env`, `migrate`, `init-db`, `populate-db`
- `run`, `run-dev`
- `minio-install`, `minio-start`, `minio-stop`, `minio-setup`, `minio-status`, `minio-console`
- `credentials`, `status`, `clean`

## Environment Configuration

The project reads settings from `.env` (see `.env.example`). Core variables:

- `DATABASE_URL`
- `SECRET_KEY`
- `CSRF_SECRET_KEY`
- `MINIO_CONFIG_PROFILE` (`local` or `remote`)
- `MINIO_LOCAL_URL`, `MINIO_LOCAL_ACCESS_KEY`, `MINIO_LOCAL_SECRET_KEY`, `MINIO_LOCAL_BUCKET`
- `MINIO_REMOTE_URL`, `MINIO_REMOTE_ACCESS_KEY`, `MINIO_REMOTE_SECRET_KEY`, `MINIO_REMOTE_BUCKET`

For local Docker Compose, `MINIO_LOCAL_URL=http://minio:9000` is expected.

## Default Credentials

Development seed/admin credentials currently used by scripts:

- Email: `superuser@admin.com`
- Password: `password123`

Update these for non-development environments.

## Testing

Run tests:

```powershell
pytest
```

Coverage output is configured in `pytest.ini` (`htmlcov/` and terminal report).

## Project Structure

```text
FastZoom/
  app/
    core/          # Config, security, middleware
    database/      # Engine, sessions, DB bootstrap
    models/        # SQLAlchemy models
    routes/        # API and HTML routes
    schemas/       # Pydantic schemas
    services/      # Business logic and integrations
    static/        # Frontend assets
    templates/     # Jinja2 templates
  alembic/         # Migration scaffolding
  tests/           # Test suite
  docker-compose.yml
  main.py
  README.md
```

## API Docs

When the app is running:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Additional Documentation

- `ER_DIAGRAM_COMPLETE.md`
- `DESIGN_PATTERNS.md`
- `REFACTORING_GUIDE.md`
- `integration-instructions.md`

## License

MIT (see `LICENSE` if present in your distribution).
