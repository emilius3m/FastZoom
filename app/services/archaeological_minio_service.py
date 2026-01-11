# app/services/archaeological_minio_service.py - SERVIZIO MINIO ARCHEOLOGICO AVANZATO OTTIMIZZATO

import io
import asyncio
import json
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, AsyncGenerator
from uuid import UUID
from pathlib import Path
from loguru import logger
from fastapi import HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse

from minio import Minio
from minio.error import S3Error
from app.core.minio_settings import settings
from app.core.exceptions import (
    StorageError, StorageFullError, StorageTemporaryError,
    StorageConnectionError, StorageNotFoundError
)
# Import locale per evitare circular import
# from app.services.deep_zoom_minio_service import deep_zoom_minio_service


class RetryWithJitter:
    """Retry pattern con backoff esponenziale e jitter per operazioni MinIO"""
    
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 60.0, jitter_factor: float = 0.1):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
    
    async def execute_with_retry(self, operation_func, operation_name: str, *args, **kwargs):
        """Esegue operazione con retry e jitter"""
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    # Calcola delay con backoff esponenziale e jitter
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    jitter = random.uniform(-self.jitter_factor * delay, self.jitter_factor * delay)
                    final_delay = max(0, delay + jitter)
                    
                    logger.warning(f"Retry {attempt}/{self.max_retries} for {operation_name} after {final_delay:.2f}s delay")
                    await asyncio.sleep(final_delay)
                
                # Esegui operazione
                if asyncio.iscoroutinefunction(operation_func):
                    return await operation_func(*args, **kwargs)
                else:
                    # Esegui operazione sincrona in thread pool
                    return await asyncio.to_thread(operation_func, *args, **kwargs)
                
            except S3Error as e:
                last_exception = e
                error_code = getattr(e, 'code', 'Unknown')
                error_message = str(e)
                
                # Classifica errori per retry strategy
                if self._should_retry_error(error_code, error_message):
                    if attempt < self.max_retries:
                        logger.warning(f"MinIO {operation_name} failed (attempt {attempt + 1}): {error_code} - {error_message}")
                        continue
                    else:
                        logger.error(f"MinIO {operation_name} failed after {self.max_retries} retries: {error_code} - {error_message}")
                        raise StorageTemporaryError(f"MinIO operation failed after retries: {error_message}")
                else:
                    # Errori non retryable
                    logger.error(f"MinIO {operation_name} failed with non-retryable error: {error_code} - {error_message}")
                    raise StorageError(f"MinIO operation failed: {error_message}")
            
            except Exception as e:
                last_exception = e
                error_message = str(e)
                
                if attempt < self.max_retries:
                    logger.warning(f"MinIO {operation_name} failed with unexpected error (attempt {attempt + 1}): {error_message}")
                    continue
                else:
                    logger.error(f"MinIO {operation_name} failed after {self.max_retries} retries: {error_message}")
                    raise StorageTemporaryError(f"MinIO operation failed after retries: {error_message}")
        
        # Questo punto non dovrebbe essere raggiunto
        raise StorageError(f"MinIO operation failed: {str(last_exception)}")
    
    def _should_retry_error(self, error_code: str, error_message: str) -> bool:
        """Determina se l'errore è retryable"""
        
        # Errori retryable comuni
        retryable_errors = {
            'InternalError', 'ServiceUnavailable', 'SlowDown', 'RequestTimeout',
            'RequestTimeoutException', 'ServiceUnavailable', 'InternalError',
            'NetworkError', 'ConnectionError', 'Timeout', 'ReadTimeout'
        }
        
        # Errori non retryable
        non_retryable_errors = {
            'InvalidAccessKeyId', 'SignatureDoesNotMatch', 'AccessDenied',
            'NoSuchBucket', 'NoSuchKey', 'InvalidBucketName', 'MalformedXML'
        }
        
        # Controlla errori specifici
        if error_code in non_retryable_errors:
            return False
        
        if error_code in retryable_errors:
            return True
        
        # Controlla messaggi di errore per casi speciali
        error_lower = error_message.lower()
        
        # Storage full - retryable con cleanup
        if 'storage full' in error_lower or 'minimum free drive' in error_lower:
            return True
        
        # Network errors - retryable
        if any(keyword in error_lower for keyword in ['connection', 'timeout', 'network', 'dns']):
            return True
        
        # Default: retry per errori sconosciuti
        return True


