# Guida al Refactoring FastAPI - Sistema Archeologico Multi-Sito

## Panoramica

Questa guida documenta il piano completo di refactoring per modernizzare l'API FastAPI del sistema archeologico, applicando le 9 tecniche di refactoring identificate nell'analisi del codice.

## Stato Attuale dell'Architettura

### Problemi Identificati

1. **Route Handler Monolitici**: L'endpoint `upload_photo` contiene 632 righe di logica business mista
2. **Service Layer Incompleto**: Logica distribuita tra route e servizi limitati
3. **Repository Pattern Parziale**: Solo alcuni repository implementati
4. **Endpoint Non Suddivisi**: Operazioni CRUD multiple in singoli endpoint
5. **Dependency Injection Basilare**: Mancano factory functions avanzate
6. **Assenza API Versioning**: Nessun controllo versioni esplicito

### Architettura Target

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Route Handlers │───▶│  Service Layer  │───▶│ Repository Layer │
│    (Thin Layer)  │    │ (Business Logic) │    │  (Data Access)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Pydantic       │    │   Middleware     │    │   SQLAlchemy     │
│   Schemas       │    │ (Cross-cutting)  │    │    Models        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 1. Estrazione della Logica Business dai Route Handler

### Problema
L'endpoint `upload_photo` in `app/routes/api/sites_photos.py` contiene tutta la logica di business.

### Soluzione
Creare service dedicati e ridurre gli handler a deleghe thin.

#### Before
```python
@photos_router.post("/{site_id}/api/photos/upload")
async def upload_photo(site_id: UUID, photos: List[UploadFile] = File(...), ...):
    # 632 righe di logica business...
    await storage_service.save_upload_file(...)
    await photo_metadata_service.extract_metadata_from_file(...)
    # ...altri 600+ righe
```

#### After
```python
@photos_router.post("/{site_id}/api/photos/upload")
async def upload_photo(
    site_id: UUID,
    photos: List[UploadFile] = File(...),
    upload_service: PhotoUploadService = Depends(get_photo_upload_service),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Upload foto con delega completa alla logica di business"""
    return await upload_service.upload_photos(site_id, photos, current_user_id)
```

### Implementazione
1. Creare `app/services/photo_upload_service.py`
2. Spostare logica da `upload_photo` al service
3. Aggiornare l'endpoint per usare il service

## 2. Introduzione del Service Layer

### Struttura Service Layer

```
app/services/
├── __init__.py
├── photo_upload_service.py      # Upload e processamento
├── photo_metadata_service.py    # Estrazione metadati (esistente)
├── photo_management_service.py  # CRUD operazioni
├── photo_search_service.py      # Ricerca e filtri
└── photo_validation_service.py  # Validazione dati
```

### Esempio PhotoUploadService

```python
class PhotoUploadService:
    def __init__(
        self,
        db: AsyncSession,
        storage_service,
        metadata_service: PhotoMetadataService,
        photo_repo: PhotoRepository
    ):
        self.db = db
        self.storage = storage_service
        self.metadata = metadata_service
        self.photo_repo = photo_repo

    async def upload_photos(
        self,
        site_id: UUID,
        files: List[UploadFile],
        user_id: UUID
    ) -> List[PhotoUploadResult]:
        results = []
        for file in files:
            result = await self._upload_single_photo(site_id, file, user_id)
            results.append(result)
        return results

    async def _upload_single_photo(
        self,
        site_id: UUID,
        file: UploadFile,
        user_id: UUID
    ) -> PhotoUploadResult:
        # 1. Validazione file
        validation = await self.metadata.validate_image_file(file)
        if not validation[0]:
            raise HTTPException(400, validation[1])

        # 2. Upload storage
        filename, file_path, file_size = await self.storage.save_upload_file(
            file, str(site_id), str(user_id)
        )

        # 3. Estrazione metadati
        await file.seek(0)
        exif_data, metadata = await self.metadata.extract_metadata_from_file(file, filename)

        # 4. Creazione record DB
        photo_record = await self.metadata.create_photo_record(
            filename=filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            site_id=str(site_id),
            uploaded_by=str(user_id),
            metadata=metadata
        )

        # 5. Salvataggio DB
        self.db.add(photo_record)
        await self.db.commit()
        await self.db.refresh(photo_record)

        # 6. Generazione thumbnail
        await file.seek(0)
        thumbnail_path = await self.metadata.generate_thumbnail_from_file(
            file, str(photo_record.id)
        )

        if thumbnail_path:
            photo_record.thumbnail_path = thumbnail_path
            await self.db.commit()

        return PhotoUploadResult(
            photo_id=photo_record.id,
            filename=filename,
            file_size=file_size
        )
```

