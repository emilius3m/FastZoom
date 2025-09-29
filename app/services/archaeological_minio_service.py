# app/services/archaeological_minio_service.py - SERVIZIO MINIO ARCHEOLOGICO AVANZATO OTTIMIZZATO

import io
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from pathlib import Path
from loguru import logger
from fastapi import HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from minio import Minio
from minio.error import S3Error
from app.core.minio_settings import settings
# Import locale per evitare circular import
# from app.services.deep_zoom_minio_service import deep_zoom_minio_service


class ArchaeologicalMinIOService:
    """Servizio MinIO ottimizzato per dati archeologici con supporto avanzato"""

    def __init__(self):
        # Supporto sia settings che environment variables per flessibilità
        minio_url = settings.minio_url.replace("http://", "").replace("https://", "")
        access_key = settings.minio_access_key
        secret_key = settings.minio_secret_key
        secure = settings.minio_secure

        # Fallback a environment variables se settings non disponibili
        if not all([minio_url, access_key, secret_key]):
            minio_url = os.getenv("MINIO_ENDPOINT", "localhost:9000")
            access_key = os.getenv("MINIO_ACCESS_KEY", "")
            secret_key = os.getenv("MINIO_SECRET_KEY", "")
            secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

        self.client = Minio(
            endpoint=minio_url,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )

        # Bucket specializzati per archeologia
        self.buckets = {
            'photos': 'archaeological-photos',
            'documents': 'archaeological-documents',
            'tiles': 'deep-zoom-tiles',
            'thumbnails': 'thumbnails',
            'backups': 'site-backups'
        }

        # Inizializza bucket (sincrono per evitare problemi con event loop)
        self._initialize_buckets_sync()

    def _initialize_buckets_sync(self):
        """Inizializza bucket archeologici con policy avanzate"""
        try:
            # Include the legacy 'storage' bucket for compatibility
            all_buckets = dict(self.buckets)
            all_buckets['storage'] = 'storage'  # Add legacy bucket
            
            for bucket_type, bucket_name in all_buckets.items():
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
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
                            self.client.set_bucket_policy(bucket_name, json.dumps(policy))
                            logger.info(f"Set public policy for bucket: {bucket_name}")
                        except Exception as policy_error:
                            logger.warning(f"Could not set policy for {bucket_name}: {policy_error}")

        except Exception as e:
            logger.error(f"Error initializing buckets: {e}")

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
            'old_inventory_number': 'x-amz-meta-old-inventory-number',
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

        # Usa il nuovo sistema di mapping metadati
        metadata = self._map_archaeological_metadata(site_id, archaeological_metadata)

        try:
            # Upload con supporto multipart per file grandi (>5MB)
            result = await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.buckets['photos'],
                object_name=object_name,
                data=io.BytesIO(photo_data),
                length=len(photo_data),
                content_type='image/jpeg',
                metadata=metadata
            )

            logger.info(f"Photo uploaded with metadata: {object_name} ({len(photo_data)} bytes)")
            return f"minio://{self.buckets['photos']}/{object_name}"

        except S3Error as e:
            error_msg = str(e)
            
            # Check if it's a storage full error
            if "XMinioStorageFull" in error_msg or "minimum free drive threshold" in error_msg:
                logger.error(f"MinIO storage full during photo upload: {photo_id}")
                
                # Try emergency cleanup
                try:
                    from app.services.storage_management_service import storage_management_service
                    cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=500)
                    
                    if cleanup_result['success'] and cleanup_result['total_freed_mb'] > 200:
                        logger.info(f"Emergency cleanup successful, retrying photo upload for {photo_id}")
                        
                        # Retry upload after cleanup
                        result = await asyncio.to_thread(
                            self.client.put_object,
                            bucket_name=self.buckets['photos'],
                            object_name=object_name,
                            data=io.BytesIO(photo_data),
                            length=len(photo_data),
                            content_type='image/jpeg',
                            metadata=metadata
                        )
                        
                        logger.info(f"Photo uploaded after cleanup: {object_name} ({len(photo_data)} bytes)")
                        return f"minio://{self.buckets['photos']}/{object_name}"
                    else:
                        logger.error(f"Emergency cleanup insufficient for photo {photo_id}")
                        raise HTTPException(status_code=507, detail="Storage full, cleanup insufficient")
                        
                except Exception as cleanup_error:
                    logger.error(f"Emergency cleanup failed for photo {photo_id}: {cleanup_error}")
                    raise HTTPException(status_code=507, detail="Storage full, cleanup failed")
            else:
                logger.error(f"MinIO upload error: {e}")
                raise HTTPException(status_code=500, detail="Upload failed")

    async def get_photo_stream_url(self, photo_path: str, expires_hours: int = 24) -> Optional[str]:
        """Genera URL temporaneo per streaming foto grandi"""

        bucket, object_name = self._parse_minio_path(photo_path)

        try:
            # URL pre-firmato con scadenza
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                bucket_name=bucket,
                object_name=object_name,
                expires=timedelta(hours=expires_hours)
            )

            return url

        except S3Error as e:
            logger.error(f"MinIO URL generation error: {e}")
            return None

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
                self.client.list_objects,
                bucket_name=self.buckets['photos'],
                prefix=prefix,
                recursive=True
            )

            results = []
            for obj in objects:
                # Ottieni metadati dell'oggetto
                stat = await asyncio.to_thread(
                    self.client.stat_object,
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

        try:
            result = await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.buckets['thumbnails'],
                object_name=object_name,
                data=io.BytesIO(thumbnail_data),
                length=len(thumbnail_data),
                metadata={'Content-Type': 'image/jpeg'}
            )

            logger.info(f"Thumbnail uploaded: {object_name}")
            return f"{self.buckets['thumbnails']}/{object_name}"

        except S3Error as e:
            error_msg = str(e)
            
            # Check if it's a storage full error
            if "XMinioStorageFull" in error_msg or "minimum free drive threshold" in error_msg:
                logger.error(f"MinIO storage full during thumbnail upload: {photo_id}")
                
                # Try to trigger emergency cleanup
                try:
                    from app.services.storage_management_service import storage_management_service
                    cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=100)
                    
                    if cleanup_result['success'] and cleanup_result['total_freed_mb'] > 50:
                        logger.info(f"Emergency cleanup successful, retrying thumbnail upload for {photo_id}")
                        
                        # Retry upload after cleanup
                        result = await asyncio.to_thread(
                            self.client.put_object,
                            bucket_name=self.buckets['thumbnails'],
                            object_name=object_name,
                            data=io.BytesIO(thumbnail_data),
                            length=len(thumbnail_data),
                            metadata={'Content-Type': 'image/jpeg'}
                        )
                        
                        logger.info(f"Thumbnail uploaded after cleanup: {object_name}")
                        return f"{self.buckets['thumbnails']}/{object_name}"
                    else:
                        logger.error(f"Emergency cleanup insufficient for thumbnail {photo_id}")
                        raise HTTPException(status_code=507, detail="Storage full, cleanup insufficient")
                        
                except Exception as cleanup_error:
                    logger.error(f"Emergency cleanup failed for thumbnail {photo_id}: {cleanup_error}")
                    raise HTTPException(status_code=507, detail="Storage full, cleanup failed")
            else:
                logger.error(f"MinIO thumbnail upload error: {e}")
                raise HTTPException(status_code=500, detail="Thumbnail upload failed")

    async def get_thumbnail_url(self, photo_id: str, expires_hours: int = 24) -> Optional[str]:
        """Genera URL per thumbnail"""

        object_name = f"{photo_id}.jpg"

        try:
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                bucket_name=self.buckets['thumbnails'],
                object_name=object_name,
                expires=timedelta(hours=expires_hours)
            )

            return url

        except S3Error as e:
            logger.error(f"MinIO thumbnail URL generation error: {e}")
            return None

    async def upload_document(
        self,
        document_data: bytes,
        document_id: str,
        site_id: str,
        document_metadata: Dict[str, Any]
    ) -> str:
        """Upload documento con metadati"""

        object_name = f"{site_id}/{document_id}.pdf"

        metadata = {
            'x-amz-meta-site-id': site_id,
            'x-amz-meta-document-type': document_metadata.get('document_type', ''),
            'x-amz-meta-title': document_metadata.get('title', ''),
            'x-amz-meta-author': document_metadata.get('author', ''),
            'x-amz-meta-date': document_metadata.get('date', ''),
            'Content-Type': 'application/pdf'
        }

        try:
            result = await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.buckets['documents'],
                object_name=object_name,
                data=io.BytesIO(document_data),
                length=len(document_data),
                metadata=metadata
            )

            logger.info(f"Document uploaded: {object_name}")
            return f"minio://{self.buckets['documents']}/{object_name}"

        except S3Error as e:
            logger.error(f"MinIO document upload error: {e}")
            raise HTTPException(status_code=500, detail="Document upload failed")

    async def create_backup(self, site_id: str, backup_data: bytes, backup_name: str) -> str:
        """Crea backup del sito"""

        object_name = f"{site_id}/{backup_name}"

        try:
            result = await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.buckets['backups'],
                object_name=object_name,
                data=io.BytesIO(backup_data),
                length=len(backup_data),
                metadata={
                    'Content-Type': 'application/zip',
                    'x-amz-meta-backup-type': 'site_backup',
                    'x-amz-meta-site-id': site_id
                }
            )

            logger.info(f"Backup created: {object_name}")
            return f"minio://{self.buckets['backups']}/{object_name}"

        except S3Error as e:
            logger.error(f"MinIO backup error: {e}")
            raise HTTPException(status_code=500, detail="Backup creation failed")

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
            return parts[0], parts[1] if len(parts) > 1 else ''

    async def get_storage_stats(self, site_id: str) -> Dict[str, Any]:
        """Ottieni statistiche storage per sito"""

        try:
            total_size = 0
            photo_count = 0
            document_count = 0

            # Statistiche foto
            photo_objects = self.client.list_objects(
                self.buckets['photos'],
                prefix=f"{site_id}/",
                recursive=True
            )
            for obj in photo_objects:
                photo_count += 1
                total_size += obj.size

            # Statistiche documenti
            doc_objects = self.client.list_objects(
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

    async def upload_tiles(self, site_id: str, photo_id: str, tiles_data: bytes) -> str:
        """Upload tiles per deep zoom viewing"""
        object_name = f"{site_id}/tiles/{photo_id}/tiles.zip"

        try:
            result = await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.buckets['tiles'],
                object_name=object_name,
                data=io.BytesIO(tiles_data),
                length=len(tiles_data),
                content_type='application/zip',
                metadata={
                    'x-amz-meta-site-id': site_id,
                    'x-amz-meta-photo-id': photo_id,
                    'x-amz-meta-tile-type': 'deep-zoom'
                }
            )

            logger.info(f"Tiles uploaded for photo: {photo_id}")
            return f"minio://{self.buckets['tiles']}/{object_name}"

        except S3Error as e:
            logger.error(f"Tiles upload error: {e}")
            raise HTTPException(status_code=500, detail="Tiles upload failed")

    async def stream_large_file(self, object_name: str, range_header: str = None):
        """Stream file grande con supporto Range requests"""
        try:
            bucket, obj_name = self._parse_minio_path(object_name)

            if range_header:
                # Parse range per streaming parziale
                response = await asyncio.to_thread(
                    self.client.get_object,
                    bucket_name=bucket,
                    object_name=obj_name,
                    request_headers={"Range": range_header}
                )
            else:
                response = await asyncio.to_thread(
                    self.client.get_object,
                    bucket_name=bucket,
                    object_name=obj_name
                )

            return response

        except S3Error as e:
            logger.error(f"Stream error: {e}")
            return None

    async def backup_site_data(self, site_id: str) -> bool:
        """Backup completo dati sito archeologico"""
        try:
            # Lista tutti gli oggetti del sito
            objects = await asyncio.to_thread(
                self.client.list_objects,
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

        try:
            # URL presigned per download sicuro
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                bucket_name=self.buckets['photos'],
                object_name=object_name,
                expires=timedelta(seconds=expires)
            )
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

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
                    from app.services.deep_zoom_minio_service import deep_zoom_minio_service

                    # Processa con deep zoom
                    deep_zoom_result = await deep_zoom_minio_service.process_and_upload_tiles(
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
            raise HTTPException(status_code=500, detail=f"Photo processing failed: {str(e)}")

    async def get_deep_zoom_info(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni informazioni deep zoom per una foto"""
        try:
            # Import locale per evitare circular import
            from app.services.deep_zoom_minio_service import deep_zoom_minio_service
            return await deep_zoom_minio_service.get_deep_zoom_info(site_id, photo_id)
        except Exception as e:
            logger.error(f"Error getting deep zoom info: {e}")
            return None

    async def get_tile_url(self, site_id: str, photo_id: str, level: int, x: int, y: int) -> Optional[str]:
        """Ottieni URL per singolo tile deep zoom"""
        try:
            # Import locale per evitare circular import
            from app.services.deep_zoom_minio_service import deep_zoom_minio_service
            return await deep_zoom_minio_service.get_tile_url(site_id, photo_id, level, x, y)
        except Exception as e:
            logger.error(f"Error getting tile URL: {e}")
            return None

    async def get_file(self, object_path: str) -> bytes:
        """Scarica file da MinIO"""
        try:
            bucket, object_name = self._parse_minio_path(object_path)

            # get_object returns HTTPResponse object, need to read content
            response = await asyncio.to_thread(
                self.client.get_object,
                bucket_name=bucket,
                object_name=object_name
            )

            # Read content from HTTPResponse object
            content = response.read()
            response.close()

            return content

        except Exception as e:
            logger.error(f"Error downloading file {object_path}: {e}")
            raise HTTPException(status_code=404, detail=f"File non trovato: {object_path}")

    async def remove_file(self, object_path: str) -> bool:
        """Rimuovi file da MinIO"""
        try:
            bucket, object_name = self._parse_minio_path(object_path)

            await asyncio.to_thread(
                self.client.remove_object,
                bucket_name=bucket,
                object_name=object_name
            )

            logger.info(f"File removed from MinIO: {object_path}")
            return True

        except Exception as e:
            logger.error(f"Error removing file {object_path}: {e}")
            return False

    async def remove_object_from_bucket(self, bucket_name: str, object_name: str) -> bool:
        """Rimuovi oggetto da bucket specifico"""
        try:
            await asyncio.to_thread(
                self.client.remove_object,
                bucket_name=bucket_name,
                object_name=object_name
            )

            logger.info(f"Object removed from bucket {bucket_name}: {object_name}")
            return True

        except Exception as e:
            logger.error(f"Error removing object {object_name} from bucket {bucket_name}: {e}")
            return False


# Istanza globale
archaeological_minio_service = ArchaeologicalMinIOService()