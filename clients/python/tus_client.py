"""
TUS Upload Client for Python
Handles resumable file uploads with progress tracking
"""
import os
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TusClient:
    """Python client for TUS resumable uploads"""
    
    def __init__(
        self,
        base_url: str,
        auth_token: str,
        chunk_size: int = 5 * 1024 * 1024,  # 5MB default
        retry_delays: list = None
    ):
        """
        Initialize TUS client
        
        Args:
            base_url: Base API URL (e.g., 'http://localhost:8000/api/v1')
            auth_token: JWT authentication token
            chunk_size: Chunk size in bytes
            retry_delays: List of retry delays in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.chunk_size = chunk_size
        self.retry_delays = retry_delays or [0, 1, 3, 5, 10]
        
        # Setup session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PATCH"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def upload_file(
        self,
        filepath: str,
        metadata: Optional[Dict[str, Any]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> str:
        """
        Upload a file using TUS protocol
        
        Args:
            filepath: Path to file to upload
            metadata: Optional metadata dict
            on_progress: Progress callback (uploaded_bytes, total_bytes)
            on_error: Error callback
            
        Returns:
            Upload URL
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        filename = filepath.name
        file_size = filepath.stat().st_size
        
        # Prepare metadata
        upload_metadata = {
            'filename': filename,
            'size': file_size,
            **(metadata or {})
        }
        
        try:
            # Create upload session
            upload_url = self._create_upload(file_size, upload_metadata)
            
            # Upload chunks
            self._upload_chunks(filepath, upload_url, file_size, on_progress)
            
            return upload_url
            
        except Exception as e:
            if on_error:
                on_error(e)
            raise
    
    def _create_upload(self, file_size: int, metadata: Dict[str, Any]) -> str:
        """Create upload session"""
        import base64
        
        # Encode metadata
        encoded_metadata = ','.join([
            f"{key} {base64.b64encode(str(value).encode()).decode()}"
            for key, value in metadata.items()
        ])
        
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Upload-Length': str(file_size),
            'Upload-Metadata': encoded_metadata,
            'Tus-Resumable': '1.0.0'
        }
        
        response = self.session.post(
            f'{self.base_url}/tus/uploads',
            headers=headers
        )
        
        if response.status_code != 201:
            raise Exception(f'Failed to create upload: {response.text}')
        
        location = response.headers.get('Location')
        if not location:
            raise Exception('No Location header in response')
        
        return location
    
    def _get_offset(self, upload_url: str) -> int:
        """Get current upload offset"""
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Tus-Resumable': '1.0.0'
        }
        
        response = self.session.head(upload_url, headers=headers)
        
        if not response.ok:
            raise Exception(f'Failed to get offset: {response.text}')
        
        offset = response.headers.get('Upload-Offset')
        return int(offset)
    
    def _upload_chunk(
        self,
        upload_url: str,
        chunk_data: bytes,
        offset: int
    ) -> int:
        """Upload a single chunk"""
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Upload-Offset': str(offset),
            'Content-Type': 'application/offset+octet-stream',
            'Tus-Resumable': '1.0.0'
        }
        
        response = self.session.patch(
            upload_url,
            headers=headers,
            data=chunk_data
        )
        
        if response.status_code != 204:
            raise Exception(f'Failed to upload chunk: {response.text}')
        
        new_offset = response.headers.get('Upload-Offset')
        return int(new_offset)
    
    def _upload_chunks(
        self,
        filepath: Path,
        upload_url: str,
        file_size: int,
        on_progress: Optional[Callable[[int, int], None]] = None
    ):
        """Upload file chunks"""
        offset = self._get_offset(upload_url)
        retry_count = 0
        
        with open(filepath, 'rb') as f:
            f.seek(offset)
            
            while offset < file_size:
                try:
                    # Read chunk
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    
                    # Upload chunk
                    offset = self._upload_chunk(upload_url, chunk, offset)
                    
                    # Progress callback
                    if on_progress:
                        on_progress(offset, file_size)
                    
                    # Reset retry count on success
                    retry_count = 0
                    
                except Exception as e:
                    # Retry logic
                    if retry_count < len(self.retry_delays):
                        delay = self.retry_delays[retry_count]
                        retry_count += 1
                        
                        print(f'Upload failed, retrying in {delay}s... ({e})')
                        time.sleep(delay)
                        
                        # Re-check offset from server
                        offset = self._get_offset(upload_url)
                        f.seek(offset)
                    else:
                        raise
    
    def get_progress(self, upload_url: str) -> Dict[str, Any]:
        """Get upload progress"""
        # Extract upload ID from URL
        upload_id = upload_url.split('/')[-1]
        progress_url = f'{self.base_url}/tus/uploads/{upload_id}/progress'
        
        headers = {
            'Authorization': f'Bearer {self.auth_token}'
        }
        
        response = self.session.get(progress_url, headers=headers)
        
        if not response.ok:
            raise Exception(f'Failed to get progress: {response.text}')
        
        return response.json()
    
    def delete_upload(self, upload_url: str):
        """Delete upload session"""
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Tus-Resumable': '1.0.0'
        }
        
        response = self.session.delete(upload_url, headers=headers)
        
        if response.status_code != 204:
            raise Exception(f'Failed to delete upload: {response.text}')


# Example usage
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python tus_client.py <file_path> <auth_token>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    auth_token = sys.argv[2]
    
    # Initialize client
    client = TusClient(
        base_url='http://localhost:8000/api/v1',
        auth_token=auth_token
    )
    
    # Progress callback
    def on_progress(uploaded, total):
        percent = (uploaded / total) * 100
        print(f'\rProgress: {percent:.2f}% ({uploaded}/{total} bytes)', end='')
    
    # Upload file
    try:
        print(f'Uploading: {file_path}')
        upload_url = client.upload_file(
            filepath=file_path,
            metadata={'description': 'Test upload'},
            on_progress=on_progress
        )
        print(f'\n✅ Upload complete: {upload_url}')
        
        # Get progress
        progress = client.get_progress(upload_url)
        print(f'Final progress: {progress}')
        
    except Exception as e:
        print(f'\n❌ Upload failed: {e}')
        sys.exit(1)