## 3. Implementazione del Repository Pattern

### Repository Esistenti vs Necessari

| Repository | Stato | Priorità |
|------------|-------|----------|
| BaseRepository | ✅ Esistente | - |
| ICCDRecordRepository | ✅ Esistente | - |
| PhotoRepository | ❌ Mancante | 🔴 Alta |
| UserRepository | ❌ Mancante | 🔴 Alta |
| SiteRepository | ❌ Mancante | 🟡 Media |

### Esempio PhotoRepository

```python
from app.repositories.base import BaseRepository
from app.models.photos import Photo
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy import select, and_, or_, func

class PhotoRepository(BaseRepository[Photo]):
    """Repository per operazioni sui dati fotografici"""

    async def get_site_photos(
        self,
        site_id: UUID,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Photo]:
        """Recupera foto del sito con filtri"""
        query = select(Photo).where(Photo.site_id == site_id)

        if filters:
            conditions = []
            # Applica filtri dinamici
            for key, value in filters.items():
                if hasattr(Photo, key):
                    if key == 'search':
                        search_term = f"%{value}%"
                        conditions.append(
                            or_(
                                Photo.filename.ilike(search_term),
                                Photo.title.ilike(search_term),
                                Photo.description.ilike(search_term)
                            )
                        )
                    elif isinstance(value, list):
                        conditions.append(getattr(Photo, key).in_(value))
                    else:
                        conditions.append(getattr(Photo, key) == value)

            if conditions:
                query = query.where(and_(*conditions))

        query = query.offset(skip).limit(limit).order_by(Photo.created.desc())
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_photo_with_relations(self, photo_id: UUID) -> Optional[Photo]:
        """Recupera foto con relazioni caricate"""
        from sqlalchemy.orm import joinedload

        query = select(Photo).options(
            joinedload(Photo.site),
            joinedload(Photo.uploader)
        ).where(Photo.id == photo_id)

        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def update_photo_metadata(
        self,
        photo_id: UUID,
        metadata: Dict[str, Any]
    ) -> Photo:
        """Aggiorna metadati foto"""
        photo = await self.get(photo_id)
        if not photo:
            raise ValueError(f"Photo {photo_id} not found")

        # Aggiorna campi specifici
        updatable_fields = {
            'title', 'description', 'keywords', 'photo_type',
            'inventory_number', 'excavation_area', 'material'
        }

        for field, value in metadata.items():
            if field in updatable_fields and hasattr(photo, field):
                setattr(photo, field, value)

        await self.db_session.commit()
        return photo

    async def get_photos_statistics(self, site_id: UUID) -> Dict[str, Any]:
        """Statistiche foto del sito"""
        # Conteggio totale
        total_query = select(func.count(Photo.id)).where(Photo.site_id == site_id)
        total_result = await self.db_session.execute(total_query)
        total = total_result.scalar()

        # Per tipo
        type_query = select(
            Photo.photo_type,
            func.count(Photo.id)
        ).where(
            and_(Photo.site_id == site_id, Photo.photo_type.isnot(None))
        ).group_by(Photo.photo_type)

        type_result = await self.db_session.execute(type_query)
        by_type = {row[0]: row[1] for row in type_result.fetchall()}

        return {
            "total_photos": total,
            "photos_by_type": by_type
        }
```

