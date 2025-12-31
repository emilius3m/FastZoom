# FastZoom Priority Refactoring Implementation Guide

## Summary of Changes

This document outlines the P0 (Critical) refactoring changes implemented to improve the FastZoom codebase architecture.

## ✅ Completed Tasks

### 1. Domain Exception Hierarchy Created

**File:** `app/core/domain_exceptions.py`

Created a comprehensive exception hierarchy that replaces `HTTPException` usage in service layers:

- **Base Exception:** `DomainException` - all domain exceptions inherit from this
- **Authentication Exceptions:** `AuthenticationError`, `InvalidCredentialsError`, `UserInactiveError`, `TokenExpiredError`, `TokenInvalidError`
- **Authorization Exceptions:** `AuthorizationError`, `InsufficientPermissionsError`, `NoSiteAccessError`, `SiteAccessDeniedError`
- **Resource Exceptions:** `ResourceNotFoundError`, `ResourceAlreadyExistsError`
- **Validation Exceptions:** `ValidationError`, `InvalidInputError`, `MissingRequiredFieldError`
- **Storage Exceptions:** `StorageError`, `StorageFullError`, `StorageConnectionError`, etc.
- **Photo Service Exceptions:** `PhotoServiceError`, `ImageProcessingError`, `UnsupportedImageFormatError`
- **Site Exceptions:** `SiteError`, `SiteNotFoundError`, `SiteAccessDeniedError`
- **Harris Matrix Exceptions:** `HarrisMatrixException`, `UnitCodeConflict`, `InvalidStratigraphicRelation`, `CycleDetectionError`

**Benefits:**
- Services no longer depend on FastAPI's HTTPException
- Clean separation between business logic and presentation layer
- Testable exceptions with consistent structure
- Automatic HTTP status code mapping

### 2. Centralized Exception Handlers

**File:** `app/core/exception_handlers.py`

Created centralized exception handlers that convert domain exceptions to appropriate HTTP responses:

- `domain_exception_handler`: Main handler for all domain exceptions
- `validation_exception_handler`: Handles Pydantic validation errors
- `generic_exception_handler`: Safety net for unexpected exceptions
- `register_exception_handlers()`: Registers all handlers with FastAPI app

**Features:**
- Automatic API vs Web route detection
- JSON responses for API routes
- Redirects for web routes (e.g., 401 → /login)
- Comprehensive error logging with context
- Consistent error response format

### 3. Services Converted to Use Domain Exceptions

**Files Modified:**
- `app/services/auth_service.py`
- `app/services/photo_service.py`
- `app/services/site_service.py`

**Changes:**
- Removed `from fastapi import HTTPException`
- Replaced `raise HTTPException(...)` with domain exceptions
- Services now raise domain-specific exceptions

**Example:**

```python
# BEFORE
raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Utente non ha accesso a nessun sito archeologico"
)

# AFTER
raise NoSiteAccessError(
    "Utente non ha accesso a nessun sito archeologico",
    details={
        "user_id": str(user.id),
        "user_email": user.email
    }
)
```

### 4. Dependency Injection Providers Created

**File:** `app/core/dependencies.py`

Created dependency injection providers for all core services:

- `get_database_session()`: Provides AsyncSession
- `get_auth_service()`: Provides AuthService
- `get_site_service()`: Provides SiteService
- `get_photo_metadata_service()`: Provides PhotoMetadataService
- `ServiceContainer`: Container for multiple services
- `get_services()`: Provides all services at once

**Usage Examples:**

```python
# Individual service injection
@router.post("/login")
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_database_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.authenticate_user(
        db, 
        credentials.email, 
        credentials.password
    )
    return await auth_service.create_login_response(db, user)

# Service container injection
@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_database_session),
    services: ServiceContainer = Depends(get_services),
    user_id: str = Depends(get_current_user_id)
):
    sites = await services.site_service.get_user_sites(db, user_id)
    return {"sites": sites}
```

### 5. Exception Handlers Registered in App

**File:** `app/app.py`

- Imported `register_exception_handlers` from `app.core.exception_handlers`
- Called `register_exception_handlers(app)` after FastAPI app creation
- Legacy HTTPException handler kept for backward compatibility

