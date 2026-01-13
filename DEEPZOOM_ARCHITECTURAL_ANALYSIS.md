# DeepZoom API Architectural Analysis & Refactoring Plan

## Executive Summary

The file [`app/routes/api/v1/deepzoom.py`](app/routes/api/v1/deepzoom.py) implements Deep Zoom functionality for archaeological photos. While functional, it contains several architectural violations that deviate from the project's Clean Architecture principles and established patterns.

---

## Identified Architectural Issues

### 1. **Direct HTTPException Usage in Routes** (Critical)
**Location:** Lines 102, 108, 144, 151, 162, 354, 426, 451, 475, 502, 520

**Problem:**
```python
# Current (violates Clean Architecture)
if format not in ['jpg', 'png', 'jpeg']:
    raise HTTPException(status_code=400, detail="Formato tile non supportato")
```

**Why it's wrong:**
- Routes should not directly raise HTTPException
- This couples the presentation layer to HTTP details
- Violates separation of concerns
- Bypasses the centralized [`domain_exception_handler`](app/core/exception_handlers.py:21)

**Correct approach:**
```python
# Should use domain exceptions
from app.core.domain_exceptions import ValidationError
raise ValidationError("Formato tile non supportato", field="format")
```

---

### 2. **Duplicate Imports** (Minor)
**Location:** Lines 26 and 32

```python
from app.core.domain_exceptions import (
    InsufficientPermissionsError,  # Line 26
    ...
    InsufficientPermissionsError  # Line 32 - Duplicate!
)
```

---

### 3. **Missing Imports** (Critical)
**Location:** Lines 421, 422

```python
# Used but not imported
"timestamp": datetime.now(timezone.utc).isoformat()
```

Missing:
```python
from datetime import datetime
from datetime import timezone
```

---

### 4. **Manual Permission Checks in Routes** (Critical)
**Location:** Lines 304-308

```python
# Current - manual permission checking
perms = await require_site_permission(site_id, request, required_permission="read")
can_write = perms.get("can_write", False) or perms.get("is_superuser", False)

if auto_repair and not can_write:
    auto_repair = False
```

**Problem:**
- Business logic in routes
- Should be handled by service layer or dedicated permission dependency

**Correct approach:**
```python
# Let service handle permission logic
result = await deep_zoom_service.verify_and_repair(
    str(site_id), str(photo_id), current_user_id, auto_repair=auto_repair
)
# Service should raise InsufficientPermissionsError if needed
```

---

### 5. **Direct Background Service Calls** (Major)
**Location:** Lines 247, 391, 418, 445, 477, 504, 522

```python
# Current - bypasses service layer
queue_status = await deep_zoom_background_service.get_queue_status()
return await deep_zoom_background_service.get_health_status()
status_info = await tiles_verification_service.get_verification_status()
```

**Problem:**
- Routes directly calling background services
- Violates layered architecture
- Should go through [`DeepZoomService`](app/services/deep_zoom_service.py:23)

**Correct approach:**
```python
# Should delegate to service layer
queue_status = await deep_zoom_service.get_queue_status()
health_status = await deep_zoom_service.get_health_status()
```

---

### 6. **Schemas Defined in Routes** (Minor)
**Location:** Lines 38-54

```python
# Current - schemas in routes file
class DeepZoomConfig(BaseModel):
    max_levels: Optional[int] = None
    ...

class BatchProcessRequest(BaseModel):
    photo_ids: List[UUID]
    ...
```

**Problem:**
- Schemas should be in dedicated `app/routes/api/v1/schemas/deepzoom.py` or `app/schemas/deepzoom.py`
- Follows project convention (see other v1 routes)

---

### 7. **Inconsistent Error Handling** (Major)
**Problem:**
- Some routes use `raise HTTPException`
- Some routes let exceptions propagate
- No consistent pattern

**Example:**
```python
# Line 368 - catches exception but wraps in result
except Exception as e:
    results.append({"photo_id": str(photo_id), "status": DeepZoomStatus.ERROR.value, "error": str(e)})

# Line 426 - raises HTTPException
raise HTTPException(status_code=500, detail=f"Errore recupero stato verifica: {str(e)}")
```

---

### 8. **Missing Use of Domain Exceptions** (Major)
**Problem:**
- Domain exceptions are imported but not consistently used
- [`InsufficientPermissionsError`](app/core/domain_exceptions.py:77) is imported but `HTTPException` is used instead

**Example:**
```python
# Line 451 - Should use domain exception
raise InsufficientPermissionsError("Richiesto accesso Superuser per verifica globale")
# But line 475 uses HTTPException:
raise InsufficientPermissionsError("Richiesto accesso Superuser")
```

---

### 9. **Inline Import of Security Functions** (Minor)
**Location:** Lines 472, 499, 517

