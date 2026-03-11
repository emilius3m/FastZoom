# FastZoom

<p align="center">
  <img src="app/static/img/logo/logo.jpg" width="350">
</p>

## Overview

FastZoom is a comprehensive web application built with FastAPI, designed for managing archaeological sites, artifacts, and documentation. It provides a complete digital platform for archaeological documentation, including:

- **Multi-tenant Site Management**: Organize multiple archaeological sites with granular permissions
- **Advanced Stratigraphy**: Full support for US (Unità Stratigrafiche) and USM (Unità Stratigrafiche Murarie) with Harris Matrix
- **Artifact Cataloging**: Complete inventory system with archaeological metadata
- **Scientific Samples**: C14 dating, pollen analysis, bone analysis, and more
- **Photo Management**: High-resolution photo storage with Deep Zoom capabilities
- **Construction Site Tracking**: Giornale di Cantiere with operator management
- **ICCD Compliance**: Standardized cataloging following Italian standards
- **Geographic Mapping**: Interactive GIS integration with layers and markers

The application supports user authentication, role-based permissions, team management, and secure file storage via MinIO. The frontend leverages HTMX for dynamic interactions, Jinja2 for templating, and Tailwind CSS with Flowbite for styling.

This project provides a robust backend for archaeological documentation, enabling collaborative workflows for teams to annotate, search, and share site photos and data.

## External Libraries Used

