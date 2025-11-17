# UUID Hex Error Fix Summary

## Problem Description

The admin API was failing with the error:
```
AttributeError: 'str' object has no attribute 'hex'
```

This occurred when trying to count photos for a site in the admin API endpoint `/api/v1/admin/sites/{site_id}`.

## Root Cause

The issue was caused by a mismatch between SQLAlchemy column definitions and actual database storage:

1. **Photo model** defined `site_id` as `UUID(as_uuid=True)` but the database stores it as a string
2. **Document model** had similar UUID column definitions
3. **FormSchema model** also had UUID column definitions

When SQLAlchemy tried to execute queries like:
```sql
SELECT count(photos.id) AS count_1 
FROM photos 
WHERE photos.site_id = ?
```

It expected a UUID object with a `.hex` attribute, but received a string, causing the error.

## Solution

### 1. Fixed Model Definitions

Changed UUID column definitions from `UUID(as_uuid=True)` to `String(36)` in:

**Photo model (`app/models/documentation_and_field.py`):**
- `site_id`: `UUID(as_uuid=True)` → `String(36)`
- `uploaded_by`: `UUID(as_uuid=True)` → `String(36)`

**Document model (`app/models/documentation_and_field.py`):**
- `id`: `UUID(as_uuid=True)` → `String(36)` with `default=lambda: str(uuid.uuid4())`
- `site_id`: `UUID(as_uuid=True)` → `String(36)`
- `uploaded_by`: `UUID(as_uuid=True)` → `String(36)`

**FormSchema model (`app/models/documentation_and_field.py`):**
- `id`: `UUID(as_uuid=True)` → `String(36)` with `default=lambda: str(uuid.uuid4())`
- `site_id`: `UUID(as_uuid=True)` → `String(36)`
- `created_by`: `UUID(as_uuid=True)` → `String(36)`

### 2. Fixed Admin API Queries

Updated all UUID comparisons in `app/routes/api/v1/admin.py` to use `str()` conversion:

**Photo queries:**
```python
# Before
Photo.site_id == site.id

# After  
Photo.site_id == str(site.id)
```

**UserSitePermission queries:**
```python
# Before
UserSitePermission.site_id == site.id
UserSitePermission.user_id == user.id

# After
UserSitePermission.site_id == str(site.id)
UserSitePermission.user_id == str(user.id)
```

**User queries:**
```python
# Before
User.id == user_id
User.id == current_user_id

# After
User.id == str(user_id)
User.id == str(current_user_id)
```

## Files Modified

1. `app/models/documentation_and_field.py` - Fixed UUID column definitions
2. `app/routes/api/v1/admin.py` - Fixed UUID comparisons in queries

## Testing

Created `test_uuid_hex_fix.py` to verify the fix:
- Tests Photo.site_id comparisons
- Tests UserSitePermission comparisons  
- Tests direct model queries
- ✅ All tests pass after the fix

## Impact

This fix resolves:
- Admin API site detail endpoint failures
- Photo counting errors
- User permission query errors
- Any other UUID comparison issues in admin functions

The admin API should now work correctly when accessing site details and performing administrative operations.