class ArchaeologicalMinIOService:
    """Servizio MinIO ottimizzato per dati archeologici con supporto avanzato"""

    def _create_minio_client(self) -> Minio:
        """Crea e configura il client MinIO con supporto profile-based configuration"""
        from app.core.config import get_settings
        
        # Get settings with profile support
        config_settings = get_settings()
        
        # Use profile-based configuration
        minio_url = config_settings.active_minio_url.replace("http://", "").replace("https://", "")
        access_key = config_settings.active_minio_access_key
        secret_key = config_settings.active_minio_secret_key
        secure = config_settings.active_minio_secure
        
        logger.debug(f"MinIO config - profile: {config_settings.minio_config_profile}, endpoint: {minio_url}, bucket: {config_settings.active_minio_bucket}, secure: {secure}")

        # Fallback a environment variables se settings non disponibili
        if not all([minio_url, access_key, secret_key]):
            logger.warning("Profile-based configuration incomplete, falling back to environment variables")
            minio_url = os.getenv("MINIO_ENDPOINT", "localhost:9000")
            access_key = os.getenv("MINIO_ACCESS_KEY", "")
            secret_key = os.getenv("MINIO_SECRET_KEY", "")
            secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

        client = Minio(
            endpoint=minio_url,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        
        logger.info(f"MinIO client initialized (profile: {config_settings.minio_config_profile})")
        return client

    def _is_storage_full_error(self, error: Exception) -> bool:
        """Check se errore è storage full"""
        error_str = str(error)
        return (
            "XMinioStorageFull" in error_str or
            "minimum free drive threshold" in error_str or
            "no space left" in error_str.lower()
        )

    def _map_minio_error(self, error: Exception) -> StorageError:
        """Mappa eccezioni MinIO a eccezioni dominio"""
        error_str = str(error).lower()

        if self._is_storage_full_error(error):
            return StorageFullError(str(error))

        if "connection" in error_str or "timeout" in error_str:
            return StorageConnectionError(str(error))

        if "temporary" in error_str or "retry" in error_str:
            return StorageTemporaryError(str(error))

        if "not found" in error_str or "nosuchkey" in error_str:
            return StorageNotFoundError(str(error))

        return StorageError(str(error))

    async def _emergency_cleanup(self) -> int:
        """Esegue cleanup emergenza, ritorna MB liberati"""
        try:
            from app.services.storage_management_service import storage_management_service
            result = await storage_management_service.emergency_cleanup(target_freed_mb=100)
            return result.get('total_freed_mb', 0)
        except Exception as e:
            logger.error(f"Emergency cleanup failed: {e}")
            return 0

    async def _handle_storage_full_error(
        self,
        operation_func,
        operation_name: str,
        target_freed_mb: int,
        *args,
        **kwargs
    ):
        """Gestione unificata errori storage full con cleanup automatico"""
        try:
            # Prima tentativo
            return await operation_func(*args, **kwargs)

        except S3Error as e:
            error_msg = str(e)

            # Verifica se è errore storage full
            if self._is_storage_full_error(e):
                logger.error(f"MinIO storage full during {operation_name}")

                # Tenta cleanup di emergenza
                try:
                    freed_mb = await self._emergency_cleanup()
                    if freed_mb > 50:
                        logger.info(f"Emergency cleanup freed {freed_mb}MB, retrying {operation_name}")

                        # Riprova operazione dopo cleanup
                        return await operation_func(*args, **kwargs)
                    else:
                        logger.error(f"Emergency cleanup insufficient for {operation_name}")
                        raise StorageFullError(
                            f"Storage full. Cleanup freed only {freed_mb}MB",
                            freed_space_mb=freed_mb
                        )

                except Exception as cleanup_error:
                    logger.error(f"Emergency cleanup failed for {operation_name}: {cleanup_error}")
                    raise StorageFullError("Storage full and cleanup failed")
            else:
                logger.error(f"MinIO {operation_name} error: {e}")
                raise self._map_minio_error(e)

    async def _upload_with_retry(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str = None,
        metadata: Dict[str, str] = None,
        operation_name: str = "upload",
        target_freed_mb: int = 100
    ) -> str:
        """FIXED: Upload with retry pattern, circuit breaker, and timeout handling"""
        
        # FIXED: Check circuit breaker before attempting operation
        if not self._check_circuit_breaker():
            raise StorageTemporaryError("Storage service temporarily unavailable (circuit breaker open)")
        
        def upload_operation():
            # FIXED: Add socket timeout to prevent hanging
            import socket
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(30)  # 30 seconds timeout
            
            try:
                result = self._client.put_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    data=io.BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                    metadata=metadata
                )
                return f"minio://{bucket_name}/{object_name}"
            finally:
                socket.setdefaulttimeout(original_timeout)

        try:
            # FIXED: Execute upload with overall timeout
            upload_future = asyncio.create_task(
                self.retry_handler.execute_with_retry(
                    upload_operation,
                    f"{operation_name} to {bucket_name}/{object_name}"
                )
            )
            
            # 60 second timeout for upload operation
            result = await asyncio.wait_for(upload_future, timeout=60.0)
            
            # FIXED: Success - reset circuit breaker
            self._reset_circuit_breaker()
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ Upload operation timed out: {operation_name} to {bucket_name}/{object_name}")
            self._record_circuit_breaker_failure()
            raise StorageTemporaryError(f"Upload operation timed out: {operation_name}")
        except HTTPException as e:
            # Gestione speciale per storage full
            if "storage full" in str(e.detail).lower():
                return await self._handle_storage_full_error(
                    upload_operation,
                    operation_name,
                    target_freed_mb
                )
            else:
                self._record_circuit_breaker_failure()
                raise
        except Exception as e:
            self._record_circuit_breaker_failure()
            raise StorageError(f"Upload operation failed: {str(e)}")

    async def _generate_presigned_url(
        self,
        bucket_name: str,
        object_name: str,
        expires_hours: int = 24,
        operation_name: str = "URL generation"
    ) -> Optional[str]:
        """Metodo base per generazione URL presigned con retry"""
        
        def url_operation():
            return self._client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=timedelta(hours=expires_hours)
            )

        try:
            return await self.retry_handler.execute_with_retry(
                url_operation,
                f"{operation_name} for {bucket_name}/{object_name}"
            )
        except HTTPException:
            # Per URL presigned, ritorna None invece di sollevare eccezione
            return None

    def _create_base_metadata(self, site_id: str, content_type: str = None) -> Dict[str, str]:
        """Crea metadati di base comuni a tutti gli oggetti"""
        metadata = {
            'x-amz-meta-site-id': site_id,
            'x-amz-meta-upload-date': str(datetime.now().isoformat())
        }

        if content_type:
            metadata['Content-Type'] = content_type

        return metadata

    def _merge_metadata(self, base_metadata: Dict[str, str], additional_metadata: Dict[str, Any]) -> Dict[str, str]:
        """Unisce metadati di base con metadati aggiuntivi"""
        merged = base_metadata.copy()

        for field, value in additional_metadata.items():
            if value is not None:
                # Converte valori complessi in stringa
                if isinstance(value, (list, dict)):
                    merged[f'x-amz-meta-{field}'] = json.dumps(value)
                else:
                    merged[f'x-amz-meta-{field}'] = str(value)

        return merged

    def __init__(self):
        self._client = self._create_minio_client()  # Renamed to private
        
        # Inizializza retry pattern con jitter
        self.retry_handler = RetryWithJitter(
            max_retries=5,
            base_delay=1.0,
            max_delay=60.0,
            jitter_factor=0.1
        )

        # Bucket specializzati per archeologia
        self.buckets = {
            'photos': 'archaeological-photos',
            'documents': 'archaeological-documents',
            'tiles': 'deep-zoom-tiles',
            'thumbnails': 'thumbnails',
            'backups': 'site-backups'
        }

        # FIXED: Circuit breaker for MinIO operations to prevent hanging
        self.circuit_breaker = {
            'failure_count': 0,
            'last_failure_time': 0,
            'state': 'CLOSED',  # CLOSED, OPEN, HALF_OPEN
            'failure_threshold': 5,
            'recovery_timeout': 60  # 60 seconds
        }

        # FIXED: Initialize buckets with timeout to prevent hanging
        self._initialize_buckets_with_timeout()

    def _initialize_buckets_with_timeout(self):
        """FIXED: Initialize buckets with timeout and non-blocking behavior"""
        try:
            # Include the legacy 'storage' bucket for compatibility
            all_buckets = dict(self.buckets)
            all_buckets['storage'] = 'storage'  # Add legacy bucket
            
            # FIXED: Set timeout for bucket operations
            import socket
            
            # Set socket timeout for all operations
            socket.setdefaulttimeout(30)  # 30 seconds timeout
            
            for bucket_type, bucket_name in all_buckets.items():
                try:
                    # FIXED: Add timeout to bucket existence check
                    if not self._client.bucket_exists(bucket_name):
                        logger.info(f"Creating bucket: {bucket_name} ({bucket_type})")
                        self._client.make_bucket(bucket_name)
                        logger.info(f"Created bucket: {bucket_name} ({bucket_type})")

                        # Policy di accesso per bucket pubblici (thumbnails e storage)
                        if bucket_name in ["thumbnails", "storage"]:
                            policy = {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Principal": {"AWS": "*"},
                                        "Action": ["s3:GetObject"],
                                        "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                                    }
                                ]
                            }
                            try:
                                self._client.set_bucket_policy(bucket_name, json.dumps(policy))
                                logger.info(f"Set public policy for bucket: {bucket_name}")
                            except Exception as policy_error:
                                logger.warning(f"Could not set policy for {bucket_name}: {policy_error}")
                    else:
                        logger.debug(f"Bucket already exists: {bucket_name}")
                        
                except Exception as bucket_e:
                    logger.error(f"Error initializing bucket {bucket_name}: {bucket_e}")
                    # FIXED: Continue with other buckets instead of failing completely
                    continue

        except Exception as e:
            logger.error(f"Error in bucket initialization: {e}")
            # FIXED: Don't fail service initialization completely
            logger.warning("Bucket initialization failed but service will continue")

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations"""
        current_time = time.time()
        
        # If circuit is OPEN, check if recovery timeout has passed
        if self.circuit_breaker['state'] == 'OPEN':
            if current_time - self.circuit_breaker['last_failure_time'] > self.circuit_breaker['recovery_timeout']:
                # Transition to HALF_OPEN state
                self.circuit_breaker['state'] = 'HALF_OPEN'
                logger.info("Circuit breaker transitioning to HALF_OPEN state")
                return True
            else:
                # Still in OPEN state, block operations
                return False
        
        # If CLOSED or HALF_OPEN, allow operations
        return True

    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker after successful operation"""
        self.circuit_breaker['failure_count'] = 0
        self.circuit_breaker['state'] = 'CLOSED'
        self.circuit_breaker['last_failure_time'] = 0
        logger.debug("Circuit breaker reset to CLOSED state")

    def _record_circuit_breaker_failure(self) -> None:
        """Record a failure and update circuit breaker state"""
        self.circuit_breaker['failure_count'] += 1
        self.circuit_breaker['last_failure_time'] = time.time()
        
        # Check if we should open the circuit
        if self.circuit_breaker['failure_count'] >= self.circuit_breaker['failure_threshold']:
            self.circuit_breaker['state'] = 'OPEN'
            logger.warning(f"Circuit breaker opened after {self.circuit_breaker['failure_count']} failures")
        else:
            logger.debug(f"Circuit breaker failure recorded: {self.circuit_breaker['failure_count']}/{self.circuit_breaker['failure_threshold']}")

    async def _get_file_size(self, file: UploadFile) -> int:
        """Calcola dimensione file in modo sicuro"""
        try:
            # Prova a ottenere dimensione da header
            if hasattr(file, 'size') and file.size:
                return file.size

            # Fallback: leggi file per calcolare dimensione
            current_pos = file.file.tell() if hasattr(file.file, 'tell') else 0
            file.file.seek(0, 2)  # Seek to end
            size = file.file.tell()
            file.file.seek(current_pos)  # Restore position
            return size

        except Exception:
            # Se tutto fallisce, restituisci 0 e lascia che MinIO gestisca
            return 0

    def _map_archaeological_metadata(self, site_id: str, archaeological_metadata: Dict[str, Any]) -> Dict[str, str]:
        """Mappa metadati archeologici per MinIO storage"""
        metadata = {
            'x-amz-meta-site-id': site_id,
            'x-amz-meta-upload-date': str(datetime.now().isoformat()),
            'Content-Type': 'image/jpeg'
        }

        # Mappa tutti i metadati archeologici
        field_mapping = {
            'inventory_number': 'x-amz-meta-inventory-number',
            'excavation_area': 'x-amz-meta-excavation-area',
            'stratigraphic_unit': 'x-amz-meta-stratigraphic-unit',
            'material': 'x-amz-meta-material',
            'object_type': 'x-amz-meta-object-type',
            'chronology_period': 'x-amz-meta-chronology',
            'photo_type': 'x-amz-meta-photo-type',
            'photographer': 'x-amz-meta-photographer',
            'description': 'x-amz-meta-description',
            'keywords': 'x-amz-meta-keywords',
            'find_date': 'x-amz-meta-find-date',
            'conservation_status': 'x-amz-meta-conservation-status',
            'catalog_number': 'x-amz-meta-catalog-number',
            'grid_square': 'x-amz-meta-grid-square',
            'depth_level': 'x-amz-meta-depth-level',
            'finder': 'x-amz-meta-finder',
            'excavation_campaign': 'x-amz-meta-excavation-campaign',
            'material_details': 'x-amz-meta-material-details',
            'object_function': 'x-amz-meta-object-function',
            'length_cm': 'x-amz-meta-length-cm',
            'width_cm': 'x-amz-meta-width-cm',
            'height_cm': 'x-amz-meta-height-cm',
            'diameter_cm': 'x-amz-meta-diameter-cm',
            'weight_grams': 'x-amz-meta-weight-grams',
            'chronology_culture': 'x-amz-meta-chronology-culture',
            'dating_from': 'x-amz-meta-dating-from',
            'dating_to': 'x-amz-meta-dating-to',
            'dating_notes': 'x-amz-meta-dating-notes',
            'conservation_notes': 'x-amz-meta-conservation-notes',
            'restoration_history': 'x-amz-meta-restoration-history',
            'bibliography': 'x-amz-meta-bibliography',
            'comparative_references': 'x-amz-meta-comparative-references',
            'external_links': 'x-amz-meta-external-links',
            'copyright_holder': 'x-amz-meta-copyright-holder',
            'license_type': 'x-amz-meta-license-type',
            'usage_rights': 'x-amz-meta-usage-rights',
            'validation_notes': 'x-amz-meta-validation-notes'
        }

        # Applica il mapping
        for field, value in archaeological_metadata.items():
            if field in field_mapping and value is not None:
                # Converte valori complessi in stringa
                if isinstance(value, (list, dict)):
                    metadata[field_mapping[field]] = json.dumps(value)
                else:
                    metadata[field_mapping[field]] = str(value)

        return metadata

    async def upload_photo_with_metadata(
        self,
        photo_data: bytes,
        photo_id: str,
        site_id: str,
        archaeological_metadata: Dict[str, Any]
    ) -> str:
        """Upload foto con metadati archeologici completi e gestione storage full"""

        object_name = f"{site_id}/{photo_id}"

        # Crea metadati usando il sistema unificato
        base_metadata = self._create_base_metadata(site_id, 'image/jpeg')
        metadata = self._merge_metadata(base_metadata, archaeological_metadata)

        # Usa il metodo di upload unificato
        result_url = await self._upload_with_retry(
            bucket_name=self.buckets['photos'],
            object_name=object_name,
            data=photo_data,
            content_type='image/jpeg',
            metadata=metadata,
            operation_name="photo upload",
            target_freed_mb=500
        )

        logger.info(f"Photo uploaded with metadata: {object_name} ({len(photo_data)} bytes)")
        return result_url

    async def get_photo_stream_url(self, photo_path: str, expires_hours: int = 24) -> Optional[str]:
        """Genera URL temporaneo per streaming foto grandi"""

        bucket, object_name = self._parse_minio_path(photo_path)

        # Usa il metodo base per generazione URL presigned
        return await self._generate_presigned_url(
            bucket_name=bucket,
            object_name=object_name,
            expires_hours=expires_hours,
            operation_name="photo stream URL generation"
        )

    async def search_photos_by_metadata(
        self,
        site_id: str,
        material: Optional[str] = None,
        inventory_number: Optional[str] = None,
        excavation_area: Optional[str] = None,
        chronology_period: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Ricerca foto per metadati archeologici"""

        prefix = f"{site_id}/"

        try:
            objects = await asyncio.to_thread(
                self._client.list_objects,
                bucket_name=self.buckets['photos'],
                prefix=prefix,
                recursive=True
            )

            results = []
            for obj in objects:
                # Ottieni metadati dell'oggetto
                stat = await asyncio.to_thread(
                    self._client.stat_object,
                    bucket_name=self.buckets['photos'],
                    object_name=obj.object_name
                )

                # Filtra per metadati archeologici
                metadata = stat.metadata
                if material and metadata.get('x-amz-meta-material') != material:
                    continue
                if inventory_number and metadata.get('x-amz-meta-inventory-number') != inventory_number:
                    continue
                if excavation_area and metadata.get('x-amz-meta-excavation-area') != excavation_area:
                    continue
                if chronology_period and metadata.get('x-amz-meta-chronology') != chronology_period:
                    continue

                results.append({
                    'object_name': obj.object_name,
                    'size': obj.size,
                    'last_modified': obj.last_modified,
                    'metadata': metadata,
                    'url': f"minio://{self.buckets['photos']}/{obj.object_name}"
                })

            return results

        except S3Error as e:
            logger.error(f"MinIO search error: {e}")
            return []

    async def upload_thumbnail(self, thumbnail_data: bytes, photo_id: str) -> str:
        """Upload thumbnail per foto con gestione errori storage full"""

        object_name = f"{photo_id}.jpg"

        # Crea metadati di base per thumbnail
        metadata = self._create_base_metadata("", 'image/jpeg')

        # Usa il metodo di upload unificato
        result_url = await self._upload_with_retry(
            bucket_name=self.buckets['thumbnails'],
            object_name=object_name,
            data=thumbnail_data,
            content_type='image/jpeg',
            metadata=metadata,
            operation_name="thumbnail upload",
            target_freed_mb=100
        )

        logger.info(f"Thumbnail uploaded: {object_name}")
        return result_url

    async def get_thumbnail_url(self, photo_id: str, expires_hours: int = 24) -> Optional[str]:
        """Genera URL per thumbnail"""

        object_name = f"{photo_id}.jpg"

        # Usa il metodo base per generazione URL presigned
        return await self._generate_presigned_url(
            bucket_name=self.buckets['thumbnails'],
            object_name=object_name,
            expires_hours=expires_hours,
            operation_name="thumbnail URL generation"
        )

    async def upload_document(
        self,
        document_data: bytes,
        document_id: str,
        site_id: str,
        document_metadata: Dict[str, Any]
    ) -> str:
        """
        Upload documento con metadati
        
        FIXED: Preserve original file extension instead of forcing .pdf.
        
        Previous issues:
        1. PDF extension duplication when document_id already had .pdf
        2. All documents (including Word files) getting .pdf extension forced
        
        Now it preserves the original extension from document_id.
        """

        # Use document_id as-is since us_file_service.py already includes the correct extension
        object_name = f"{site_id}/{document_id}"

        # Crea metadati usando il sistema unificato
        base_metadata = self._create_base_metadata(site_id, 'application/pdf')
        metadata = self._merge_metadata(base_metadata, {
            'document-type': document_metadata.get('document_type', ''),
            'title': document_metadata.get('title', ''),
            'author': document_metadata.get('author', ''),
            'date': document_metadata.get('date', '')
        })

        # Usa il metodo di upload unificato
        result_url = await self._upload_with_retry(
            bucket_name=self.buckets['documents'],
            object_name=object_name,
            data=document_data,
            content_type='application/pdf',
            metadata=metadata,
            operation_name="document upload",
            target_freed_mb=200
        )

        logger.info(f"Document uploaded: {object_name}")
        return result_url

    async def create_backup(self, site_id: str, backup_data: bytes, backup_name: str) -> str:
        """Crea backup del sito"""

        object_name = f"{site_id}/{backup_name}"

        # Crea metadati per backup
        base_metadata = self._create_base_metadata(site_id, 'application/zip')
        metadata = self._merge_metadata(base_metadata, {
            'backup-type': 'site_backup'
        })

        # Usa il metodo di upload unificato
        result_url = await self._upload_with_retry(
            bucket_name=self.buckets['backups'],
            object_name=object_name,
            data=backup_data,
            content_type='application/zip',
            metadata=metadata,
            operation_name="backup creation",
            target_freed_mb=1000  # I backup possono essere grandi
        )

        logger.info(f"Backup created: {object_name}")
        return result_url

    def _parse_minio_path(self, path: str) -> Tuple[str, str]:
        """Parse minio://bucket/object path or legacy path format"""
        if path.startswith('minio://'):
            path = path[8:]  # Remove minio://
            parts = path.split('/', 1)
            return parts[0], parts[1] if len(parts) > 1 else ''
        
        # Handle legacy path formats that need bucket mapping
        if path.startswith('sites/'):
            # Map sites/ paths to archaeological-photos bucket, removing 'sites/' prefix
            object_name = path[6:]  # Remove 'sites/' prefix (6 characters)
            return self.buckets['photos'], object_name
        elif path.startswith('storage/sites/'):
            # Handle legacy storage/sites/ paths - map to photos bucket
            object_name = path[14:]  # Remove 'storage/sites/' prefix
            return self.buckets['photos'], object_name
        elif path.startswith('storage/'):
            # Handle other storage/ paths - map to photos bucket by default
            object_name = path[8:]  # Remove 'storage/' prefix
            return self.buckets['photos'], object_name
        elif path.startswith('thumbnails/'):
            # Map thumbnails/ paths to thumbnails bucket
            object_name = path[11:]  # Remove 'thumbnails/' prefix
            return self.buckets['thumbnails'], object_name
        elif path.startswith('documents/'):
            # Map documents/ paths to documents bucket
            object_name = path[10:]  # Remove 'documents/' prefix
            return self.buckets['documents'], object_name
        else:
            # Default parsing for other formats
            parts = path.split('/', 1)
            if len(parts) > 1:
                first_part = parts[0]
                try:
                    UUID(first_part)
                    # Path starts with UUID/site_id, map to photos bucket with full path as object
                    return self.buckets['photos'], path
                except ValueError:
                    # Check if first part is 'storage' and handle it
                    if first_part == 'storage':
                        # Map to photos bucket, use rest of path as object name
                        return self.buckets['photos'], parts[1] if len(parts) > 1 else ''
            # FIXED: Handle deep zoom tiles paths (UUID/tiles/photo_id/...)
            elif len(parts) >= 3 and '/' in parts[1]:
                # Check if this looks like a deep zoom tiles path: UUID/tiles/photo_id/...
                try:
                    UUID(parts[0])  # Validate first part is UUID
                    # Check if second part starts with 'tiles/'
                    if parts[1].startswith('tiles/'):
                        # This is a deep zoom tiles path, map to tiles bucket
                        object_name = path  # Keep full path as object name
                        return self.buckets['tiles'], object_name
                except ValueError:
                    pass  # Not a UUID, continue to default handling
            
            return parts[0], parts[1] if len(parts) > 1 else ''

    async def get_storage_stats(self, site_id: str) -> Dict[str, Any]:
        """Ottieni statistiche storage per sito"""

        def _calculate_stats():
            try:
                total_size = 0
                photo_count = 0
                document_count = 0

                # Statistiche foto
                photo_objects = self._client.list_objects(
                    self.buckets['photos'],
                    prefix=f"{site_id}/",
                    recursive=True
                )
                for obj in photo_objects:
                    photo_count += 1
                    total_size += obj.size

                # Statistiche documenti
                doc_objects = self._client.list_objects(
                    self.buckets['documents'],
                    prefix=f"{site_id}/",
                    recursive=True
                )
                for obj in doc_objects:
                    document_count += 1
                    total_size += obj.size

                return {
                    'site_id': site_id,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'photo_count': photo_count,
                    'document_count': document_count,
                    'total_files': photo_count + document_count
                }

            except Exception as e:
                logger.error(f"Error getting storage stats: {e}")
                return {
                    'site_id': site_id,
                    'total_size_mb': 0,
                    'photo_count': 0,
                    'document_count': 0,
                    'total_files': 0
                }

        # Esegui il calcolo delle statistiche in un thread separato
        return await asyncio.to_thread(_calculate_stats)

    async def upload_tiles(self, site_id: str, photo_id: str, tiles_data: bytes) -> str:
        """Upload tiles per deep zoom viewing"""
        object_name = f"{site_id}/tiles/{photo_id}/tiles.zip"

        # Crea metadati per tiles
        base_metadata = self._create_base_metadata(site_id, 'application/zip')
        metadata = self._merge_metadata(base_metadata, {
            'photo-id': photo_id,
            'tile-type': 'deep-zoom'
        })

        # Usa il metodo di upload unificato
        result_url = await self._upload_with_retry(
            bucket_name=self.buckets['tiles'],
            object_name=object_name,
            data=tiles_data,
            content_type='application/zip',
            metadata=metadata,
            operation_name="tiles upload",
            target_freed_mb=300
        )

        logger.info(f"Tiles uploaded for photo: {photo_id}")
        return result_url

    async def stream_large_file(self, object_name: str, range_header: str = None):
        """Stream file grande con supporto Range requests"""
        try:
            bucket, obj_name = self._parse_minio_path(object_name)

            def _get_stream():
                if range_header:
                    # Parse range per streaming parziale
                    response = self._client.get_object(
                        bucket_name=bucket,
                        object_name=obj_name,
                        request_headers={"Range": range_header}
                    )
                else:
                    response = self._client.get_object(
                        bucket_name=bucket,
                        object_name=obj_name
                    )
                return response

            # Esegui l'operazione di get_object in un thread separato
            response = await asyncio.to_thread(_get_stream)
            return response

        except S3Error as e:
            logger.error(f"Stream error: {e}")
            return None

    async def backup_site_data(self, site_id: str) -> bool:
        """Backup completo dati sito archeologico"""
        try:
            # Lista tutti gli oggetti del sito
            objects = await asyncio.to_thread(
                self._client.list_objects,
                bucket_name=self.buckets['photos'],
                prefix=f"{site_id}/",
                recursive=True
            )

            # Conta oggetti per backup
            object_count = sum(1 for _ in objects)

            # Crea metadata backup
            backup_metadata = {
                'x-amz-meta-backup-type': 'site_backup',
                'x-amz-meta-site-id': site_id,
                'x-amz-meta-object-count': str(object_count),
                'x-amz-meta-backup-date': str(datetime.now().isoformat())
            }

            # TODO: Implementa creazione archive e upload
            logger.info(f"Site backup prepared: {site_id} ({object_count} objects)")
            return True

        except S3Error as e:
            logger.error(f"Backup error: {e}")
            return False

    async def get_photo_url(self, site_id: str, photo_id: str, expires: int = 3600) -> str:
        """Genera URL presigned per accesso temporaneo sicuro"""
        object_name = f"{site_id}/{photo_id}"

        # Converte secondi in ore per il metodo base
        expires_hours = expires // 3600

        # Usa il metodo base per generazione URL presigned
        url = await self._generate_presigned_url(
            bucket_name=self.buckets['photos'],
            object_name=object_name,
            expires_hours=expires_hours,
            operation_name="photo presigned URL generation"
        )

        return url

    async def process_photo_with_deep_zoom(
        self,
        photo_data: bytes,
        photo_id: str,
        site_id: str,
        archaeological_metadata: Dict[str, Any],
        generate_deep_zoom: bool = True
    ) -> Dict[str, Any]:
        """
        Processa foto con deep zoom se richiesto

        Args:
            photo_data: Dati immagine in bytes
            photo_id: ID della foto
            site_id: ID del sito archeologico
            archaeological_metadata: Metadati archeologici
            generate_deep_zoom: Se generare tiles deep zoom

        Returns:
            Dict con informazioni upload e deep zoom
        """
        try:
            # 1. Upload foto originale
            photo_url = await self.upload_photo_with_metadata(
                photo_data, photo_id, site_id, archaeological_metadata
            )

            result = {
                'photo_id': photo_id,
                'site_id': site_id,
                'photo_url': photo_url,
                'deep_zoom_available': False,
                'tile_count': 0,
                'metadata_url': None
            }

            # 2. Genera deep zoom se richiesto e immagine sufficientemente grande
            if generate_deep_zoom:
                try:
                    # Crea UploadFile temporaneo per il servizio deep zoom
                    from fastapi import UploadFile
                    import io as bytes_io

                    temp_file = UploadFile(
                        filename=f"{photo_id}.jpg",
                        file=bytes_io.BytesIO(photo_data)
                    )

                    # Import locale per evitare circular import
                    from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service

                    # Processa con deep zoom
                    deep_zoom_service = get_deep_zoom_minio_service()
                    deep_zoom_result = await deep_zoom_service.process_and_upload_tiles(
                        photo_id=photo_id,
                        original_file=temp_file,
                        site_id=site_id,
                        archaeological_metadata=archaeological_metadata
                    )

                    result.update({
                        'deep_zoom_available': True,
                        'tile_count': deep_zoom_result['total_tiles'],
                        'levels': deep_zoom_result['levels'],
                        'metadata_url': deep_zoom_result['metadata_url']
                    })

                    logger.info(f"Deep zoom processing completed for {photo_id}: {deep_zoom_result['total_tiles']} tiles")

                except Exception as e:
                    logger.warning(f"Deep zoom processing failed for {photo_id}: {e}")
                    # Non bloccare l'upload se deep zoom fallisce
                    result['deep_zoom_error'] = str(e)

            return result

        except Exception as e:
            logger.error(f"Photo processing with deep zoom failed for {photo_id}: {e}")
            raise StorageError(f"Photo processing failed: {str(e)}")

    async def get_deep_zoom_info(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni informazioni deep zoom per una foto"""
        try:
            # Import locale per evitare circular import
            from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service
            deep_zoom_service = get_deep_zoom_minio_service()
            return await deep_zoom_service.get_deep_zoom_info(site_id, photo_id)
        except Exception as e:
            logger.error(f"Error getting deep zoom info: {e}")
            return None

    async def get_tile_url(self, site_id: str, photo_id: str, level: int, x: int, y: int) -> Optional[str]:
        """Ottieni URL per singolo tile deep zoom"""
        try:
            # Import locale per evitare circular import
            from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service
            deep_zoom_service = get_deep_zoom_minio_service()
            return await deep_zoom_service.get_tile_url(site_id, photo_id, level, x, y)
        except Exception as e:
            logger.error(f"Error getting tile URL: {e}")
            return None

    async def get_tile_content(self, site_id: str, photo_id: str, level: int, x: int, y: int) -> Optional[bytes]:
        """Ottieni contenuto diretto del tile invece di URL presigned"""
        try:
            from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service
            deep_zoom_service = get_deep_zoom_minio_service()
            return await deep_zoom_service.get_tile_content(site_id, photo_id, level, x, y)
        except Exception as e:
            logger.error(f"Error getting tile content: {e}")
            return None

    async def get_file(self, object_path: str) -> bytes:
        """Scarica file da MinIO"""
        try:
            logger.info(f"Attempting to download file from MinIO: {object_path}")
            bucket, object_name = self._parse_minio_path(object_path)
            logger.info(f"Parsed MinIO path - Bucket: {bucket}, Object: {object_name}")

            def _download_file():
                # get_object returns HTTPResponse object, need to read content
                logger.info(f"Calling get_object on bucket {bucket} for object {object_name}")
                response = self._client.get_object(
                    bucket_name=bucket,
                    object_name=object_name
                )
                try:
                    # Read content from HTTPResponse object
                    content = response.read()
                    logger.info(f"Successfully read {len(content)} bytes from MinIO")
                    return content
                finally:
                    response.close()

            # Esegui l'intera operazione di download in un thread separato
            content = await asyncio.to_thread(_download_file)
            return content

        except Exception as e:
            # Check if it's a NoSuchKey error (file not found)
            if hasattr(e, 'code') and e.code == 'NoSuchKey':
                logger.info(f"File not found in MinIO: {object_path}")
                raise StorageNotFoundError(f"File non trovato: {object_path}")
            
            logger.error(f"Error downloading file {object_path}: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise StorageNotFoundError(f"File non trovato: {object_path}")

    async def get_file_stream(self, object_path: str, chunk_size: int = 64 * 1024) -> AsyncGenerator[bytes, None]:
        """
        Ottieni stream di un file da MinIO per StreamingResponse.
        Restituisce un generatore asincrono che legge il file a blocchi senza caricarlo tutto in RAM.
        NOTA: Questa funzione è awaitable e restituisce il generatore.
        """
        try:
            logger.debug(f"Streaming file from MinIO: {object_path}")
            bucket, object_name = self._parse_minio_path(object_path)
            
            # 1. Ottieni l'oggetto response da MinIO con retry logic
            retry_handler = RetryWithJitter(max_retries=3, base_delay=0.5, max_delay=5.0)
            
            async def get_object_with_retry():
                return await asyncio.to_thread(
                    self._client.get_object,
                    bucket_name=bucket,
                    object_name=object_name
                )
            
            response = await retry_handler.execute_with_retry(
                get_object_with_retry,
                f"get_object stream for {object_path}"
            )
            
            # 2. Definisci il generatore interno
            async def stream_generator():
                try:
                    while True:
                        # Leggi un blocco di dati (operazione bloccante eseguita in thread)
                        try:
                            chunk = await asyncio.to_thread(response.read, chunk_size)
                        except Exception as read_err:
                            logger.error(f"Error reading stream chunk from {object_path}: {read_err}")
                            raise
                            
                        if not chunk:
                            break
                        yield chunk
                finally:
                    # Assicura la chiusura della connessione
                    response.close()
                    response.release_conn()
                    logger.debug(f"Stream closed for {object_path}")
            
            # 3. Restituisci il generatore (avviandolo)
            return stream_generator()

        except S3Error as e:
            # Gestione esplicita errori S3/MinIO
            if e.code == 'NoSuchKey':
                logger.debug(f"File not found in MinIO: {object_path}")
                raise StorageNotFoundError(f"File non trovato: {object_path}")
            elif e.code == 'AccessDenied':
                logger.warning(f"Access denied to MinIO object: {object_path}")
                raise StorageError(f"Accesso negato: {object_path}")
            else:
                logger.error(f"MinIO S3Error streaming {object_path}: {e.code} - {e.message}")
                raise StorageError(f"Errore MinIO: {e.message}")
        except StorageNotFoundError:
            # Re-raise domain exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error streaming file {object_path}: {e}")
            raise StorageError(f"Errore nello streaming del file: {str(e)}")

    async def remove_file(self, object_path: str) -> bool:
        """Rimuovi file da MinIO"""
        try:
            bucket, object_name = self._parse_minio_path(object_path)

            def _remove_object():
                self._client.remove_object(
                    bucket_name=bucket,
                    object_name=object_name
                )

            await asyncio.to_thread(_remove_object)

            logger.info(f"File removed from MinIO: {object_path}")
            return True

        except Exception as e:
            logger.error(f"Error removing file {object_path}: {e}")
            return False

    async def remove_object_from_bucket(self, bucket_name: str, object_name: str) -> bool:
        """Rimuovi oggetto da bucket specifico"""
        try:
            def _remove_object():
                self._client.remove_object(
                    bucket_name=bucket_name,
                    object_name=object_name
                )

            await asyncio.to_thread(_remove_object)

            logger.info(f"Object removed from bucket {bucket_name}: {object_name}")
            return True

        except Exception as e:
            logger.error(f"Error removing object {object_name} from bucket {bucket_name}: {e}")
            return False


    async def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
        with_cleanup_on_full: bool = True
    ) -> str:
        """
        Upload bytes con gestione automatica storage full.

        Args:
            bucket: Bucket name
            object_name: Object key
            data: Bytes da uploadare
            content_type: MIME type
            metadata: Metadata opzionali
            with_cleanup_on_full: Se True, tenta cleanup automatico su storage full

        Returns:
            URL oggetto caricato

        Raises:
            StorageFullError: Se storage pieno e cleanup fallito
            StorageTemporaryError: Errore temporaneo, retry raccomandato
            StorageError: Altri errori storage
        """
        try:
            return await self._upload_with_retry(
                bucket_name=bucket,
                object_name=object_name,
                data=data,
                content_type=content_type,
                metadata=metadata
            )
        except Exception as e:
            if with_cleanup_on_full and self._is_storage_full_error(e):
                # Tenta cleanup automatico
                freed_mb = await self._emergency_cleanup()
                if freed_mb > 50:
                    # Retry dopo cleanup
                    return await self._upload_with_retry(
                        bucket_name=bucket,
                        object_name=object_name,
                        data=data,
                        content_type=content_type,
                        metadata=metadata
                    )
                raise StorageFullError(
                    f"Storage full. Cleanup freed only {freed_mb}MB",
                    freed_space_mb=freed_mb
                ) from e

            # Mappa altri errori
            raise self._map_minio_error(e) from e

    async def upload_json(
        self,
        bucket: str,
        object_name: str,
        data: dict,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """Upload JSON object"""
        json_bytes = json.dumps(data, indent=2).encode('utf-8')
        return await self.upload_bytes(
            bucket=bucket,
            object_name=object_name,
            data=json_bytes,
            content_type='application/json',
            metadata=metadata
        )

    async def upload_thumbnail(
        self,
        thumbnail_bytes: bytes,
        photo_id: str,
        site_id: Optional[str] = None
    ) -> str:
        """Upload thumbnail con path automatico"""
        object_name = f"thumbnails/{photo_id}.jpg"
        return await self.upload_bytes(
            bucket=self.buckets['thumbnails'],
            object_name=object_name,
            data=thumbnail_bytes,
            content_type='image/jpeg',
            metadata={'photo_id': photo_id}
        )

    async def upload_tile(
        self,
        tile_bytes: bytes,
        photo_id: str,
        level: int,
        col: int,
        row: int
    ) -> str:
        """Upload deep zoom tile"""
        object_name = f"tiles/{photo_id}/{level}/{col}_{row}.jpg"
        return await self.upload_bytes(
            bucket=self.buckets['tiles'],
            object_name=object_name,
            data=tile_bytes,
            content_type='image/jpeg',
            metadata={
                'photo_id': photo_id,
                'level': str(level),
                'col': str(col),
                'row': str(row)
            }
        )


    async def execute_with_retry(self, operation_func, operation_name: str):
        """Execute operation with retry pattern using domain exceptions"""
        return await self.retry_handler.execute_with_retry(operation_func, operation_name)


# Istanza globale
archaeological_minio_service = ArchaeologicalMinIOService()