## 🚧 Next Steps (TODO)

### Task 5: Update Routes to Use Depends()

**What to do:** Update route functions to use dependency injection instead of manual service instantiation.

**Example Route Refactoring:**

```python
# BEFORE - Manual instantiation
@router.post("/api/v1/auth/login")
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Service instantiated inside route
    auth_service = AuthService()
    user = await auth_service.authenticate_user(db, credentials.email, credentials.password)
    return await auth_service.create_login_response(db, user)

# AFTER - Dependency injection
@router.post("/api/v1/auth/login")
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_database_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Service injected via Depends()
    user = await auth_service.authenticate_user(db, credentials.email, credentials.password)
    return await auth_service.create_login_response(db, user)
```

**Files to update:**
- `app/routes/api/v1/auth.py`
- `app/routes/api/v1/photos.py`
- `app/routes/api/v1/sites.py`
- `app/routes/api/v1/admin.py`
- All other route files that instantiate services manually

### Task 6: Remove Manual Service Instantiation

**What to do:** Search for patterns like `service = SomeService()` in routes and replace with dependency injection.

**Search patterns:**
```python
# Bad patterns to find and fix:
AuthService()
SiteService()
PhotoService()
UserService()
```

### Task 7: Move Business Logic from Routes to Services

**Current issue:** Some routes in `app/routes/api/v1/auth.py` contain business logic that should be in `AuthService`.

**Example refactoring:**

```python
# BEFORE - Logic in route
@router.post("/register")
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # All this logic should be in AuthService
    existing_user = await db.execute(select(User).where(User.email == user_data.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(user_data.password)
    new_user = User(email=user_data.email, hashed_password=hashed_password)
    db.add(new_user)
    await db.commit()
    return {"user_id": new_user.id}

# AFTER - Logic in service, thin route
@router.post("/register")
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_database_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Route delegates to service
    user = await auth_service.register_user(db, user_data)
    return {"user_id": user.id}

# AuthService gains new method:
async def register_user(
    db: AsyncSession,
    user_data: UserCreate
) -> User:
    """Register a new user."""
    # Check if user exists
    existing_user = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if existing_user.scalar_one_or_none():
        raise ResourceAlreadyExistsError(
            "User",
            user_data.email,
            details={"email": user_data.email}
        )
    
    # Create user
    hashed_password = SecurityService.hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_password
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user
```

### Task 8: Move Photo Upload Logic to Service Layer

**Current issue:** Photo upload logic scattered across routes.

**What to do:** Consolidate photo upload, thumbnail generation, and metadata extraction into `PhotoService`.

### Task 9: Use Pydantic Schemas for Request Validation

**What to do:** Ensure all API endpoints use Pydantic models for request validation instead of manual parsing.

**Example:**

```python
# BEFORE - Manual form parsing
@router.post("/update-user")
async def update_user(
    first_name: str = Form(None),
    last_name: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    # Manual validation
    if not first_name:
        raise HTTPException(status_code=400, detail="First name required")
    # ...

# AFTER - Pydantic schema
class UserUpdateRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    
    @validator('first_name')
    def validate_first_name(cls, v):
        if not v or not v.strip():
            raise ValueError('First name is required')
        return v.strip()

@router.post("/update-user")
async def update_user(
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_database_session)
):
    # Pydantic handles validation automatically
    # ...
```

### Task 10: Test the Refactored Code

**What to test:**
1. Exception handling - verify domain exceptions are caught and converted to proper HTTP responses
2. Dependency injection - ensure services are properly injected
3. API endpoints - test all refactored endpoints
4. Error responses - verify consistent error format
5. Logging - check that errors are logged with proper context

**Test approach:**
```bash
# Run tests
pytest app/tests/

# Check specific areas
pytest app/tests/test_auth.py
pytest app/tests/test_exceptions.py
pytest app/tests/test_services.py
```

## Migration Checklist

### For Each Route File:

- [ ] Add imports for dependencies:
  ```python
  from app.core.dependencies import (
      get_database_session,
      get_auth_service,
      get_site_service,
      get_photo_metadata_service,
      get_services
  )
  ```