```python
# Importing inside route handler
from app.core.security import get_current_user_with_superuser_check
```

**Problem:**
- Imports should be at module level
- Affects performance and readability

---

### 10. **Response Formatting in Routes** (Minor)
**Location:** Lines 200-204, 258-263

```python
# Current - manual response construction
return JSONResponse({
    "message": "Deep zoom processing avviato",
    "photo_id": str(photo_id),
    "task_info": result
})
```

**Problem:**
- Response schemas should be defined
- Allows for OpenAPI documentation
- Type safety

---

## Refactoring Plan

### Phase 1: Fix Critical Issues
1. Add missing imports (`datetime`, `timezone`)
2. Remove duplicate import (`InsufficientPermissionsError`)
3. Replace all `HTTPException` with appropriate domain exceptions

### Phase 2: Extract Schemas
1. Create `app/routes/api/v1/schemas/deepzoom.py`
2. Move all Pydantic models to schemas file
3. Import schemas in routes

### Phase 3: Centralize Permission Handling
1. Remove manual permission checks from routes
2. Use centralized dependencies from [`security.py`](app/core/security.py:660)
3. Let service layer handle permission logic

### Phase 4: Service Layer Improvements
1. Add missing methods to [`DeepZoomService`](app/services/deep_zoom_service.py:23):
   - `get_queue_status()`
   - `get_health_status()`
   - `process_missing_tiles()`
2. Remove direct background service calls from routes

### Phase 5: Response Schemas
1. Define response schemas for all endpoints
2. Use Pydantic models for responses
3. Enable automatic OpenAPI documentation

---

## Refactored Structure

```
app/
├── core/
│   ├── domain_exceptions.py        # ✓ Already has PhotoNotFoundError, DomainValidationError
│   ├── exception_handlers.py       # ✓ Handles domain exceptions
│   └── security.py                # ✓ Centralized permission dependencies
├── routes/
│   └── api/
│       └── v1/
│           ├── schemas/
│           │   └── deepzoom.py   # NEW: Request/Response schemas
│           └── deepzoom.py       # REFACTORED: Clean route handlers
└── services/
    └── deep_zoom_service.py       # ENHANCED: Add missing methods
```

---

## Example Refactored Code

### Before (Current)
```python
@router.get("/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}")
async def get_deep_zoom_tile(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    format: str,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    await require_site_permission(site_id, request, required_permission="read")
    
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")
    
    tile_content = await deep_zoom_service.get_tile_content(str(site_id), str(photo_id), level, x, y)
    
    if not tile_content:
        raise HTTPException(status_code=404, detail="Tile non trovato")
    
    media_type = "image/jpeg" if format in ['jpg', 'jpeg'] else "image/png"
    return Response(content=tile_content, media_type=media_type, headers={...})
```

### After (Refactored)
```python
from app.core.domain_exceptions import ValidationError, PhotoNotFoundError
from app.routes.api.v1.schemas.deepzoom import TileResponse

@router.get("/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}",
            response_model=TileResponse)
async def get_deep_zoom_tile(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    format: str,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    _ = Depends(site_read_permission)  # Centralized permission
):
    # Validation logic in service or validator
    if format not in ['jpg', 'png', 'jpeg']:
        raise ValidationError("Formato tile non supportato", field="format")
    
    tile_content = await deep_zoom_service.get_tile_content(
        str(site_id), str(photo_id), level, x, y
    )
    
    if not tile_content:
        raise PhotoNotFoundError(f"Tile {level}/{x}_{y} not found for photo {photo_id}")
    
    media_type = "image/jpeg" if format in ['jpg', 'jpeg'] else "image/png"
    return Response(
        content=tile_content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*"
        }
    )
```

---

## Benefits of Refactoring

1. **Clean Architecture Compliance**
   - Routes only handle HTTP concerns
   - Business logic in services
   - Domain exceptions for errors

2. **Consistent Error Handling**
   - Centralized exception handling
   - Automatic HTTP status code mapping
   - Consistent error responses

3. **Better Maintainability**
   - Clear separation of concerns
   - Easier to test
   - Follows project conventions

4. **Improved Documentation**
   - Response schemas enable OpenAPI
   - Type safety
   - Better IDE support

5. **Security**
   - Centralized permission handling
   - No manual permission checks
   - Consistent access control

---

## Implementation Priority

| Priority | Issue | Impact | Effort |
|----------|-------|--------|--------|
| P0 | Missing imports | Breaking | Low |
| P0 | Duplicate imports | Code quality | Low |
| P1 | HTTPException usage | Architecture | Medium |
| P1 | Direct background service calls | Architecture | Medium |
| P2 | Manual permission checks | Architecture | Medium |
| P3 | Schemas in routes | Code quality | Low |
| P3 | Inline imports | Code quality | Low |
| P3 | Response formatting | Documentation | Low |
