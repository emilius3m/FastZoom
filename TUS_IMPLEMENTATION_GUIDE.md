# TUS Protocol Implementation Guide

## Overview

This document describes the TUS (resumable upload protocol) implementation in the FastZoom archaeological system. TUS allows large files to be uploaded in chunks with automatic resume capability if the connection is interrupted.

## Architecture

### Components

1. **TusUploadService** (`app/services/tus_service.py`)
   - Core service handling upload sessions
   - Manages chunk storage and metadata
   - Handles validation and cleanup

2. **TUS API Routes** (`app/routes/api/v1/tus_uploads.py`)
   - RESTful endpoints implementing TUS protocol
   - Authentication integration
   - Progress tracking

3. **Configuration** (`app/core/config.py`)
   - TUS-specific settings
   - Upload limits and timeouts

## Configuration

Add to your `.env` file:

```bash
# TUS Configuration
TUS_ENABLED=true
TUS_UPLOAD_DIR=app/static/tus_uploads
TUS_MAX_SIZE=1073741824  # 1GB
TUS_CHUNK_SIZE=5242880   # 5MB
TUS_EXPIRATION_HOURS=24
TUS_ALLOWED_EXTENSIONS=jpg,jpeg,png,tiff,raw,dng,pdf,doc,docx
```

## API Endpoints

### Create Upload Session
```http
POST /api/v1/tus/uploads
Headers:
  Upload-Length: 1048576
  Upload-Metadata: filename dXBsb2FkLmpwZw==
  Authorization: Bearer <token>

Response: 201 Created
Location: http://localhost:8000/api/v1/tus/uploads/{upload_id}
Upload-Offset: 0
Tus-Resumable: 1.0.0
```

### Get Upload Status
```http
HEAD /api/v1/tus/uploads/{upload_id}
Authorization: Bearer <token>

Response: 200 OK
Upload-Offset: 524288
Upload-Length: 1048576
Tus-Resumable: 1.0.0
```

### Upload Chunk
```http
PATCH /api/v1/tus/uploads/{upload_id}
Headers:
  Upload-Offset: 0
  Content-Type: application/offset+octet-stream
  Authorization: Bearer <token>
Body: <binary chunk data>

Response: 204 No Content
Upload-Offset: 524288
Tus-Resumable: 1.0.0
```

### Get Progress
```http
GET /api/v1/tus/uploads/{upload_id}/progress
Authorization: Bearer <token>

Response: 200 OK
{
  "upload_id": "uuid",
  "filename": "photo.jpg",
  "offset": 524288,
  "upload_length": 1048576,
  "progress_percent": 50.0,
  "is_complete": false,
  "created_at": "2025-12-31T12:00:00",
  "expires_at": "2026-01-01T12:00:00"
}
```

### Delete Upload
```http
DELETE /api/v1/tus/uploads/{upload_id}
Authorization: Bearer <token>

Response: 204 No Content
```

### Check TUS Capabilities
```http
OPTIONS /api/v1/tus/uploads

Response: 204 No Content
Tus-Resumable: 1.0.0
Tus-Version: 1.0.0
Tus-Extension: creation,termination
Tus-Max-Size: 1073741824
```

## Client Implementation Example

### JavaScript/TypeScript with tus-js-client

```javascript
import * as tus from 'tus-js-client';

async function uploadFile(file, accessToken) {
  const upload = new tus.Upload(file, {
    endpoint: 'http://localhost:8000/api/v1/tus/uploads',
    retryDelays: [0, 3000, 5000, 10000, 20000],
    metadata: {
      filename: file.name,
      filetype: file.type
    },
    headers: {
      'Authorization': `Bearer ${accessToken}`
    },
    onError: function(error) {
      console.error('Upload failed:', error);
    },
    onProgress: function(bytesUploaded, bytesTotal) {
      const percentage = (bytesUploaded / bytesTotal * 100).toFixed(2);
      console.log(`Progress: ${percentage}%`);
    },
    onSuccess: function() {
      console.log('Upload complete!');
      console.log('Upload URL:', upload.url);
    }
  });

  // Start the upload
  upload.start();

  // Optional: pause/resume
  // upload.abort();
  // upload.start();
}

// Usage
const fileInput = document.querySelector('input[type="file"]');
fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  const token = 'your-access-token';
  await uploadFile(file, token);
});
```

### Python Client