- [FastAPI](https://fastapi.tiangolo.com/) (^0.115.0): High-performance web framework for APIs and HTML responses.
- [SQLAlchemy](https://www.sqlalchemy.org/) (^2.0.0): ORM and SQL toolkit for database interactions.
- [Alembic](https://alembic.sqlalchemy.org/) (^1.13.0): Database migration tool.
- [Pydantic](https://docs.pydantic.dev/) (^2.8.0): Data validation and serialization.
- [Jinja2](https://jinja.palletsprojects.com/) (^3.1.0): Templating engine for HTML.
- [Alpine.js](https://alpinejs.dev/) (via CDN): Lightweight JavaScript for interactivity.
- [OpenSeadragon](https://openseadragon.github.io/) (minified JS): Deep zoom image viewer for high-res photos.
- [MinIO](https://min.io/) (Python client): Object storage for photos and deep zoom tiles.
- [Uvicorn](https://www.uvicorn.org/) (^0.30.0): ASGI server.
- [Passlib](https://passlib.readthedocs.io/) (^1.7.0): Password hashing.
- [python-multipart](https://github.com/encode/python-multipart) (^0.0.9): Form data parsing for uploads.
- [Pillow](https://pillow.readthedocs.io/) (^10.0.0): Image processing for thumbnails and tiles.
- [Loguru](https://loguru.readthedocs.io/) (^0.7.2): Structured logging.

Dependencies are managed via Poetry (`pyproject.toml` and `poetry.lock`).

## Features

### Core Functionality
- **User Management**: Registration, login, password updates, profiles, and admin controls.
- **Role and Permissions**: Custom roles with granular permissions for sites and photos.
- **Site Management**: Create, edit, and organize archaeological sites with teams and user assignments.
- **Multi-tenant Architecture**: Each user can have access to multiple sites with different permission levels.
- **Photo Upload and Storage**: Secure uploads to MinIO, automatic thumbnail generation, and deep zoom pyramid creation (DZI format).
- **Deep Zoom Viewing**: Interactive photo viewer with zoom, pan, rotate, and annotation support using OpenSeadragon.

### Advanced Archaeological Features
- **Stratigraphy (US/USM)**: Complete management of stratigraphic units with standard MiC 2021 compliance
  - US (Unità Stratigrafiche): Positive and negative units with full documentation
  - USM (Unità Stratigrafiche Murarie): Wall stratigraphic units with construction techniques
  - File management: Drawings, photos, sections, and documents per unit
  - Harris Matrix: Automatic generation and visualization of stratigraphic relationships
  
- **Artifact Inventory**: Complete cataloging system
  - Full metadata: material, dimensions, dating, conservation status
  - Provenience tracking: US, USM, or burial association
  - Multiple classification systems: category, type, class, form
  
- **Burial Records**: Comprehensive tomb documentation
  - Anthropological data: sex, age, stature, orientation
  - Grave goods: artifact inventory per burial
  - Conservation status and pathologies
  
- **Scientific Samples**: Sample management for analysis
  - Sample types: C14, pollen, bone, ceramic, sediment, mortar, wood
  - Laboratory tracking: analysis requests, results, and interpretations
  - Dating calibration: C14 calibration data and sigma values
  
- **Construction Site Management**:
  - Giornale di Cantiere: Daily site journals with weather and activities
  - Operatori: Worker management with specializations
  - Problem tracking and solutions documentation
  
- **ICCD Compliance**: Standardized cataloging following Italian Ministry standards
  - Multiple record types: CA (Ceramics), MA (Materials), RA (Artifacts), SI (Sites)
  - Schema validation and export capabilities
  
- **Geographic Maps**: Interactive GIS integration
  - Map layers with GeoJSON support
  - Markers with photo associations
  - Coordinate systems and bounds management

### UI/UX Features
- **Admin Dashboard**: Manage users, sites, roles, and permissions via intuitive interfaces.
- **Team Collaboration**: Invite users to sites, manage group permissions.
- **Security**: CSRF protection, JWT authentication with blacklist, rate limiting.
- **Responsive UI**: Mobile-friendly design with themes and modals for uploads/edits.
- **Dark Mode**: Full dark mode support throughout the application.
- **API Endpoints**: RESTful APIs for CRUD on all entities.

### Developer Tools
- **API Documentation**: Auto-generated Swagger/OpenAPI docs at `/docs`
- **Database Migrations**: Alembic for schema evolution.
- **Performance Monitoring**: Request tracking and performance metrics.
- **Logging**: Structured logging with Loguru for debugging and monitoring.

## Admin Login Credentials

- **Email**: superuser@admin.com
- **Password**: password123

Use these to access admin dashboard after setup.

## Docker Compose

1. Copy `.env.example` to `.env` and adjust secrets/URLs as needed.
2. Build and start containers:
   ```bash
   docker compose up --build
   ```
3. Access the app at http://localhost:8000
4. Access MinIO console at http://localhost:9001 (user/pass: minioadmin)
5. Stop containers:
   ```bash
   docker compose down
   ```

## Quick Setup Using PowerShell Script

For Windows, use `setup.ps1` to automate setup.

### Commands

| Command      | Description                     |
|--------------|---------------------------------|
| setup        | Full project initialization     |
| install      | Install dependencies            |
| env          | Generate .env file              |
| migrate      | Run Alembic migrations          |
| init-db      | Initialize database             |
| run          | Start production server         |
| run-dev      | Start with auto-reload          |
| credentials  | Display admin credentials       |
| status       | Check project status            |
| clean        | Clean temporary files           |

### Usage

1. Open PowerShell in project directory:
   ```powershell
    cd "C:\Users\E3M\OneDrive - beniculturali.it\Desktop\FastZoom"
    ```

2. Run a command, e.g.:
   ```powershell
    .\setup.ps1 setup
    ```

   Or start the app:
   ```powershell
    .\setup.ps1 run-dev
    ```

## Manual Setup

### Prerequisites

- Python 3.12+ (Python 3.13.7 is specified in pyproject.toml)
- MinIO server (local or cloud) for storage.
- PostgreSQL/SQLite for database (SQLite for dev).
- Poetry (optional - if you encounter "Schema poetry-schemas does not exist" error, use pip instead)

### Steps

1. **Clone/Navigate**:
   ```bash
    git clone <repo-url>
    cd FastZoom
    ```

2. **Install Dependencies**:
   ```bash
    poetry install
   ```
   Or with pip:
   ```bash
    pip install -r requirements.txt
   ```

   **Note**: If you encounter error "Schema poetry-schemas does not exist",
   this indicates Poetry is not properly installed or configured in your environment.
   You can install dependencies directly using pip instead of Poetry:

   **Option 1: Use provided installer script**
   ```bash
   .\install.bat  # Windows
   # or
   python install_dependencies.py  # Cross-platform
   ```

   **Option 2: Manual installation**
   
   ```bash
   pip install python==3.13.7
   pip install fastapi==0.115.14
   pip install sqlalchemy==2.0.41
   pip install uvicorn==0.35.0
   pip install aiosqlite==0.19.0
   pip install jinja2==3.1.6
   pip install httpx==0.28.1
   pip install nh3==0.2.21
   pip install alembic==1.16.2
   pip install pydantic-settings==2.2.1
   pip install minio==7.2.7
   pip install fastapi-csrf-protect==1.0.3
   pip install "fastapi-users[sqlalchemy]==14.0.1"
   pip install prompt-toolkit==6.25.2
   pip install pydantic==2.11.7
   pip install jsonschema==4.23.0
   pip install loguru==0.7.2
   pip install ruff==0.0.291
   pip install black==23.9.1
   pip install isort==5.12.0
   pip install ipykernel==6.25.2
   pip install pytest==7.4.3
   ```

3. **Environment Configuration**:

   Create `.env` in root:
   ```env
   # Database
   DATABASE_URL=sqlite+aiosqlite:///./fastzoom.db

   # JWT/Security
   SECRET_KEY=your-super-secret-key-change-me
   CSRF_SECRET_KEY=your-csrf-secret-key-change-me

   # MinIO Storage
   MINIO_URL=http://localhost:9000
   MINIO_ACCESS_KEY=minioadmin
   MINIO_SECRET_KEY=minioadmin
   MINIO_BUCKET=fastzoom-bucket
   MINIO_SECURE=false

   # App
   COOKIE_SAMESITE=lax
   COOKIE_SECURE=false  # Set true for HTTPS
   ```

4. **MinIO Setup**: Run MinIO locally (`minio server /data`) and create bucket.

5. **Database Migrations**:
   ```bash
   alembic upgrade head
   ```

6. **Run Application**:
   ```bash
   poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Access**: Open http://localhost:8000 in your browser.

## Project Structure

```
FastZoom/
├── app/
│   ├── core/              # Config, security, permissions, middleware
│   ├── database/          # DB session, base, migrations
│   ├── models/            # SQLAlchemy models (30+ models)
│   ├── routes/            # API and view routes
│   │   ├── api/           # REST API endpoints (v1 structure)
│   │   └── view/         # HTML view routes
│   ├── schema/            # Pydantic schemas
│   ├── services/          # Business logic layer
│   ├── static/            # CSS, JS (OpenSeadragon, HTMX), images
│   └── templates/         # Jinja2 HTML (sites, photos, admin, modals)
├── alembic/               # Migration versions
├── tests/                 # Unit tests
├── main.py                # App entrypoint
├── pyproject.toml         # Poetry config
├── alembic.ini
├── setup.ps1              # Windows setup script
└── README.md
```

## Recent Updates (2025-01-16)

### Bug Fixes
- ✅ Fixed JavaScript syntax error in `cantieri.html` template (line 659-662)
- ✅ Commented out missing `photo_metadata` import in `app.py` (line 266)

### Documentation
- ✅ Generated complete Entity Relationship Diagram (ERD) with 30+ entities
- ✅ Documented all API endpoints in `archeologia_avanzata.py` and their usage
- ✅ Updated project architecture documentation

### Architecture Status
- **API v1**: RESTful API structure with `/api/v1` prefix
- **Multi-tenant**: Full support for user permissions per site
- **Domain Exceptions**: Comprehensive exception hierarchy implemented
- **Dependency Injection**: Service layer with proper dependency injection
- **Harris Matrix**: Complete implementation with visualization

## ER Diagram

A complete Entity Relationship Diagram is available in [`ER_DIAGRAM_COMPLETE.md`](ER_DIAGRAM_COMPLETE.md).

The diagram includes 30+ entities covering:
- User management and authentication
- Archaeological sites and permissions
- Stratigraphy (US/USM) with Harris Matrix
- Archaeological records (tombs, artifacts, samples)
- Photos and documentation
- Geographic maps and markers
- Construction site management
- ICCD records and forms

## Troubleshooting

### Poetry Installation Error

- **Issue**: "Schema poetry-schemas does not exist" when running Poetry commands.
- **Cause**: Usually caused by invalid `pyproject.toml` configuration or corrupted Poetry installation.
- **Fix Options**:

  **Option 1: Validate and fix pyproject.toml**
  ```bash
  python validate_poetry_config.py  # Validates and fixes common issues
  ```

  **Option 2: Reset Poetry completely**
  ```bash
  .\reset_poetry.bat  # Windows script provided
  ```
  Or manually:
  ```bash
  # 1. Uninstall Poetry completely
  curl -sSL https://install.python-poetry.org | python3 --uninstall

  # 2. Clean Poetry cache and config
  # Delete these folders if they exist:
  # %USERPROFILE%\AppData\Local\pypoetry
  # %USERPROFILE%\AppData\Roaming\pypoetry

  # 3. Reinstall Poetry
  curl -sSL https://install.python-poetry.org | python3 -

  # 4. Verify installation
  poetry --version
  ```

  **Option 3: Use provided installation script (bypasses Poetry)**
  ```bash
  .\install.bat  # Windows
  # or
  python install_dependencies.py  # Cross-platform
  ```

  **Option 4: Install dependencies directly with pip**
  ```bash
  pip install -r requirements.txt
  ```
  Or install dependencies individually as listed in Manual Setup section.

### Photo Thumbnails and Deep Zoom

- **Issue**: Missing thumbnails or DZI tiles (404 errors).
- **Cause**: Failed generation during upload or invalid MinIO paths.
- **Fix**:
  - Ensure MinIO is running and bucket accessible.
  - Run thumbnail regeneration if needed (custom script available in services).
  - Fallback images used for missing assets.
  - **Deep Zoom**: Tiles generated on upload; viewer in `photo_modal.html` uses OpenSeadragon.

### MinIO Integration

- Verify credentials in `.env`.
- Test bucket access: `mc mb myminio/fastzoom-bucket` (using MinIO client).

## API Documentation

### Main API Routes

- **Authentication**: `/api/v1/auth/*` - Login, register, logout
- **Sites**: `/api/v1/sites/*` - Site CRUD and management
- **Photos**: `/api/v1/photos/*` - Photo upload, metadata, deep zoom
- **Users**: `/api/v1/users/*` - User management and profiles
- **Admin**: `/api/v1/admin/*` - System administration
- **Archaeology**: `/api/v1/archeologia/*` - US, tombs, artifacts, samples
- **Stratigraphy**: `/api/v1/us/*` - US/USM management
- **Harris Matrix**: `/api/v1/harris-matrix/*` - Matrix visualization and editing
- **Construction Sites**: `/api/v1/cantieri/*` - Giornale and operatori
- **Geographic**: `/api/v1/geographic/*` - Maps and layers
- **ICCD**: `/api/v1/iccd/*` - ICCD records and exports

### View Routes

- **Dashboard**: `/dashboard` - Main dashboard
- **Sites**: `/sites/*` - Site management pages
- **Photos**: `/photos/*` - Photo gallery and viewer
- **Archaeology**: `/archeologia/*` - Advanced archaeology features
- **Construction**: `/cantieri/*` - Construction site management
- **Admin**: `/admin/*` - Administration pages

## Contributing

Contributions welcome! Fork the repo, create a branch, and submit a PR. Ensure tests pass and follow PEP 8.

## License

MIT License. See [LICENSE](LICENSE) for details.