- [ ] Replace manual service instantiation with `Depends()`:
  ```python
  # BEFORE
  service = AuthService()
  
  # AFTER
  auth_service: AuthService = Depends(get_auth_service)
  ```

- [ ] Move business logic to service layer

- [ ] Use Pydantic schemas for request validation

- [ ] Remove HTTPException imports if no longer needed

- [ ] Update exception handling to use domain exceptions

- [ ] Test the endpoint

### For Each Service File:

- [ ] Import domain exceptions from `app.core.domain_exceptions`

- [ ] Replace `HTTPException` with appropriate domain exception

- [ ] Ensure methods accept `db: AsyncSession` as parameter (not `self.db`)

- [ ] Add proper logging with structured context

- [ ] Add type hints to all methods

- [ ] Document exceptions in docstrings

## Architecture Benefits

### Before Refactoring:
```
Route → Creates Service → Service raises HTTPException → FastAPI handles
```
**Problems:**
- Services depend on FastAPI (coupling)
- Can't test services without FastAPI
- Inconsistent error handling
- Business logic in routes

### After Refactoring:
```
Route (depends on Service) → Service raises DomainException → 
Centralized Handler converts to HTTP → FastAPI returns response
```
**Benefits:**
- Services are framework-agnostic
- Easy to test services independently
- Consistent error handling and logging
- Thin routes, fat services
- Clear separation of concerns

## Code Style Guidelines

### Services:
```python
# ✅ GOOD
class AuthService:
    @staticmethod
    async def authenticate_user(
        db: AsyncSession,  # ← db as parameter
        email: str,
        password: str
    ) -> Optional[User]:
        """Authenticate user with email and password."""
        try:
            # Business logic here
            ...
        except SomeException as e:
            logger.error("Auth failed", exc_info=True)
            raise InvalidCredentialsError("Invalid email or password")

# ❌ BAD
class AuthService:
    def __init__(self, db):
        self.db = db  # ← Don't store db in self
    
    async def authenticate_user(self, email, password):
        # Missing type hints, no docstring
        raise HTTPException(...)  # ← Don't raise HTTPException
```

### Routes:
```python
# ✅ GOOD
@router.post("/login")
async def login(
    credentials: LoginRequest,  # ← Pydantic schema
    db: AsyncSession = Depends(get_database_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Login endpoint."""
    # Thin route - delegates to service
    user = await auth_service.authenticate_user(
        db, 
        credentials.email, 
        credentials.password
    )
    return await auth_service.create_login_response(db, user)

# ❌ BAD
@router.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    # Missing dependency injection
    # Manual form parsing instead of Pydantic
    # Business logic in route
    service = AuthService()  # ← Manual instantiation
    if not email:
        raise HTTPException(...)  # ← Manual validation
    # ... more logic in route
```

## Additional Resources

- FastAPI Dependency Injection: https://fastapi.tiangolo.com/tutorial/dependencies/
- Pydantic Validation: https://docs.pydantic.dev/latest/
- Clean Architecture: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html

## Questions or Issues?

If you encounter any issues during refactoring:

1. Check the examples in this guide
2. Look at already refactored files (`auth_service.py`, `site_service.py`)
3. Verify exception mappings in `domain_exceptions.py`
4. Check dependency providers in `dependencies.py`
5. Test with `pytest` after each change

## Summary

The P0 refactoring establishes a solid foundation for clean architecture:

✅ **Domain exceptions** - Services are framework-agnostic
✅ **Centralized handlers** - Consistent error handling
✅ **Dependency injection** - Testable, maintainable code
🚧 **Route refactoring** - Next step: update all routes
🚧 **Service layer** - Next step: move logic from routes
🚧 **Validation** - Next step: use Pydantic everywhere

This refactoring improves:
- **Testability**: Services can be tested without FastAPI
- **Maintainability**: Clear separation of concerns
- **Consistency**: Standardized error handling and responses
- **Scalability**: Easy to add new services and exceptions
- **Documentation**: Self-documenting exception hierarchy