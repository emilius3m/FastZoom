# app/services/photo_serving_service.py - Consolidated photo serving service
"""
Consolidated service for photo serving operations.
Eliminates duplication between photos_router and sites_photos API endpoints.
"""

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
import io
from uuid import UUID
from typing import Optional, Tuple

from app.database.session import get_async_session
from app.models import Photo
from app.services.archaeological_minio_service import archaeological_minio_service


class PhotoServingService:
    """Consolidated service for all photo serving operations."""

    @staticmethod
    def clean_minio_path(file_path: str) -> str:
        """
        🔧 FUNZIONE DI SUPPORTO: Pulisce path per compatibilità MinIO
        Rimuove prefisso "sites/" se presente
        """
        if file_path and file_path.startswith("sites/"):
            cleaned = file_path[6:]  # Rimuove "sites/"
            logger.debug(f"Cleaned path: '{file_path}' -> '{cleaned}'")
            return cleaned
        return file_path

    @staticmethod
    async def get_photo_from_db(db: AsyncSession, photo_id: UUID) -> Optional[Photo]:
        """Retrieve photo record from database with error handling."""
        try:
            photo_query = select(Photo).where(Photo.id == photo_id)
            photo = await db.execute(photo_query)
            return photo.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving photo {photo_id} from database: {e}")
            return None

    @staticmethod
    async def serve_file_from_minio(file_path: str, mime_type: str = "image/jpeg") -> StreamingResponse:
        """Serve file from MinIO storage."""
        try:
            clean_path = PhotoServingService.clean_minio_path(file_path)
            logger.info(f"Attempting to retrieve file from Archaeological MinIO: {clean_path}")

            file_data = await archaeological_minio_service.get_file(clean_path)

            if file_data and isinstance(file_data, bytes):
                logger.info(f"Successfully retrieved file from Archaeological MinIO: {clean_path}")
                return StreamingResponse(
                    io.BytesIO(file_data),
                    media_type=mime_type,
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            else:
                logger.warning(f"Archaeological MinIO returned invalid data for {clean_path}: {type(file_data)}")
                raise HTTPException(status_code=404, detail="File data non valido")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error serving file from Archaeological MinIO: {e}")
            raise HTTPException(status_code=500, detail=f"Errore nel servire file: {str(e)}")

    @staticmethod
    def serve_file_from_local(file_path: str, mime_type: str = "image/jpeg") -> FileResponse:
        """Serve file from local filesystem."""
        try:
            file_path_obj = Path(file_path)
            logger.info(f"Checking local file path: {file_path_obj}")

            if file_path_obj.exists():
                logger.info(f"Serving local file: {file_path_obj}")
                return FileResponse(
                    file_path_obj,
                    media_type=mime_type,
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            else:
                logger.warning(f"Local file not found: {file_path_obj}")
                raise HTTPException(status_code=404, detail="File locale non trovato")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error serving local file: {e}")
            raise HTTPException(status_code=500, detail=f"Errore nel servire file locale: {str(e)}")

    @staticmethod
    def serve_fallback_thumbnail() -> FileResponse:
        """Serve fallback thumbnail when all other methods fail."""
        try:
            fallback_thumbnail_path = Path("app/static/img/logo/logo.jpg")
            logger.info(f"Checking fallback thumbnail path: {fallback_thumbnail_path}")

            if fallback_thumbnail_path.exists():
                logger.warning("SERVING FALLBACK THUMBNAIL - this should not happen if thumbnail was generated correctly!")
                return FileResponse(
                    fallback_thumbnail_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            else:
                logger.error(f"Fallback thumbnail not found at: {fallback_thumbnail_path}")
                raise HTTPException(status_code=404, detail="Thumbnail di fallback non disponibile")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error serving fallback thumbnail: {e}")
            raise HTTPException(status_code=500, detail=f"Errore nel servire thumbnail di fallback: {str(e)}")

    @staticmethod
    async def serve_photo_thumbnail(photo_id: UUID, db: AsyncSession) -> StreamingResponse:
        """Serve photo thumbnail with consolidated logic."""
        try:
            # Recupera info foto dal database
            photo = await PhotoServingService.get_photo_from_db(db, photo_id)

            if not photo:
                raise HTTPException(status_code=404, detail="Foto non trovata")

            # Determina path thumbnail
            if photo.thumbnail_path:
                logger.info(f"Photo {photo_id} has thumbnail_path: {photo.thumbnail_path}")

                # Se thumbnail è su MinIO
                if photo.thumbnail_path.startswith("thumbnails/") or not photo.thumbnail_path.startswith("storage/"):
                    try:
                        return await PhotoServingService.serve_file_from_minio(photo.thumbnail_path)
                    except HTTPException as e:
                        if e.status_code == 404:
                            logger.warning(f"Thumbnail file not found in MinIO: {photo.thumbnail_path}, using fallback")
                        else:
                            logger.error(f"Error serving thumbnail from MinIO: {e}")
                        # Fall through to fallback

                # Se thumbnail è su filesystem locale
                elif photo.thumbnail_path.startswith("storage/thumbnails/"):
                    try:
                        return PhotoServingService.serve_file_from_local(photo.thumbnail_path)
                    except HTTPException as e:
                        if e.status_code == 404:
                            logger.warning(f"Thumbnail file not found locally: {photo.thumbnail_path}, using fallback")
                        else:
                            logger.error(f"Error serving thumbnail from local: {e}")
                        # Fall through to fallback

            # Fallback: restituisci thumbnail di default
            logger.warning(f"All thumbnail retrieval methods failed for photo {photo_id}, using fallback")
            return PhotoServingService.serve_fallback_thumbnail()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error serving thumbnail: {e}")
            raise HTTPException(status_code=500, detail="Errore nel servire thumbnail")

    @staticmethod
    async def serve_photo_full(photo_id: UUID, db: AsyncSession) -> StreamingResponse:
        """Serve full photo with consolidated logic."""
        try:
            # Recupera info foto dal database
            photo = await PhotoServingService.get_photo_from_db(db, photo_id)

            if not photo:
                raise HTTPException(status_code=404, detail="Foto non trovata")

            # Determina path file
            if photo.filepath:
                logger.info(f"Photo {photo_id} has filepath: {photo.filepath}")

                # Se file è su MinIO
                if photo.filepath.startswith("sites/") or not photo.filepath.startswith("storage/"):
                    return await PhotoServingService.serve_file_from_minio(
                        photo.filepath,
                        photo.mime_type or "image/jpeg"
                    )

                # Se file è su filesystem locale
                elif photo.filepath.startswith("storage/") or photo.filepath.startswith("app/static/"):
                    return PhotoServingService.serve_file_from_local(
                        photo.filepath,
                        photo.mime_type or "image/jpeg"
                    )

            # Se tutto fallisce, restituisci 404
            raise HTTPException(status_code=404, detail="Immagine non disponibile")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error serving full image: {e}")
            raise HTTPException(status_code=500, detail="Errore nel servire immagine")

    @staticmethod
    async def serve_photo_download(photo_id: UUID, db: AsyncSession) -> StreamingResponse:
        """Serve photo for download with consolidated logic."""
        try:
            # Recupera info foto dal database
            photo = await PhotoServingService.get_photo_from_db(db, photo_id)

            if not photo:
                raise HTTPException(status_code=404, detail="Foto non trovata")

            # Determina path file
            if photo.filepath:
                logger.info(f"Photo {photo_id} download request for filepath: {photo.filepath}")

                # Determina filename per il download
                filename = photo.original_filename or photo.filename or f"photo_{photo_id}.jpg"

                # Se file è su MinIO
                if photo.filepath.startswith("sites/") or not photo.filepath.startswith("storage/"):
                    try:
                        clean_path = PhotoServingService.clean_minio_path(photo.filepath)
                        logger.info(f"Attempting to download from Archaeological MinIO: {clean_path}")

                        file_data = await archaeological_minio_service.get_file(clean_path)

                        if file_data and isinstance(file_data, bytes):
                            logger.info(f"Successfully downloading file from Archaeological MinIO for photo {photo_id}")
                            return StreamingResponse(
                                io.BytesIO(file_data),
                                media_type=photo.mime_type or "image/jpeg",
                                headers={
                                    "Content-Disposition": f"attachment; filename=\"{filename}\"",
                                    "Cache-Control": "private, max-age=0"
                                }
                            )
                        else:
                            logger.warning(f"Archaeological MinIO returned invalid data for download {clean_path}")
                            raise HTTPException(status_code=404, detail="File data non valido")

                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.error(f"Error downloading file from Archaeological MinIO: {e}")
                        raise HTTPException(status_code=500, detail=f"Errore nel download: {str(e)}")

                # Se file è su filesystem locale
                elif photo.filepath.startswith("storage/") or photo.filepath.startswith("app/static/uploads/"):
                    file_path = Path(photo.filepath)
                    logger.info(f"Checking local file path for download: {file_path}")

                    if file_path.exists():
                        logger.info(f"Serving local file for download: {photo_id}")
                        return FileResponse(
                            file_path,
                            media_type=photo.mime_type or "image/jpeg",
                            headers={
                                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                                "Cache-Control": "private, max-age=0"
                            }
                        )
                    else:
                        logger.warning(f"Local file not found for download: {file_path}")
                        raise HTTPException(status_code=404, detail="File locale non trovato per il download")

            # Se tutto fallisce, restituisci 404
            raise HTTPException(status_code=404, detail="File non disponibile per il download")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error downloading photo: {e}")
            raise HTTPException(status_code=500, detail="Errore nel download del file")


# Create singleton instance
photo_serving_service = PhotoServingService()