## 4. Suddivisione di Endpoint Monolitici

### Endpoint Problematici

| Endpoint | Righe | Problema | Soluzione |
|----------|-------|----------|-----------|
| `upload_photo` | 632 | Tutto in uno | Split in fasi |
| `update_photo` | 150+ | CRUD + validation | Endpoint separati |
| `bulk_update_photos` | 100+ | Multiple operations | Service dedicato |

### Refactoring upload_photo

#### Before
```python
@photos_router.post("/{site_id}/api/photos/upload")
async def upload_photo(site_id: UUID, photos: List[UploadFile] = File(...), ...):
    # Upload + metadata + thumbnail + deep zoom + logging (632 righe)
```

#### After
```python
# Fase 1: Upload base
@photos_router.post("/{site_id}/api/photos/upload")
async def upload_photos(
    site_id: UUID,
    photos: List[UploadFile] = File(...),
    upload_service: PhotoUploadService = Depends()
):
    return await upload_service.upload_photos(site_id, photos, current_user_id)

# Fase 2: Processamento avanzato (separato)
@photos_router.post("/{site_id}/api/photos/{photo_id}/process")
async def process_photo(
    site_id: UUID,
    photo_id: UUID,
    processing_service: PhotoProcessingService = Depends()
):
    return await processing_service.process_deep_zoom(site_id, photo_id)

# Fase 3: Batch operations
@photos_router.post("/{site_id}/api/photos/batch/process")
async def batch_process_photos(
    site_id: UUID,
    photo_ids: List[UUID],
    batch_service: PhotoBatchService = Depends()
):
    return await batch_service.process_batch(site_id, photo_ids)
```

## 5. Separazione tra Pydantic Schema e Database Model

### Schema Ottimizzati

```python
# app/schema/photo_schemas.py

# Request Schemas (input validation)
class PhotoCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    description: Optional[str] = Field(None, max_length=2000)
    photo_type: PhotoType
    archaeological_metadata: 'ArchaeologicalMetadataRequest'

    class Config:
        use_enum_values = True

class ArchaeologicalMetadataRequest(BaseModel):
    inventory_number: Optional[str] = Field(None, max_length=100)
    excavation_area: Optional[str] = Field(None, max_length=200)
    stratigraphic_unit: Optional[str] = Field(None, max_length=100)
    material: Optional[MaterialType] = None
    chronology_period: Optional[str] = Field(None, max_length=100)

# Response Schemas (output formatting)
class PhotoResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    photo_type: str
    archaeological_data: 'ArchaeologicalMetadataResponse'
    urls: 'PhotoUrls'
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class PhotoUrls(BaseModel):
    full: str
    thumbnail: str
    deep_zoom: Optional[str] = None

# Update Schemas (partial updates)
class PhotoMetadataUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    description: Optional[str] = Field(None, max_length=2000)
    archaeological_metadata: Optional['ArchaeologicalMetadataUpdate'] = None

# Database Model (ottimizzato per query)
# app/models/photo_models.py
class Photo(Base):
    __tablename__ = "photos"

    # PK e relazioni
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('sites.id'), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Dati tecnici (indexed per performance)
    filename = Column(String(255), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, index=True)
    width = Column(Integer)
    height = Column(Integer)

    # Metadati tecnici JSONB (ricerca efficiente)
    exif_data = Column(JSONB, default={})

    # Metadati archeologici (campi separati per query)
    title = Column(String(250))
    description = Column(Text)
    photo_type = Column(Enum(PhotoType), index=True)
    inventory_number = Column(String(100), index=True)
    excavation_area = Column(String(200), index=True)
    material = Column(Enum(MaterialType), index=True)

    # Status e workflow
    is_published = Column(Boolean, default=False, index=True)
    is_validated = Column(Boolean, default=False, index=True)
    has_deep_zoom = Column(Boolean, default=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relazioni
    site = relationship("ArchaeologicalSite", back_populates="photos")
    uploader = relationship("User")
```

