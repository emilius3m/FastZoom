# app/services/storage_service.py - GESTIONE STORAGE MINIO CORRETTA

import io
from typing import Optional, Tuple, Dict, Any
from uuid import uuid4
from pathlib import Path
from fastapi import UploadFile, HTTPException
from loguru import logger
from minio.error import S3Error
from app.core.config import get_settings
from app.services.archaeological_minio_service import archaeological_minio_service

settings = get_settings()


class StorageService:
    """Servizio per gestione storage MinIO"""

    def __init__(self):
        self.bucket_name = settings.minio_bucket
        self.base_url = f"{settings.minio_url}/{self.bucket_name}"
        logger.info(f"MinIO Storage service initialized: {self.base_url}")

    async def ensure_bucket_exists(self):
        """Assicura che il bucket esista"""
        try:
            # Il servizio archeologico gestisce già la creazione dei bucket durante l'inizializzazione
            # Verifica che il servizio sia disponibile
            if archaeological_minio_service:
                logger.info(f"Archaeological MinIO service available - buckets initialized")
            else:
                raise Exception("Archaeological MinIO service not available")
        except Exception as e:
            logger.error(f"Error with bucket: {e}")
            # Don't raise exception, allow fallback to local storage
            logger.warning("MinIO not available, will use local storage as fallback")

    async def save_upload_file(
            self,
            file: UploadFile,
            site_id: str,
            user_id: str
    ) -> Tuple[str, str, int]:
        """
        Salva file uploadato su MinIO
        Returns: Tuple[filename, minio_path, file_size]

        🔧 CORREZIONE CRITICA: Path compatibili con photos_router.py
        """
        # Validazione file
        if not await self._validate_file(file):
            raise HTTPException(status_code=400, detail="File non valido")

        # Assicurati che il bucket esista
        await self.ensure_bucket_exists()

        # Genera nome file univoco
        file_extension = Path(file.filename).suffix.lower()
        unique_filename = f"{site_id}_{user_id}_{uuid4().hex[:8]}{file_extension}"

        # 🔧 CORREZIONE CRITICA: Path MinIO senza prefisso "sites/"
        # Il photos_router.py controlla se il path inizia con "sites/" per decidere se usare MinIO
        minio_object_name = f"{site_id}/{unique_filename}"

        # Legge contenuto file una volta sola
        file_content = await file.read()
        file_size = len(file_content)

        if file_size == 0:
            raise HTTPException(status_code=400, detail="File vuoto")

        # Salva file su MinIO archeologico
        try:
            # Usa il servizio archeologico per upload con metadati
            photo_url = await archaeological_minio_service.upload_photo_with_metadata(
                file_content,
                unique_filename,
                site_id,
                {
                    'file_size': file_size,
                    'original_filename': file.filename,
                    'content_type': file.content_type or 'application/octet-stream'
                }
            )

            # Parse actual object name from returned URL
            if photo_url.startswith("minio://"):
                parsed = photo_url.replace("minio://", "").split("/", 1)
                bucket = parsed[0]
                actual_object_name = parsed[1] if len(parsed) > 1 else unique_filename
            else:
                actual_object_name = minio_object_name

            logger.info(f"File uploaded to Archaeological MinIO: {actual_object_name} ({file_size} bytes)")

            # Return actual stored path for DB consistency
            return unique_filename, actual_object_name, file_size

        except Exception as e:
            logger.warning(f"Archaeological MinIO upload failed: {e}, falling back to local storage")
            # Fallback a storage locale
            return await self._save_file_locally_from_content(
                file_content, site_id, user_id, unique_filename, f"storage/site/{site_id}/{unique_filename}"
            )

    async def delete_file(self, object_name: str) -> bool:
        """Elimina file da MinIO archeologico"""
        try:
            # 🔧 CORREZIONE: Rimuovi prefisso "sites/" se presente
            clean_object_name = object_name
            if object_name.startswith("sites/"):
                clean_object_name = object_name[6:]  # Rimuove "sites/"
                logger.info(f"Cleaned object name from '{object_name}' to '{clean_object_name}'")

            # Usa il servizio archeologico per eliminare file
            success = await archaeological_minio_service.remove_file(clean_object_name)

            if success:
                logger.info(f"File deleted from Archaeological MinIO: {clean_object_name}")
                return True
            else:
                logger.error(f"Error deleting file {clean_object_name}")
                return False

        except Exception as e:
            logger.error(f"Error deleting file {object_name}: {e}")
            return False

    async def file_exists(self, object_name: str) -> bool:
        """Verifica se un file esiste in MinIO"""
        try:
            # 🔧 CORREZIONE: Rimuovi prefisso "sites/" se presente
            clean_object_name = object_name
            if object_name.startswith("sites/"):
                clean_object_name = object_name[6:]  # Rimuove "sites/"

            return await archaeological_minio_service.file_exists(clean_object_name)
        except Exception as e:
            logger.warning(f"Error checking file existence {object_name}: {e}")
            return False

    async def get_file_info(self, object_name: str) -> Optional[Dict[str, Any]]:
        """Ottiene informazioni file da MinIO"""
        try:
            # 🔧 CORREZIONE: Rimuovi prefisso "sites/" se presente
            clean_object_name = object_name
            if object_name.startswith("sites/"):
                clean_object_name = object_name[6:]  # Rimuove "sites/"

            # Verifica esistenza
            exists = await self.file_exists(object_name)

            return {
                "object_name": clean_object_name,
                "url": f"{self.base_url}/{clean_object_name}",
                "exists": exists
            }

        except Exception as e:
            logger.error(f"Error getting file info {object_name}: {e}")
            return None

    async def get_presigned_url(self, object_name: str, expiry_seconds: int = 3600) -> Optional[str]:
        """Ottiene URL pre-firmato per accesso diretto"""
        try:
            # 🔧 CORREZIONE: Rimuovi prefisso "sites/" se presente
            clean_object_name = object_name
            if object_name.startswith("sites/"):
                clean_object_name = object_name[6:]  # Rimuove "sites/"
                logger.debug(f"Cleaned object name for presigned URL: '{object_name}' -> '{clean_object_name}'")

            return await archaeological_minio_service.get_presigned_url(clean_object_name, expiry_seconds)
        except Exception as e:
            logger.error(f"Error getting presigned URL for {object_name}: {e}")
            return None

    async def _validate_file(self, file: UploadFile) -> bool:
        """Valida file uploadato"""
        # Controlla se file è presente
        if not file or not file.filename:
            return False

        # Dimensioni massime
        max_size = settings.max_photo_size_mb * 1024 * 1024
        file_size = 0

        # Legge file per validazione
        content = await file.read()
        file_size = len(content)

        # Reset file pointer
        await file.seek(0)

        if file_size > max_size:
            logger.warning(f"File too large: {file_size} bytes (max: {max_size})")
            return False

        if file_size == 0:
            logger.warning("Empty file")
            return False

        # Estensioni permesse
        allowed_extensions = {f'.{fmt}' for fmt in settings.supported_formats_list}
        file_extension = Path(file.filename).suffix.lower()

        if file_extension not in allowed_extensions:
            logger.warning(f"File type not allowed: {file_extension}")
            return False

        # MIME types permesse
        mime_mapping = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.bmp': 'image/bmp',
            '.gif': 'image/gif',
            '.raw': 'image/x-raw',
            '.cr2': 'image/x-canon-cr2',
            '.nef': 'image/x-nikon-nef',
            '.arw': 'image/x-sony-arw',
            '.dng': 'image/x-adobe-dng'
        }

        expected_mime = mime_mapping.get(file_extension)
        if expected_mime and hasattr(file, 'content_type') and file.content_type and file.content_type != expected_mime:
            logger.warning(f"MIME type mismatch: expected {expected_mime}, got {file.content_type}")
            return False

        return True

    def get_site_upload_path(self, site_id: str) -> str:
        """Restituisce path MinIO per sito (SENZA prefisso sites/)"""
        return f"{site_id}/"

    def get_thumbnail_path(self, photo_id: str) -> str:
        """Restituisce path MinIO per thumbnail"""
        return f"thumbnails/{photo_id}.jpg"

    async def upload_thumbnail_with_metadata(
            self,
            thumbnail_data: bytes,
            photo_id: str,
            site_id: str,
            photo_metadata: Dict[str, Any] = None
    ) -> str:
        """
        Upload thumbnail usando il servizio archeologico MinIO
        """
        try:
            # Usa il servizio archeologico per upload thumbnail
            thumbnail_url = await archaeological_minio_service.upload_thumbnail(
                thumbnail_data, photo_id
            )

            logger.info(f"Thumbnail uploaded with archaeological service: {photo_id}")
            return thumbnail_url

        except Exception as e:
            logger.error(f"Archaeological MinIO thumbnail upload failed: {e}")
            # Fallback al metodo precedente
            return await self._upload_thumbnail_fallback(thumbnail_data, photo_id, site_id)

    async def _upload_thumbnail_fallback(
            self,
            thumbnail_data: bytes,
            photo_id: str,
            site_id: str
    ) -> str:
        """Fallback per upload thumbnail"""
        try:
            # Upload con servizio archeologico
            thumbnail_url = await archaeological_minio_service.upload_thumbnail(
                thumbnail_data, photo_id
            )

            logger.info(f"Thumbnail uploaded with archaeological service fallback: {photo_id}")
            return thumbnail_url

        except Exception as e:
            logger.error(f"Fallback thumbnail upload failed: {e}")
            raise HTTPException(status_code=500, detail="Thumbnail upload failed")

    async def _save_file_locally_from_content(
            self,
            file_content: bytes,
            site_id: str,
            user_id: str,
            unique_filename: str,
            object_name: str
    ) -> Tuple[str, str, int]:
        """
        Salva file localmente da contenuto bytes come fallback quando MinIO non è disponibile
        """
        try:
            # Crea directory se non esiste
            upload_dir = Path(settings.upload_dir) / "storage" / "sites" / site_id
            upload_dir.mkdir(parents=True, exist_ok=True)

            # Salva file
            file_path = upload_dir / unique_filename
            with open(file_path, "wb") as f:
                f.write(file_content)

            file_size = len(file_content)

            # 🔧 CORREZIONE: Restituisci path che photos_router.py riconoscerà come locale
            # Il photos_router.py controlla: elif photo.file_path.startswith("storage/")
            relative_path = f"storage/site/{site_id}/{unique_filename}"

            logger.info(f"File saved locally: {file_path} ({file_size} bytes)")
            return unique_filename, relative_path, file_size

        except Exception as e:
            logger.error(f"Error saving file locally from content: {e}")
            raise HTTPException(status_code=500, detail="Errore salvataggio file locale")


# Istanza globale
storage_service = StorageService()
