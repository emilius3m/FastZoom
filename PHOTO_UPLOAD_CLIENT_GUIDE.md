# Photo Upload Client Guide - JSON Metadata API

## Overview

This guide provides comprehensive documentation for frontend developers on how to use the new photo upload endpoint with JSON metadata. The new API replaces the previous Form parameter approach with a modern JSON-based metadata system.

## API Endpoint

```
POST /api/v1/sites/{site_id}/photos/upload
```

### Key Changes

- **Before**: 40+ individual Form fields for metadata
- **Now**: Single JSON string containing all metadata
- **Benefits**: Better validation, structured data, easier error handling

## Quick Start

### Basic Upload Example

```javascript
const formData = new FormData();
formData.append('photos', fileInput.files[0]);
formData.append('metadata', JSON.stringify({
    title: 'Photo title',
    description: 'Photo description',
    photo_type: 'detail',
    photographer: 'John Doe',
    inventory_number: 'INV-2023-001'
}));

const response = await fetch('/api/v1/sites/site-id/photos/upload', {
    method: 'POST',
    body: formData,
    headers: {
        'Authorization': 'Bearer ' + token
    }
});
```

## Complete Metadata Schema

### Basic Information
- `title` (string, optional): Photo title
- `description` (string, optional): Photo description
- `photo_type` (string, optional): Photo type (general, detail, context, etc.)
- `photographer` (string, optional): Photographer name
- `keywords` (string, optional): Comma-separated keywords

### Archaeological Context
- `inventory_number` (string, optional): Museum inventory number
- `catalog_number` (string, optional): Catalog number
- `excavation_area` (string, optional): Excavation area
- `stratigraphic_unit` (string, optional): Stratigraphic unit reference
- `grid_square` (string, optional): Grid square location
- `depth_level` (float, optional): Depth level in meters
- `find_date` (string, optional): Date of discovery (ISO format)
- `finder` (string, optional): Person who found the item
- `excavation_campaign` (string, optional): Excavation campaign name

### Material and Object Information
- `material` (string, optional): Material type
- `material_details` (string, optional): Material specific details
- `object_type` (string, optional): Type of object
- `object_function` (string, optional): Object function/use

### Physical Dimensions
- `length_cm` (float, optional): Length in centimeters
- `width_cm` (float, optional): Width in centimeters
- `height_cm` (float, optional): Height in centimeters
- `diameter_cm` (float, optional): Diameter in centimeters
- `weight_grams` (float, optional): Weight in grams

### Chronology and Dating
- `chronology_period` (string, optional): Chronological period
- `chronology_culture` (string, optional): Associated culture
- `dating_from` (string, optional): Dating start year or period
- `dating_to` (string, optional): Dating end year or period
- `dating_notes` (string, optional): Dating interpretation notes

### Conservation Information
- `conservation_status` (string, optional): Conservation status
- `conservation_notes` (string, optional): Conservation details
- `restoration_history` (string, optional): Restoration history

### References and Documentation
- `bibliography` (string, optional): Bibliographic references
- `comparative_references` (string, optional): Comparative examples
- `external_links` (string, optional): External reference links

### Rights and Licensing
- `copyright_holder` (string, optional): Copyright holder
- `license_type` (string, optional): License type
- `usage_rights` (string, optional): Usage restrictions

### Queue Control
- `use_queue` (boolean, optional): Use queue processing (default: false)
- `priority` (string, optional): Processing priority (critical, high, normal, low, bulk)

## Response Format

### Successful Response (200 OK)

```json
{
    "uploaded_photos": [
        {
            "photo_id": "550e8400-e29b-41d4-a716-446655440000",
            "filename": "photo_001.jpg",
            "file_size": 2048576,
            "file_path": "sites/site-id/photos/photo_001.jpg",
            "metadata": {
                "width": 1920,
                "height": 1080,
                "photo_date": "2023-05-15T10:30:00Z",
                "camera_model": "Canon EOS 5D"
            },
            "archaeological_metadata": {
                "inventory_number": "INV-2023-001",
                "excavation_area": "Sector A",
                "material": "ceramic",
                "chronology_period": "Late Bronze Age",
                "photo_type": "detail",
                "photographer": "Dr. Maria Rossi",
                "description": "Fine example of decorated ceramic"
            }
        }
    ],
    "message": "1 foto caricate con successo",
    "total_uploaded": 1,
    "photos_needing_tiles": 1,
    "upload_timestamp": "2023-11-19T12:00:00Z"
}
```

### Validation Error Response (422 Unprocessable Entity)

