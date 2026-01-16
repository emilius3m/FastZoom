# Design Patterns in the Archaeological Catalog System

This document describes the main design patterns used in the archaeological catalog system built with FastAPI. The patterns are organized by their architectural purpose and layer to provide a clearer understanding of how they work together.

---

## Table of Contents

1. [Core Architectural Patterns](#core-architectural-patterns)
2. [Data Access Patterns](#data-access-patterns)
3. [Business Logic Patterns](#business-logic-patterns)
4. [API & Presentation Patterns](#api--presentation-patterns)
5. [Cross-Cutting Concerns](#cross-cutting-concerns)
6. [Benefits Summary](#benefits-summary)

---

## Core Architectural Patterns

These patterns form the foundation of the application architecture and define the overall structure.

### 1. Model-View-Controller (MVC) / Model-View-Template (MVT)

The application follows a variation of the MVC pattern with clear separation between data models, business logic, and presentation.

#### Components
- **Models**: SQLAlchemy ORM models in `app/models/`
- **Views/Templates**: HTML templates in `app/templates/`
- **Controllers**: API routes in `app/routes/`

#### Key Features
- Clear separation of concerns
- Reusable components
- Maintainable code structure

#### Architecture Flow
```
Client Request → Routes (Controllers) → Services → Repositories → Database
                      ↓                      ↓
                Templates              Pydantic Schemas
                      ↓                      ↓
                HTML Response           JSON Response
```

### 2. Multi-Site Architecture Pattern

The application supports multiple archaeological sites with site-based permissions, enabling multi-tenancy.

#### Implementation
- Site-based permission system
- User-site relationship management
- Multi-tenancy support

#### Key Features
- Site isolation
- Permission management per site
- Scalable multi-site support

#### Data Flow
```
User Request → Site Identification → Permission Check → Site-Specific Data Access
```

---

## Data Access Patterns

These patterns handle how the application interacts with the database and manages data persistence.

### 3. Repository Pattern

The Repository Pattern separates the logic that retrieves data from the data source from the business logic that uses the data.

#### Implementation
- Located in `app/repositories/` directory
- Base repository class defined in `app/repositories/base.py`
- Specific repositories for different entities (e.g., `geographic_maps.py`, `iccd_records.py`)

#### Key Features
- Generic CRUD operations in the base repository
- Type safety with generics and Pydantic models
- Asynchronous database operations
- Filtering, pagination, and sorting capabilities

#### Example Usage
```python
class BaseRepository(Generic[ModelType]):
    def __init__(self, db_session: AsyncSession, model: Type[ModelType]):
        self.db_session = db_session
        self.model = model

    async def get(self, id: UUID) -> Optional[ModelType]:
        query = select(self.model).where(self.model.id == id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(self, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        query = select(self.model).offset(skip).limit(limit)
        result = await self.db_session.execute(query)
        return result.scalars().all()
```

#### Repository Hierarchy
```
BaseRepository (Generic CRUD)
    ├── GeographicMapRepository
    ├── ICCDRecordRepository
    ├── PhotoRepository
    └── GiornaleRepository
```

### 4. Database Session Management

Asynchronous database sessions are managed through a factory pattern with proper lifecycle management.

#### Implementation
- Asynchronous SQLAlchemy sessions
- Session factory using `async_sessionmaker`
- Dependency injection for session management

#### Key Features
- Asynchronous operations
- Connection pooling
- Automatic session lifecycle management

#### Session Lifecycle
```
Request → Session Created → Transaction → Commit/Rollback → Session Closed
```

### 5. Factory Pattern

Factory functions create service instances with their dependencies, providing clean object instantiation.

#### Implementation
- Service factory functions
- Repository instantiation within services
- Dependency injection for complex object creation

#### Key Features
- Decoupled object creation
- Dependency management
- Testability

#### Example
```python
def get_geographic_map_service(db: AsyncSession = Depends(get_async_session)) -> GeographicMapService:
    return GeographicMapService(db)
```

---

## Business Logic Patterns

These patterns encapsulate and manage the business rules and application logic.

### 6. Service Layer Pattern

The Service Layer encapsulates the business logic, coordinates operations between repositories, handles business rules, and manages transactions.

#### Implementation
- Located in `app/services/` directory
- Each service corresponds to a specific domain or functionality
- Services use repositories to access data

#### Key Features
- Business logic separation from data access and presentation
- Transaction management
- Validation and business rule enforcement
- Error handling and logging

#### Example Usage
```python
class GeographicMapService:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.repository = GeographicMapRepository(db_session)

    async def get_site_maps(self, site_id: UUID, current_user_id: UUID) -> List[Dict[str, Any]]:
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Read permissions required", 403)
        
        maps = await self.repository.get_site_maps(site_id)
        # Process and return data
        return maps_data
```

#### Service Responsibilities
- Business rule validation
- Transaction coordination
- Permission checking
- Data transformation
- Error handling

### 7. Exception Handling Pattern

Custom exception handling provides consistent error responses throughout the application.

#### Implementation
- Custom exception classes in `app/exceptions/`
- Global exception handlers in `app/core/exception_handlers.py`
- Business logic error handling

#### Key Features
- Consistent error format
- Proper HTTP status codes
- Detailed error messages

#### Exception Hierarchy
```
Exception
    ├── BusinessLogicError
    ├── PermissionError
    ├── ValidationError
    └── NotFoundError
```

---

## API & Presentation Patterns

These patterns manage how the application exposes its functionality to external consumers.

### 8. API Layer Pattern

The API layer provides a clean separation between the external interface and internal business logic.

#### Implementation
- API routes separated in `app/routes/api/`
- Consistent request/response handling
- Error handling and validation

#### Key Features
- RESTful API design
- Consistent error responses
- Authentication and authorization

#### API Structure
```
/api/v1/
    ├── auth/          # Authentication endpoints
    ├── sites/         # Site management
    ├── geographic/    # Geographic maps
    ├── iccd/          # ICCD records
    ├── harris_matrix/ # Harris matrix operations
    ├── documents/     # Document management
    └── ...
```

### 9. Dependency Injection

FastAPI's built-in dependency injection system manages and provides dependencies to different parts of the application.

#### Implementation
- FastAPI dependency functions
- Session management through dependency injection
- Security functions as dependencies

#### Key Features
- Automatic dependency resolution
- Lifecycle management of dependencies
- Testability through dependency substitution

#### Example Usage
```python
@geographic_maps_router.get("/sites/{site_id}/maps")
async def get_site_geographic_maps(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    # Implementation
```

#### Dependency Chain
```
Request → get_current_user_id → get_async_session → get_geographic_map_service → Handler
```

---

## Cross-Cutting Concerns

These patterns address concerns that span multiple layers of the application.

### 10. Configuration Pattern

The configuration pattern provides a centralized way to manage application settings.

#### Implementation
- Pydantic Settings model in `app/core/config.py`
- Environment-based configuration loading
- Caching for performance

#### Key Features
- Type-safe configuration
- Environment variable support
- Validation of configuration values

#### Configuration Categories
- Database settings
- Security settings (JWT, secrets)
- Storage settings (MinIO)
- CORS settings
- Application settings

### 11. Security Pattern

The application implements comprehensive security measures including authentication and authorization.

#### Components
- JWT-based authentication
- Token blacklist management
- Role-based access control
- CSRF protection

#### Key Features
- Secure token management
- Session invalidation
- Permission checking
- Multi-site access control

#### Security Layers
```
1. Authentication (JWT tokens)
2. Authorization (Role-based + Site-based)
3. CSRF Protection
4. Input Validation
5. SQL Injection Prevention (ORM)
```

---

## Benefits Summary

### Architectural Benefits

1. **Maintainability**: Clear separation of concerns makes the code easier to maintain and understand
2. **Testability**: Dependencies can be easily mocked for unit testing
3. **Scalability**: Architecture supports growth and additional features
4. **Reusability**: Components can be reused across different parts of the application

### Operational Benefits

5. **Security**: Built-in security patterns protect against common vulnerabilities
6. **Performance**: Asynchronous operations and caching improve performance
7. **Reliability**: Proper error handling and transaction management ensure data consistency
8. **Flexibility**: Easy to modify or extend functionality without affecting other components

### Developer Experience

9. **Clear Code Structure**: Logical organization makes navigation easier
10. **Type Safety**: Strong typing with Pydantic and generics
11. **Consistent Patterns**: Once learned, patterns apply across the entire codebase
12. **Easy Debugging**: Clear separation helps isolate issues quickly

---

## Pattern Interactions

### Request Flow Example

```
1. Client sends request to /api/v1/sites/{id}/maps
2. Dependency Injection resolves:
   - get_current_user_id → validates JWT
   - get_async_session → creates DB session
   - get_geographic_map_service → creates service with repository
3. Route handler calls service method
4. Service checks permissions (Security Pattern)
5. Service calls repository (Repository Pattern)
6. Repository executes query (Database Session Management)
7. Data flows back through layers
8. Exception caught if any (Exception Handling Pattern)
9. Response formatted and returned (API Layer Pattern)
```

### Layer Responsibilities

| Layer | Pattern | Responsibility |
|-------|---------|----------------|
| Presentation | MVC/MVT, API Layer | Handle HTTP requests/responses |
| Business Logic | Service Layer, Exception Handling | Implement business rules |
| Data Access | Repository, Database Session | Manage database operations |
| Infrastructure | Configuration, Security, DI | Provide cross-cutting services |

---

## Best Practices

1. **Always use repositories** for data access, never query directly from routes
2. **Keep services thin** - business logic in services, data access in repositories
3. **Use dependency injection** for all dependencies to enable testing
4. **Validate inputs** at the route level using Pydantic models
5. **Handle exceptions** at the appropriate layer with custom exception classes
6. **Follow the repository hierarchy** when creating new data access patterns
7. **Maintain separation** - don't mix concerns across layers
8. **Document patterns** when introducing new design patterns to the codebase

---

## Related Documentation

- [REFACTORING_GUIDE.md](REFACTORING_GUIDE.md) - Refactoring guidelines and patterns
- [ER_DIAGRAM_COMPLETE.md](ER_DIAGRAM_COMPLETE.md) - Database schema and relationships
- [README.md](README.md) - Project overview and setup instructions
