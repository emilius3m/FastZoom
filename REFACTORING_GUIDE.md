# FastZoom Comprehensive Refactoring Guide

## Overview

This guide provides comprehensive refactoring guidelines for the FastZoom archaeological documentation system. It covers architecture improvements, code organization, best practices, and migration strategies.

## Current Architecture Status

### ✅ Completed Refactoring

1. **Domain Exception Hierarchy** (`app/core/domain_exceptions.py`)
   - Comprehensive exception classes replacing HTTPException usage
   - Automatic HTTP status code mapping
   - Structured error details with context

2. **Centralized Exception Handlers** (`app/core/exception_handlers.py`)
   - API vs Web route detection
   - JSON responses for API routes
   - Redirects for web routes
   - Comprehensive error logging

3. **Dependency Injection System** (`app/core/dependencies.py`)
   - Service providers for all core services
   - Database session management
   - Service container for multiple services

4. **Service Layer Architecture**
   - `AuthService`: Authentication and user management
   - `SiteService`: Site CRUD and permissions
   - `PhotoService`: Photo upload and metadata
   - `PhotoMetadataService`: Metadata management

### 🚧 In Progress

- Route refactoring to use dependency injection
- Business logic migration from routes to services

### 📋 TODO

- Complete Pydantic schema adoption
- Move remaining business logic to services
- Comprehensive test coverage

## Architecture Principles

### Clean Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Presentation Layer                    │
│  (Routes, View Templates, API Responses)         │
├─────────────────────────────────────────────────────────────┤
│                   Application Layer                    │
│  (Services, Business Logic, Validation)            │
├─────────────────────────────────────────────────────────────┤
│                   Domain Layer                          │
│  (Models, Domain Exceptions, Business Rules)         │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                   │
│  (Database, Storage, External APIs)                 │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**Presentation Layer (`app/routes/`)**
- Handle HTTP requests/responses
- Input validation (Pydantic schemas)
- Call services for business logic
- Format responses (JSON/HTML)
- **DO NOT**: Direct database access, business logic

**Application Layer (`app/services/`)**
- Implement business logic
- Orchestrate domain operations
- Handle transactions
- Validate business rules
- **DO NOT**: Handle HTTP, format responses

**Domain Layer (`app/models/`, `app/core/domain_exceptions.py`)**
- Define data structures
- Domain-specific exceptions
- Business rules validation
- **DO NOT**: Know about HTTP, database

**Infrastructure Layer (`app/database/`, `app/core/`)**
- Database operations
- External API clients
- Configuration management
- Security utilities

## Refactoring Guidelines

### 1. Route Refactoring

#### Before (Anti-Pattern)
```python
# ❌ BAD: Manual service instantiation
@router.post("/login")
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Service instantiated inside route
    auth_service = AuthService()
    user = await auth_service.authenticate_user(db, credentials.email, credentials.password)
    
    # Business logic in route
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Manual validation
    if not credentials.email:
        raise HTTPException(status_code=400, detail="Email required")
    
    return await auth_service.create_login_response(db, user)
```

#### After (Best Practice)
```python
# ✅ GOOD: Dependency injection + Pydantic validation
@router.post("/api/v1/auth/login")
async def login(
    credentials: LoginRequest,  # Pydantic handles validation
    db: AsyncSession = Depends(get_database_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Route delegates to service
    user = await auth_service.authenticate_user(
        db, 
        credentials.email, 
        credentials.password
    )
    return await auth_service.create_login_response(db, user)
```

#### Route Refactoring Checklist

For each route file:

- [ ] Import dependencies from `app.core.dependencies`
- [ ] Remove manual service instantiation
- [ ] Use Pydantic schemas for request validation
- [ ] Remove `raise HTTPException` (use domain exceptions)
- [ ] Remove business logic from routes
- [ ] Keep routes thin (delegation only)

### 2. Service Layer Guidelines

#### Service Structure
```python
# ✅ GOOD: Framework-agnostic service
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
        except InvalidCredentials as e:
            logger.error("Auth failed", exc_info=True)
            raise InvalidCredentialsError(
                "Invalid email or password",
                details={"email": email}
            )
```

#### Service Checklist

For each service file:

