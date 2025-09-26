# app/routes/photos_router.py - PHOTO ENDPOINTS CORRETTI

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
import io
from uuid import UUID

from app.database.session import get_async_session
from app.models.photos import Photo
from app.services.archaeological_minio_service import archaeological_minio_service

photos_router = APIRouter(prefix="/photos", tags=["photos"])


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


@photos_router.get("/{photo_id}/thumbnail")
async def get_photo_thumbnail(
        photo_id: UUID,
        db: AsyncSession = Depends(get_async_session)
):
    """Serve thumbnail foto (endpoint senza prefisso /sites/)"""
    try:
        # Recupera info foto dal database
        photo_query = select(Photo).where(Photo.id == photo_id)
        photo = await db.execute(photo_query)
        photo = photo.scalar_one_or_none()

        if not photo:
            raise HTTPException(status_code=404, detail="Foto non trovata")

        # Determina path thumbnail
        if photo.thumbnail_path:
            logger.info(f"Photo {photo_id} has thumbnail_path: {photo.thumbnail_path}")

            # Se thumbnail è su MinIO (archaeological service)
            if photo.thumbnail_path.startswith("thumbnails/") or not photo.thumbnail_path.startswith("storage/"):
                try:
                    # 🔧 CORREZIONE: Pulisci path prima di usarlo
                    clean_path = clean_minio_path(photo.thumbnail_path)
                    logger.info(f"Attempting to retrieve thumbnail from Archaeological MinIO: {clean_path}")

                    thumbnail_data = await archaeological_minio_service.get_file(clean_path)

                    if thumbnail_data and isinstance(thumbnail_data, bytes):
                        logger.info(f"Successfully serving thumbnail from Archaeological MinIO for photo {photo_id}")
                        return StreamingResponse(
                            io.BytesIO(thumbnail_data),
                            media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=3600"}
                        )
                    else:
                        logger.warning(
                            f"Archaeological MinIO returned invalid data for thumbnail {clean_path}: {type(thumbnail_data)}")

                except HTTPException as http_err:
                    # Log specific HTTP errors (like 404) and continue to fallback
                    logger.warning(
                        f"HTTP error serving thumbnail from Archaeological MinIO: {http_err.status_code}: {http_err.detail}")
                except Exception as e:
                    logger.warning(f"Error serving thumbnail from Archaeological MinIO: {e}")

            # Se thumbnail è su filesystem locale
            elif photo.thumbnail_path.startswith("storage/thumbnails/"):
                thumbnail_path = Path(photo.thumbnail_path)
                logger.info(f"Checking local thumbnail path: {thumbnail_path}")

                if thumbnail_path.exists():
                    logger.info(f"Serving local thumbnail for photo {photo_id}")
                    return FileResponse(
                        thumbnail_path,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                else:
                    logger.warning(f"Local thumbnail not found: {thumbnail_path}")

        # Fallback: restituisci thumbnail di default
        logger.warning(f"All thumbnail retrieval methods failed for photo {photo_id}, using fallback")
        try:
            fallback_thumbnail_path = Path("app/static/img/logo/logo.jpg")
            logger.info(f"Checking fallback thumbnail path: {fallback_thumbnail_path}")

            if fallback_thumbnail_path.exists():
                logger.warning(
                    f"SERVING FALLBACK THUMBNAIL for photo {photo_id} - this should not happen if thumbnail was generated correctly!")
                return FileResponse(
                    fallback_thumbnail_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            else:
                logger.error(f"Fallback thumbnail not found at: {fallback_thumbnail_path}")

        except Exception as e:
            logger.warning(f"Error serving fallback thumbnail: {e}")

        # Se tutto fallisce, restituisci 404
        raise HTTPException(status_code=404, detail="Thumbnail non disponibile")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving thumbnail: {e}")
        raise HTTPException(status_code=500, detail="Errore nel servire thumbnail")


@photos_router.get("/{photo_id}/full")
async def get_photo_full(
        photo_id: UUID,
        db: AsyncSession = Depends(get_async_session)
):
    """Serve immagine completa"""
    try:
        # Recupera info foto dal database
        photo_query = select(Photo).where(Photo.id == photo_id)
        photo = await db.execute(photo_query)
        photo = photo.scalar_one_or_none()

        if not photo:
            raise HTTPException(status_code=404, detail="Foto non trovata")

        # Determina path file
        if photo.file_path:
            logger.info(f"Photo {photo_id} has file_path: {photo.file_path}")

            # Se file è su MinIO (sites/ prefix or other MinIO paths)
            if photo.file_path.startswith("sites/") or not photo.file_path.startswith("storage/"):
                try:
                    # 🔧 CORREZIONE: Pulisci path prima di usarlo
                    clean_path = clean_minio_path(photo.file_path)
                    logger.info(f"Attempting to retrieve full image from Archaeological MinIO: {clean_path}")

                    file_data = await archaeological_minio_service.get_file(clean_path)

                    if file_data and isinstance(file_data, bytes):
                        logger.info(f"Successfully serving full image from Archaeological MinIO for photo {photo_id}")
                        return StreamingResponse(
                            io.BytesIO(file_data),
                            media_type=photo.mime_type or "image/jpeg",
                            headers={"Cache-Control": "public, max-age=3600"}
                        )
                    else:
                        logger.warning(
                            f"Archaeological MinIO returned invalid data for file {clean_path}: {type(file_data)}")
                        raise HTTPException(status_code=404, detail="File data non valido")

                except HTTPException:
                    # Rilancia HTTPException per gestione corretta
                    raise
                except Exception as e:
                    logger.error(f"Error serving file from Archaeological MinIO: {e}")
                    raise HTTPException(status_code=400, detail=f"File non trovato: {photo.file_path}")

            # Se file è su filesystem locale
            elif photo.file_path.startswith("storage/") or photo.file_path.startswith("app/static/"):
                file_path = Path(photo.file_path)
                logger.info(f"Checking local file path: {file_path}")

                if file_path.exists():
                    logger.info(f"Serving local file for photo {photo_id}")
                    return FileResponse(
                        file_path,
                        media_type=photo.mime_type or "image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                else:
                    logger.warning(f"Local file not found: {file_path}")

        # Se tutto fallisce, restituisci 404
        raise HTTPException(status_code=404, detail="Immagine non disponibile")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving full image: {e}")
        raise HTTPException(status_code=500, detail="Errore nel servire immagine")


@photos_router.get("/{photo_id}/download")
async def download_photo(
        photo_id: UUID,
        db: AsyncSession = Depends(get_async_session)
):
    """Scarica file originale foto"""
    try:
        # Recupera info foto dal database
        photo_query = select(Photo).where(Photo.id == photo_id)
        photo = await db.execute(photo_query)
        photo = photo.scalar_one_or_none()

        if not photo:
            raise HTTPException(status_code=404, detail="Foto non trovata")

        # Determina path file
        if photo.file_path:
            logger.info(f"Photo {photo_id} download request for file_path: {photo.file_path}")

            # Se file è su MinIO
            if photo.file_path.startswith("sites/") or not photo.file_path.startswith("storage/"):
                try:
                    # 🔧 CORREZIONE: Pulisci path prima di usarlo
                    clean_path = clean_minio_path(photo.file_path)
                    logger.info(f"Attempting to download from Archaeological MinIO: {clean_path}")

                    file_data = await archaeological_minio_service.get_file(clean_path)

                    if file_data and isinstance(file_data, bytes):
                        # Determina filename per il download
                        filename = photo.original_filename or photo.filename or f"photo_{photo_id}.jpg"
                        logger.info(
                            f"Successfully downloading file from Archaeological MinIO for photo {photo_id}, filename: {filename}")

                        return StreamingResponse(
                            io.BytesIO(file_data),
                            media_type=photo.mime_type or "image/jpeg",
                            headers={
                                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                                "Cache-Control": "private, max-age=0"
                            }
                        )
                    else:
                        logger.warning(
                            f"Archaeological MinIO returned invalid data for download {clean_path}: {type(file_data)}")
                        raise HTTPException(status_code=404, detail="File data non valido")

                except HTTPException:
                    # Rilancia HTTPException per gestione corretta
                    raise
                except Exception as e:
                    logger.error(f"Error downloading file from Archaeological MinIO: {e}")
                    raise HTTPException(status_code=500, detail=f"Errore nel download: {str(e)}")

            # Se file è su filesystem locale
            elif photo.file_path.startswith("storage/") or photo.file_path.startswith("app/static/uploads/"):
                file_path = Path(photo.file_path)
                logger.info(f"Checking local file path for download: {file_path}")

                if file_path.exists():
                    logger.info(f"Serving local file for download: {photo_id}")
                    # Determina filename per il download
                    filename = photo.filename or f"photo_{photo_id}.jpg"

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

        # Se tutto fallisce, restituisci 404
        raise HTTPException(status_code=404, detail="File non disponibile per il download")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading photo: {e}")
        raise HTTPException(status_code=500, detail="Errore nel download del file")