## 6. Dependency Injection Avanzata

### Factory Functions

```python
# app/core/dependencies.py

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_session

# Repository dependencies
def get_photo_repository(db: AsyncSession = Depends(get_async_session)) -> PhotoRepository:
    return PhotoRepository(db)

def get_user_repository(db: AsyncSession = Depends(get_async_session)) -> UserRepository:
    return UserRepository(db)

# Service dependencies
def get_photo_metadata_service() -> PhotoMetadataService:
    return photo_metadata_service

def get_storage_service() -> StorageService:
    return storage_service

def get_photo_upload_service(
    db: AsyncSession = Depends(get_async_session),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    metadata_service: PhotoMetadataService = Depends(get_photo_metadata_service),
    storage_service = Depends(get_storage_service)
) -> PhotoUploadService:
    return PhotoUploadService(db, storage_service, metadata_service, photo_repo)

def get_photo_management_service(
    db: AsyncSession = Depends(get_async_session),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    user_repo: UserRepository = Depends(get_user_repository)
) -> PhotoManagementService:
    return PhotoManagementService(db, photo_repo, user_repo)

# Annotated dependencies per type hints puliti
PhotoUploadServiceDep = Annotated[PhotoUploadService, Depends(get_photo_upload_service)]
PhotoManagementServiceDep = Annotated[PhotoManagementService, Depends(get_photo_management_service)]
```

### Usage negli Endpoint

```python
@photos_router.post("/{site_id}/api/photos/upload")
async def upload_photos(
    site_id: UUID,
    photos: List[UploadFile] = File(...),
    upload_service: PhotoUploadServiceDep,
    current_user_id: UUID = Depends(get_current_user_id)
):
    return await upload_service.upload_photos(site_id, photos, current_user_id)

@photos_router.get("/{site_id}/api/photos")
async def get_site_photos(
    site_id: UUID,
    page: int = 1,
    per_page: int = 24,
    search: Optional[str] = None,
    management_service: PhotoManagementServiceDep,
    current_user_id: UUID = Depends(get_current_user_id)
):
    return await management_service.get_site_photos_paginated(
        site_id, page, per_page, search, current_user_id
    )
```

## 7. Middleware per Cross-Cutting Concerns

### Middleware Implementati

```python
# app/core/middleware.py

import time
import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware per logging centralizzato delle richieste"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log richiesta
        logger.info(f"→ {request.method} {request.url}")
        if hasattr(request, 'user') and request.user:
            logger.info(f"  User: {request.user.id}")

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log risposta
            logger.info(".3f"
            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(".3f"
            raise

class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware per audit trail delle operazioni"""

    async def dispatch(self, request: Request, call_next):
        # Estrai info utente se presente
        user_id = None
        if hasattr(request, 'user') and request.user:
            user_id = request.user.id

        # Log operazione audit
        await self._log_audit_event(
            user_id=user_id,
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query),
            user_agent=request.headers.get('user-agent'),
            ip=request.client.host if request.client else None
        )

        response = await call_next(request)
        return response

    async def _log_audit_event(self, **kwargs):
        """Log evento audit nel database"""
        # Implementazione logging audit
        pass

class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware per monitoraggio performance"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        # Monitora performance
        if process_time > 5.0:  # Slow query threshold
            logger.warning(".3f"
        elif process_time > 1.0:
            logger.info(".3f"
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware per security headers"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Aggiungi security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        return response
```

### Registrazione Middleware

```python
# app/app.py

from app.core.middleware import (
    RequestLoggingMiddleware,
    AuditMiddleware,
    PerformanceMonitoringMiddleware,
    SecurityHeadersMiddleware
)

# Aggiungi middleware all'app
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
```

