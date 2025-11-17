# DeepZoom Tiles Authentication Fix

## Problem
The DeepZoom tiles endpoint was returning 401 Unauthorized errors when OpenSeadragon tried to load tiles:

```
GET http://127.0.0.1:8000/api/v1/deepzoom/public/sites/553088aa-f2c3-4799-badc-8ed8f5c41751/photos/32e7f935-e712-44f1-a2b2-c3aa28645c59/tiles/7/0_0.png 401 (Unauthorized)
```

## Root Cause
The public DeepZoom endpoint only supported browser session authentication, but OpenSeadragon couldn't provide proper session context, causing authentication failures.

## Solution Implemented

### 1. Enhanced Multi-Method Authentication
Modified `/api/v1/deepzoom/public/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}` endpoint to support multiple authentication methods with fallback:

- **Primary**: Browser session authentication (`request.session.get("user_id")`)
- **Fallback 1**: JWT Authorization header (`Authorization: Bearer <token>`)
- **Fallback 2**: JWT from cookie (`access_token` cookie)

### 2. Improved Error Handling
- Better error messages for debugging
- More granular permission checking (allowing viewers to access tiles)
- Enhanced logging for security monitoring

### 3. Fixed Import Issues
Corrected import from non-existent `get_user_sites_by_id` to proper `AuthService.get_user_sites_with_permissions`.

## Files Modified

### `app/routes/api/v1/deepzoom.py`
- **Lines 191-289**: Enhanced `get_public_deep_zoom_tile` function
- **Key Changes**:
  - Added multi-method authentication with fallback
  - Fixed import from `get_user_sites_by_id` to `AuthService.get_user_sites_with_permissions`
  - Improved error handling and logging
  - Allow viewers to access tiles (not just admins/editors)

### `test_deepzoom_tiles_auth_fix.py`
- **New file**: Comprehensive test script to verify authentication fixes
- Tests session authentication, JWT fallback, and proper rejection of unauthenticated requests

## How It Works Now

1. **Session Authentication**: Tries browser session first (for logged-in users)
2. **JWT Header Fallback**: Checks Authorization header if session fails
3. **JWT Cookie Fallback**: Checks access_token cookie if header fails
4. **Proper Rejection**: Returns 401 if no authentication method works

## Test Results

✅ **JWT Fallback Authentication**: Working correctly  
✅ **Server Health**: Running and responding  
✅ **Authentication System**: Properly rejecting unauthenticated requests  
✅ **Session Middleware**: Functioning correctly  
⚠️ **Session Authentication**: Fails in test (expected - test session not logged in)

## Implementation Details

### Authentication Flow
```python
# Try session authentication first
if session.get("user_id"):
    current_user_id = UUID(session.get("user_id"))

# Fallback: Try JWT header authentication  
if not current_user_id:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # Verify JWT token

# Fallback: Try cookie authentication
if not current_user_id:
    access_token_cookie = request.cookies.get("access_token")
    if access_token_cookie:
        # Verify JWT token from cookie
```

### Permission Checking
```python
# Get user sites from database
user_sites = await AuthService.get_user_sites_with_permissions(db, current_user_id)
site_info = verify_site_access(site_id, user_sites)

# Allow viewers to access tiles (not just admins/editors)
if not site_info.get("permission_level"):
    raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
```

## Usage

1. **Restart the FastZoom server** to apply changes
2. **Test in browser** - Navigate to photo pages with DeepZoom viewer
3. **Monitor logs** - Check for successful tile access logs

The DeepZoom tiles should now load properly for authenticated users using any of the supported authentication methods.

## Benefits

- **Backward Compatibility**: Existing authentication methods continue to work
- **Multi-Method Support**: Supports session, header, and cookie authentication
- **Better Error Handling**: Clear error messages for debugging
- **Security**: Proper permission verification and logging
- **Performance**: Efficient authentication with minimal database queries

## Future Improvements

- Add caching for user permissions to reduce database load
- Implement rate limiting for tile requests
- Add metrics for monitoring tile access patterns