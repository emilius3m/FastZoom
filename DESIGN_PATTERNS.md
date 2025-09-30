# Design Patterns in the Archaeological Catalog System

This document describes the main design patterns used in the archaeological catalog system built with FastAPI.

## 1. Repository Pattern

The Repository Pattern is implemented to separate the logic that retrieves data from the data source from the business logic that uses the data. This pattern provides a clean, testable, and maintainable way to access data.

### Implementation
- Located in `app/repositories/` directory
- Base repository class defined in `app/repositories/base.py`
- Specific repositories for different entities (e.g., `geographic_maps.py`, `iccd_records.py`)

### Key Features
- Generic CRUD operations in the base repository
- Type safety with generics and Pydantic models
- Asynchronous database operations
- Filtering, pagination, and sorting capabilities

### Example Usage
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

## 2. Service Layer Pattern

The Service Layer Pattern encapsulates the business logic of the application. It coordinates operations between repositories, handles business rules, and manages transactions.

### Implementation
- Located in `app/services/` directory
- Each service corresponds to a specific domain or functionality
- Services use repositories to access data

### Key Features
- Business logic separation from data access and presentation
- Transaction management
- Validation and business rule enforcement
- Error handling and logging

### Example Usage
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

## 3. Dependency Injection

FastAPI's built-in dependency injection system is used to manage and provide dependencies to different parts of the application.

### Implementation
- FastAPI dependency functions
- Session management through dependency injection
- Security functions as dependencies

### Key Features
- Automatic dependency resolution
- Lifecycle management of dependencies
- Testability through dependency substitution

### Example Usage
```python
def get_geographic_map_service(db: AsyncSession = Depends(get_async_session)) -> GeographicMapService:
    return GeographicMapService(db)

@geographic_maps_router.get("/sites/{site_id}/maps")
async def get_site_geographic_maps(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    # Implementation
```

## 4. Model-View-Controller (MVC) / Model-View-Template (MVT)

The application follows a variation of the MVC pattern with clear separation between data models, business logic, and presentation.

### Components
- **Models**: SQLAlchemy ORM models in `app/models/`
- **Views/Templates**: HTML templates in `app/templates/`
- **Controllers**: API routes in `app/routes/`

### Key Features
- Clear separation of concerns
- Reusable components
- Maintainable code structure

## 5. API Layer Pattern

The API layer provides a clean separation between the external interface and internal business logic.

### Implementation
- API routes separated in `app/routes/api/`
- Consistent request/response handling
- Error handling and validation

### Key Features
- RESTful API design
- Consistent error responses
- Authentication and authorization

## 6. Configuration Pattern

The configuration pattern provides a centralized way to manage application settings.

### Implementation
- Pydantic Settings model in `app/core/config.py`
- Environment-based configuration loading
- Caching for performance

### Key Features
- Type-safe configuration
- Environment variable support
- Validation of configuration values

## 7. Security Pattern

The application implements comprehensive security measures including authentication and authorization.

### Components
- JWT-based authentication
- Token blacklist management
- Role-based access control
- CSRF protection

### Key Features
- Secure token management
- Session invalidation
- Permission checking
- Multi-site access control

## 8. Database Session Management

Asynchronous database sessions are managed through a factory pattern with proper lifecycle management.

### Implementation
- Asynchronous SQLAlchemy sessions
- Session factory using `async_sessionmaker`
- Dependency injection for session management

### Key Features
- Asynchronous operations
- Connection pooling
- Automatic session lifecycle management

## 9. Exception Handling Pattern

Custom exception handling provides consistent error responses throughout the application.

### Implementation
- Custom exception classes
- Global exception handlers
- Business logic error handling

### Key Features
- Consistent error format
- Proper HTTP status codes
- Detailed error messages

## 10. Factory Pattern

Factory functions create service instances with their dependencies.

### Implementation
- Service factory functions
- Repository instantiation within services
- Dependency injection for complex object creation

### Key Features
- Decoupled object creation
- Dependency management
- Testability

## 11. Multi-Site Architecture Pattern

The application supports multiple archaeological sites with site-based permissions.

### Implementation
- Site-based permission system
- User-site relationship management
- Multi-tenancy support

### Key Features
- Site isolation
- Permission management per site
- Scalable multi-site support

## Benefits of These Patterns

1. **Maintainability**: Clear separation of concerns makes the code easier to maintain
2. **Testability**: Dependencies can be easily mocked for unit testing
3. **Scalability**: Architecture supports growth and additional features
4. **Reusability**: Components can be reused across different parts of the application
5. **Security**: Built-in security patterns protect against common vulnerabilities
6. **Performance**: Asynchronous operations and caching improve performance