```python
import requests
import os

class TusUploader:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.chunk_size = 5 * 1024 * 1024  # 5MB
    
    def upload_file(self, filepath: str, on_progress=None):
        """Upload a file using TUS protocol"""
        
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        
        # Create upload session
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Upload-Length': str(file_size),
            'Tus-Resumable': '1.0.0'
        }
        
        response = requests.post(
            f'{self.base_url}/tus/uploads',
            headers=headers
        )
        
        if response.status_code != 201:
            raise Exception(f'Failed to create upload: {response.text}')
        
        upload_url = response.headers['Location']
        
        # Upload chunks
        with open(filepath, 'rb') as f:
            offset = 0
            
            while offset < file_size:
                chunk = f.read(self.chunk_size)
                
                headers = {
                    'Authorization': f'Bearer {self.token}',
                    'Upload-Offset': str(offset),
                    'Content-Type': 'application/offset+octet-stream',
                    'Tus-Resumable': '1.0.0'
                }
                
                response = requests.patch(
                    upload_url,
                    headers=headers,
                    data=chunk
                )
                
                if response.status_code != 204:
                    raise Exception(f'Failed to upload chunk: {response.text}')
                
                offset += len(chunk)
                
                if on_progress:
                    on_progress(offset, file_size)
        
        return upload_url

# Usage
uploader = TusUploader(
    base_url='http://localhost:8000/api/v1',
    token='your-access-token'
)

def progress_callback(uploaded, total):
    pct = (uploaded / total) * 100
    print(f'Progress: {pct:.2f}%')

upload_url = uploader.upload_file(
    '/path/to/photo.jpg',
    on_progress=progress_callback
)
print(f'Upload complete: {upload_url}')
```

## Integration with Photo System

After a TUS upload completes, you can process it and save to the photo system:

```python
from app.services.tus_service import tus_upload_service
from app.services.photo_service import PhotoService

# Get completed upload
upload_id = "..."
file_path = await tus_upload_service.get_upload_file_path(upload_id)
metadata = await tus_upload_service.get_upload_metadata(upload_id)

# Process with photo service
photo_service = PhotoService()
photo = await photo_service.create_photo(
    db=db,
    site_id=site_id,
    file_path=file_path,
    filename=metadata['filename'],
    user_id=metadata['custom_metadata']['user_id']
)

# Clean up TUS upload
await tus_upload_service.delete_upload(upload_id)
```

## Maintenance

### Cleanup Expired Uploads

Expired incomplete uploads should be cleaned up periodically:

```python
# Manual cleanup
POST /api/v1/tus/cleanup
Authorization: Bearer <admin-token>

# Or via scheduled task
from app.services.tus_service import tus_upload_service
cleaned = await tus_upload_service.cleanup_expired_uploads()
```

### Monitoring

Monitor TUS upload directory size:

```bash
# Check upload directory
du -sh app/static/tus_uploads

# Check metadata
ls -la app/static/tus_uploads/.metadata
```

## Security

1. **Authentication**: All endpoints require valid JWT token
2. **User Isolation**: Users can only access their own uploads
3. **Size Limits**: Configurable max file size
4. **Extension Validation**: Only allowed file types accepted
5. **Expiration**: Incomplete uploads auto-expire after 24h

## Error Handling

- **400**: Invalid request (wrong offset, bad metadata)
- **403**: Access denied (not upload owner)
- **404**: Upload not found
- **409**: Offset conflict (resume from correct position)
- **500**: Server error

## Performance

- **Chunk Size**: Default 5MB chunks for optimal network performance
- **Parallel Uploads**: Multiple files can be uploaded simultaneously
- **Resume Support**: Upload resumes automatically from last successful chunk
- **Storage**: Uploads stored in filesystem, metadata in JSON files

## Troubleshooting

### Upload Not Resuming
- Check `Upload-Offset` header matches server offset
- Verify upload hasn't expired
- Check authentication token is valid

### Slow Uploads
- Adjust `TUS_CHUNK_SIZE` (larger = fewer requests, more memory)
- Check network bandwidth
- Monitor disk I/O

### Out of Disk Space
- Clean up expired uploads
- Check `TUS_EXPIRATION_HOURS` setting
- Monitor upload directory size

## Future Enhancements

1. **Concatenation**: Merge multiple uploads into one file
2. **Checksum**: Verify chunk integrity with checksums
3. **S3 Backend**: Store directly to MinIO/S3
4. **Database Metadata**: Store metadata in database instead of JSON files
5. **WebSocket Progress**: Real-time progress updates
6. **Parallel Chunks**: Upload multiple chunks simultaneously

## References

- [TUS Protocol Specification](https://tus.io/protocols/resumable-upload.html)
- [tus-js-client](https://github.com/tus/tus-js-client)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)