- [ ] Import domain exceptions from `app.core.domain_exceptions`
- [ ] Accept `db: AsyncSession` as parameter (don't store in `self`)
- [ ] Use `@staticmethod` for stateless methods
- [ ] Add comprehensive docstrings
- [ ] Add type hints to all methods
- [ ] Add structured logging with context
- [ ] **DO NOT**: Import `fastapi.HTTPException`

### 3. Exception Handling

#### Domain Exception Hierarchy

```python
# Base exception
class DomainException(Exception):
    """Base exception for all domain errors."""
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

# Specific exceptions
class AuthenticationError(DomainException):
    """Authentication-related errors."""
    pass

class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials provided."""
    http_status = 401

class ResourceNotFoundError(DomainException):
    """Resource not found."""
    http_status = 404

class ValidationError(DomainException):
    """Validation errors."""
    http_status = 400
```

#### Exception Handler Pattern

```python
# Centralized handler
async def domain_exception_handler(request: Request, exc: DomainException):
    """Handle all domain exceptions."""
    status_code = getattr(exc, 'http_status', 500)
    
    # API routes return JSON
    if request.url.path.startswith('/api/'):
        return JSONResponse(
            status_code=status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
                "details": exc.details
            }
        )
    
    # Web routes redirect
    else:
        return RedirectResponse(url='/login', status_code=302)
```

### 4. Pydantic Schema Guidelines

#### Request Schemas
```python
# ✅ GOOD: Pydantic with validation
from pydantic import BaseModel, EmailStr, validator

class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    
    @validator('email')
    def email_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Email is required')
        return v.strip()
```

#### Schema Checklist

- [ ] All request data uses Pydantic schemas
- [ ] Add validators for complex rules
- [ ] Add field descriptions
- [ ] Use appropriate types (EmailStr, HttpUrl, etc.)
- [ ] Add `example` values for documentation
- [ ] Remove manual validation from routes

### 5. Database Operations

#### Best Practices
```python
# ✅ GOOD: Proper session handling
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email with proper session handling."""
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()

# ❌ BAD: Session stored in service
class BadService:
    def __init__(self, db: AsyncSession):
        self.db = db  # ← Don't do this
```

#### Database Checklist

- [ ] Accept `db: AsyncSession` as parameter
- [ ] Use `select()` with proper joins
- [ ] Use `scalar_one_or_none()` for optional results
- [ ] Handle transactions with `try/except/rollback`
- [ ] Use `selectinload()` for eager loading
- [ ] Add indexes for frequently queried fields

### 6. API Design Patterns

#### RESTful Conventions

```
GET    /api/v1/sites          - List all sites
GET    /api/v1/sites/{id}     - Get specific site
POST   /api/v1/sites          - Create new site
PUT    /api/v1/sites/{id}     - Update site
DELETE /api/v1/sites/{id}     - Delete site
```

#### Response Format
```python
# ✅ GOOD: Consistent response format
{
    "data": {...},        # Primary data
    "message": "...",      # Optional message
    "meta": {            # Metadata
        "page": 1,
        "total": 100,
        "filters": {...}
    }
}
```

## Migration Strategy

### Phase 1: Foundation (Completed)
- ✅ Domain exceptions created
- ✅ Exception handlers registered
- ✅ Dependency injection system
- ✅ Service layer structure

### Phase 2: Routes (In Progress)
- 🔄 Update authentication routes
- 🔄 Update site routes
- 🔄 Update photo routes
- 🔄 Update user routes
- 🔄 Update admin routes

### Phase 3: Services (Pending)
- ⏳ Move business logic from routes
- ⏳ Add comprehensive logging
- ⏳ Add transaction handling
- ⏳ Add caching where appropriate

### Phase 4: Testing (Pending)
- ⏳ Unit tests for services
- ⏳ Integration tests for routes
- ⏳ Exception handler tests
- ⏳ End-to-end API tests

### Phase 5: Documentation (Pending)
- ⏳ Update API documentation
- ⏳ Add architecture diagrams
- ⏳ Document migration process
- ⏳ Create developer onboarding guide

## Code Style Guidelines

### Python Code Style

#### Naming Conventions
```python
# Classes: PascalCase
class AuthService:
    pass

# Functions/Methods: snake_case
async def authenticate_user():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_LOGIN_ATTEMPTS = 5

# Private members: _leading_underscore
class Service:
    def __init__(self):
        self._internal_value = None
```

#### Docstring Format
```python
def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """
    Get user by ID from database.
    
    Args:
        db: Database session
        user_id: User UUID to fetch
        
    Returns:
        User object if found, None otherwise
        
    Raises:
        ResourceNotFoundError: If user doesn't exist
    """
    result = await db.execute(
        select(User).where(User.id == str(user_id))
    )
    return result.scalar_one_or_none()
```

### Logging Guidelines

#### Structured Logging
```python
# ✅ GOOD: Structured logging
logger.info(
    "User authenticated successfully",
    extra={
        "user_id": str(user.id),
        "email": user.email,
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent")
    }
)

# ❌ BAD: Unstructured logging
logger.info(f"User {user.email} logged in from {ip}")
```

#### Log Levels
- **DEBUG**: Detailed diagnostic information
- **INFO**: Normal operation flow
- **WARNING**: Unexpected but recoverable situations
- **ERROR**: Errors that don't stop execution
- **CRITICAL**: Errors that require immediate attention

## Performance Guidelines

### Database Optimization

#### Query Optimization
```python
# ✅ GOOD: Indexed queries
async def get_user_sites(db: AsyncSession, user_id: UUID) -> List[Site]:
    """Get user sites with indexed query."""
    result = await db.execute(
        select(Site)
        .join(UserSitePermission)
        .where(UserSitePermission.user_id == str(user_id))
        .where(UserSitePermission.is_active == True)
        .options(selectinload(Site.creator))  # Eager load
    )
    return result.scalars().all()

# ❌ BAD: N+1 queries
for permission in user.permissions:
    site = await get_site_by_id(db, permission.site_id)  # ← N queries
```

#### Caching Strategy
```python
# Cache frequently accessed data
@lru_cache(maxsize=100)
async def get_site_config(site_id: UUID) -> dict:
    """Get site configuration with caching."""
    return await load_config_from_db(site_id)
```

### API Performance

#### Pagination
```python
# ✅ GOOD: Pagination with limits
@router.get("/api/v1/sites")
async def list_sites(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_database_session)
):
    """List sites with pagination."""
    offset = (page - 1) * per_page
    result = await db.execute(
        select(Site)
        .offset(offset)
        .limit(per_page)
        .order_by(Site.created_at.desc())
    )
    sites = result.scalars().all()
    
    return {
        "data": sites,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": len(sites)
        }
    }
```

## Security Guidelines

### Input Validation
```python
# ✅ GOOD: Pydantic validation
from pydantic import BaseModel, Field, validator

class CreateSiteRequest(BaseModel):
    """Create site request with validation."""
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=50)
    coordinates_lat: Optional[float] = Field(None, ge=-90, le=90)
    coordinates_lng: Optional[float] = Field(None, ge=-180, le=180)
    
    @validator('code')
    def code_must_be_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError('Code must be alphanumeric')
        return v.upper()
```

### Authorization
```python
# ✅ GOOD: Permission checks via dependency
async def check_site_admin(
    site_id: UUID,
    user_id: UUID,
    db: AsyncSession
) -> bool:
    """Check if user has admin access to site."""
    permission = await db.execute(
        select(UserSitePermission).where(
            and_(
                UserSitePermission.site_id == str(site_id),
                UserSitePermission.user_id == str(user_id),
                UserSitePermission.permission_level == "admin",
                UserSitePermission.is_active == True
            )
        )
    )
    return permission.scalar_one_or_none() is not None

# Usage in route
@router.delete("/api/v1/sites/{site_id}")
async def delete_site(
    site_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database_session)
):
    """Delete site with permission check."""
    if not await check_site_admin(site_id, user_id, db):
        raise InsufficientPermissionsError(
            "Admin access required",
            details={"site_id": str(site_id)}
        )
    # ... deletion logic
```

## Testing Guidelines

### Unit Tests
```python
# ✅ GOOD: Isolated unit test
import pytest
from app.services.auth_service import AuthService
from app.core.domain_exceptions import InvalidCredentialsError

@pytest.mark.asyncio
async def test_authenticate_user_success(db_session):
    """Test successful authentication."""
    # Setup
    user = await create_test_user(db_session, email="test@example.com", password="password123")
    
    # Execute
    result = await AuthService.authenticate_user(
        db_session, 
        "test@example.com", 
        "password123"
    )
    
    # Assert
    assert result is not None
    assert result.email == "test@example.com"

@pytest.mark.asyncio
async def test_authenticate_user_invalid_password(db_session):
    """Test authentication with invalid password."""
    with pytest.raises(InvalidCredentialsError):
        await AuthService.authenticate_user(
            db_session, 
            "test@example.com", 
            "wrongpassword"
        )
```

### Integration Tests
```python
# ✅ GOOD: API integration test
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_login_success():
    """Test login endpoint."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "password123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "user" in data
```

## Migration Checklist

### For Each Route File

- [ ] Import dependencies from `app.core.dependencies`
- [ ] Remove manual service instantiation
- [ ] Use Pydantic schemas for validation
- [ ] Replace `HTTPException` with domain exceptions
- [ ] Move business logic to services
- [ ] Add type hints
- [ ] Add docstrings
- [ ] Add logging
- [ ] Write unit tests

### For Each Service File

- [ ] Import domain exceptions
- [ ] Accept `db` as parameter
- [ ] Use `@staticmethod` where appropriate
- [ ] Add comprehensive docstrings
- [ ] Add type hints
- [ ] Add structured logging
- [ ] Handle transactions properly
- [ ] Write unit tests

## Common Anti-Patterns to Avoid

### 1. Manual Service Instantiation
```python
# ❌ BAD
@router.post("/create")
async def create(db: AsyncSession = Depends(get_db)):
    service = SomeService()  # ← New instance every request
    return await service.create(db)
```

### 2. Business Logic in Routes
```python
# ❌ BAD
@router.post("/create")
async def create(data: CreateRequest, db: AsyncSession = Depends(get_db)):
    # Business logic in route
    if data.type == "special":
        if not has_permission():
            raise HTTPException(403, "No permission")
    # More logic...
    return await create_item(db, data)
```

### 3. HTTPException in Services
```python
# ❌ BAD
class SomeService:
    async def do_something(self, db):
        if not item:
            raise HTTPException(404, "Not found")  # ← Wrong layer
```

### 4. Direct Database Access in Routes
```python
# ❌ BAD
@router.get("/items/{id}")
async def get_item(id: str, db: AsyncSession = Depends(get_db)):
    # Direct DB access in route
    item = await db.execute(select(Item).where(Item.id == id))
    return item.scalar_one_or_none()
```

### 5. Session Storage in Services
```python
# ❌ BAD
class BadService:
    def __init__(self, db: AsyncSession):
        self.db = db  # ← Stores session in instance
```

## Best Practices Summary

### ✅ DO

- Use dependency injection for services
- Use Pydantic for validation
- Raise domain exceptions in services
- Accept `db` as parameter in services
- Use `@staticmethod` for stateless methods
- Add comprehensive docstrings
- Add type hints everywhere
- Use structured logging
- Write unit tests for all services
- Follow RESTful conventions
- Use proper HTTP status codes

### ❌ DON'T

- Don't instantiate services manually in routes
- Don't put business logic in routes
- Don't raise `HTTPException` in services
- Don't store `db` in service instances
- Don't use `raise HTTPException` directly
- Don't skip validation
- Don't ignore type hints
- Don't use unstructured logging
- Don't skip tests
- Don't break RESTful conventions

## Additional Resources

### Documentation
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/14/orm/extensions/asyncio/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)

### Architecture Patterns
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repositoryPattern.html)

## Questions or Issues?

If you encounter any issues during refactoring:

1. Check examples in this guide
2. Look at already refactored files (`auth_service.py`, `site_service.py`)
3. Verify exception mappings in `domain_exceptions.py`
4. Check dependency providers in `dependencies.py`
5. Test with `pytest` after each change

## Summary

This refactoring guide establishes a solid foundation for clean, maintainable, and testable code:

✅ **Domain exceptions** - Framework-agnostic error handling
✅ **Centralized handlers** - Consistent error responses
✅ **Dependency injection** - Testable, maintainable code
✅ **Service layer** - Business logic separation
🚧 **Route refactoring** - Next step: update all routes
⏳ **Testing** - Next step: comprehensive test coverage
⏳ **Documentation** - Next step: update all docs

This refactoring improves:
- **Testability**: Services can be tested without FastAPI
- **Maintainability**: Clear separation of concerns
- **Consistency**: Standardized error handling and responses
- **Scalability**: Easy to add new services and exceptions
- **Documentation**: Self-documenting exception hierarchy