## 8. Versioning delle API

### Struttura Versioning

```
api/
├── v1/
│   ├── photos/
│   ├── sites/
│   └── iccd/
└── v2/
    ├── photos/
    ├── sites/
    └── iccd/
```

### Implementazione

```python
# app/routes/api/v1/photos.py
from fastapi import APIRouter

v1_photos_router = APIRouter(prefix="/photos", tags=["photos-v1"])

@v1_photos_router.get("/")
async def get_photos_v1():
    # Implementazione V1
    pass

@v1_photos_router.post("/upload")
async def upload_photos_v1():
    # Implementazione V1 (legacy)
    pass

# app/routes/api/v2/photos.py
from fastapi import APIRouter

v2_photos_router = APIRouter(prefix="/photos", tags=["photos-v2"])

@v2_photos_router.get("/")
async def get_photos_v2():
    # Implementazione V2 migliorata
    pass

@v2_photos_router.post("/upload")
async def upload_photos_v2():
    # Implementazione V2 con service layer
    pass

# app/app.py
from app.routes.api.v1 import photos as v1_photos
from app.routes.api.v2 import photos as v2_photos

# API Versionate
app.include_router(v1_photos.v1_photos_router, prefix="/api/v1")
app.include_router(v2_photos.v2_photos_router, prefix="/api/v2")

# Backward compatibility (deprecation warning)
@app.middleware("http")
async def deprecation_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/photos"):
        logger.warning("Deprecated API endpoint used: {request.url.path}. Use /api/v1/photos instead.")
    return await call_next(request)

app.include_router(v1_photos.v1_photos_router, prefix="/api", deprecated=True)
```

## 9. Best Practices Aggiuntive

### Type Hints Completi

```python
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from fastapi import UploadFile
from pydantic import BaseModel

# Type aliases
PhotoID = UUID
SiteID = UUID
UserID = UUID

# Generic response types
class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None

class PaginatedResponse(APIResponse):
    data: List[Any]
    total: int
    page: int
    per_page: int
    total_pages: int

# Service method signatures
class PhotoServiceProtocol(Protocol):
    async def upload_photos(
        self,
        site_id: SiteID,
        files: List[UploadFile],
        user_id: UserID
    ) -> List[PhotoUploadResult]:
        ...

    async def get_site_photos(
        self,
        site_id: SiteID,
        filters: Dict[str, Any],
        pagination: PaginationParams
    ) -> PaginatedResponse[PhotoResponse]:
        ...
```

### Gestione Errori Centralizzata

```python
# app/exceptions.py

class ArchaeologicalAPIError(Exception):
    """Base exception for API errors"""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(ArchaeologicalAPIError):
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message, status_code=400)
        self.field = field

class NotFoundError(ArchaeologicalAPIError):
    def __init__(self, resource: str, resource_id: Any):
        message = f"{resource} with id {resource_id} not found"
        super().__init__(message, status_code=404)

class PermissionDeniedError(ArchaeologicalAPIError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status_code=403)

class StorageError(ArchaeologicalAPIError):
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, status_code=507)  # Insufficient Storage
        self.original_error = original_error

# Exception handlers
# app/exception_handlers.py

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.exceptions import ArchaeologicalAPIError

async def archaeological_api_exception_handler(
    request: Request,
    exc: ArchaeologicalAPIError
) -> JSONResponse:
    """Handler centralizzato per eccezioni API"""

    # Log errore
    logger.error(f"API Error: {exc.message}", extra={
        'status_code': exc.status_code,
        'path': request.url.path,
        'method': request.method,
        'details': exc.details
    })

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "details": exc.details,
            "path": request.url.path
        }
    )

# Registrazione handlers
# app/app.py
from app.exception_handlers import archaeological_api_exception_handler
from app.exceptions import ArchaeologicalAPIError

app.add_exception_handler(ArchaeologicalAPIError, archaeological_api_exception_handler)
```