```json
{
    "message": "Metadata validation failed",
    "validation_errors": [
        {
            "loc": ["dating_from"],
            "msg": "Invalid date format: 2023-XX-XX. Use ISO format, YYYY-MM-DD, YYYY, or negative years for BCE",
            "type": "value_error"
        }
    ],
    "error_type": "ValidationError",
    "received_metadata": {
        "title": "Test Photo",
        "dating_from": "2023-XX-XX"
    }
}
```

## Framework Examples

This guide includes complete examples for:

1. **JavaScript/TypeScript** - Pure JS implementation with full error handling
2. **React** - Modern React component with hooks
3. **Alpine.js** - Compatible with existing FastZoom system
4. **Vue.js** - Vue 3 composition API component
5. **Axios vs Fetch** - Comparison of both approaches
6. **Error Handling** - Comprehensive 422 error management
7. **Migration Guide** - Step-by-step upgrade from old system

## Best Practices

### 1. Always Validate Metadata Client-Side
```javascript
function validateMetadata(metadata) {
    const errors = [];
    
    if (metadata.dating_from && !isValidDate(metadata.dating_from)) {
        errors.push('Invalid dating_from format');
    }
    
    if (metadata.length_cm && metadata.length_cm < 0) {
        errors.push('Length must be positive');
    }
    
    return errors;
}
```

### 2. Handle File Size Limits
```javascript
const MAX_FILE_SIZE_MB = 50;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

if (file.size > MAX_FILE_SIZE_BYTES) {
    throw new Error(`File size exceeds ${MAX_FILE_SIZE_MB}MB limit`);
}
```

### 3. Use Progress Indicators for Multiple Files
```javascript
const uploadProgress = {
    total: files.length,
    completed: 0,
    failed: 0
};

// Update UI with progress
updateProgressBar((uploadProgress.completed / uploadProgress.total) * 100);
```

### 4. Implement Retry Logic for Network Errors
```javascript
async function uploadWithRetry(formData, maxRetries = 3) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const response = await fetch('/api/v1/sites/site-id/photos/upload', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) return response;
            
            if (attempt === maxRetries) throw new Error('Max retries exceeded');
            
            // Exponential backoff
            await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        } catch (error) {
            if (attempt === maxRetries) throw error;
        }
    }
}
```

## Migration from Old System

### Old Approach (Deprecated)
```javascript
// OLD - Don't use this anymore
const formData = new FormData();
formData.append('photos', file);
formData.append('title', 'Photo title');
formData.append('description', 'Photo description');
formData.append('inventory_number', 'INV-001');
// ... 40+ more fields
```

### New Approach (Current)
```javascript
// NEW - Use this instead
const metadata = {
    title: 'Photo title',
    description: 'Photo description',
    inventory_number: 'INV-001',
    // All metadata in one object
};

const formData = new FormData();
formData.append('photos', file);
formData.append('metadata', JSON.stringify(metadata));
```

## Error Handling

### Common Error Types

1. **422 Validation Error** - Invalid metadata format
2. **401 Authentication Error** - Invalid or expired token
3. **403 Authorization Error** - Insufficient permissions
4. **413 Payload Too Large** - File exceeds size limit
5. **503 Service Unavailable** - Storage system issues

### Handling 422 Validation Errors

```javascript
if (response.status === 422) {
    const errorData = await response.json();
    
    // Extract field-specific errors
    const fieldErrors = {};
    errorData.validation_errors?.forEach(error => {
        const field = error.loc[error.loc.length - 1];
        fieldErrors[field] = error.msg;
    });
    
    // Display errors to user
    Object.entries(fieldErrors).forEach(([field, message]) => {
        showFieldError(field, message);
    });
}
```

## TypeScript Support

For TypeScript users, use the provided type definitions:

```typescript
import { PhotoUploadRequest } from './photo_upload_types';

const metadata: PhotoUploadRequest = {
    title: 'Photo title',
    photo_type: 'detail',
    // Full type safety and autocomplete
};
```

## Testing

Use the provided test scripts to validate your implementation:

```bash
# Test with curl
./test_upload_curl.sh

# Test with PowerShell
./test_upload_curl.bat
```

## Support

For issues or questions:
1. Check the validation error messages carefully
2. Review this guide for correct field formats
3. Test with minimal metadata first, then add complexity
4. Check browser console for JavaScript errors
5. Verify network requests in browser dev tools

---

*This documentation covers the new JSON metadata upload system. For legacy Form parameter documentation, see the archived documentation.*