### Testing Structure

```python
# tests/
# ├── unit/
# │   ├── test_services/
# │   │   ├── test_photo_upload_service.py
# │   │   └── test_photo_metadata_service.py
# │   ├── test_repositories/
# │   │   ├── test_photo_repository.py
# │   │   └── test_user_repository.py
# │   └── test_schemas/
# │       └── test_photo_schemas.py
# ├── integration/
# │   ├── test_api/
# │   │   ├── test_photos_api.py
# │   │   └── test_sites_api.py
# │   └── test_database/
# │       └── test_photo_operations.py
# └── conftest.py

# tests/unit/test_services/test_photo_upload_service.py

import pytest
from unittest.mock import Mock, AsyncMock
from app.services.photo_upload_service import PhotoUploadService

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_storage():
    return AsyncMock()

@pytest.fixture
def mock_metadata():
    return AsyncMock()

@pytest.fixture
def mock_repo():
    return AsyncMock()

@pytest.fixture
def upload_service(mock_db, mock_storage, mock_metadata, mock_repo):
    return PhotoUploadService(mock_db, mock_storage, mock_metadata, mock_repo)

@pytest.mark.asyncio
async def test_upload_single_photo_success(upload_service, mock_storage, mock_metadata, mock_repo):
    # Arrange
    mock_file = Mock()
    mock_file.filename = "test.jpg"

    mock_storage.save_upload_file.return_value = ("test_uuid.jpg", "/path/test.jpg", 1024)
    mock_metadata.extract_metadata_from_file.return_value = ({"exif": "data"}, {"width": 800, "height": 600})
    mock_metadata.create_photo_record.return_value = Mock(id="photo-uuid")

    # Act
    result = await upload_service._upload_single_photo(
        site_id="site-uuid",
        file=mock_file,
        user_id="user-uuid"
    )

    # Assert
    assert result.photo_id == "photo-uuid"
    mock_storage.save_upload_file.assert_called_once()
    mock_metadata.extract_metadata_from_file.assert_called_once()
    mock_repo.db_session.add.assert_called_once()
    mock_repo.db_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_upload_photo_validation_failure(upload_service, mock_metadata):
    # Arrange
    mock_file = Mock()
    mock_metadata.validate_image_file.return_value = (False, "Invalid format")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await upload_service._upload_single_photo("site-uuid", mock_file, "user-uuid")

    assert exc_info.value.status_code == 400
    assert "Invalid format" in str(exc_info.value.detail)
```

## Roadmap di Implementazione

### Fase 1: Foundation (Settimane 1-2)
- [ ] Creare repository mancanti (PhotoRepository, UserRepository)
- [ ] Implementare PhotoUploadService base
- [ ] Refactoring upload_photo endpoint
- [ ] Test unitari per service layer

### Fase 2: Core Refactoring (Settimane 3-5)
- [ ] Suddivisione endpoint monolitici
- [ ] Dependency injection avanzata
- [ ] Middleware per cross-cutting concerns
- [ ] Repository pattern completo

### Fase 3: Modernization (Settimane 6-7)
- [ ] API versioning
- [ ] Ottimizzazione schemi Pydantic
- [ ] Gestione errori centralizzata
- [ ] Testing completo

### Fase 4: Optimization (Settimana 8)
- [ ] Performance monitoring
- [ ] Caching layer
- [ ] Documentazione API completa
- [ ] Deployment e migration

## Metriche di Successo

### Qualità del Codice
- Riduzione complessità ciclomatica del 70%
- Coverage test > 85%
- Zero code smells critici

### Performance
- Tempo risposta API < 500ms (media)
- Throughput upload > 10 foto/minuto
- Memory usage stabile

### Manutenibilità
- Service layer testabile isolatamente
- Repository riutilizzabili
- Schema validation robusta

### Scalabilità
- Dependency injection modulare
- Middleware configurabili
- API versionate per evoluzione