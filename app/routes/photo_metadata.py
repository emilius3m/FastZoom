"""
API Endpoints per Metadati Fotografici - Versione Async
Compatibile con la tua architettura esistente
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from uuid import UUID
from loguru import logger
from datetime import datetime

# Import dalla tua architettura
from app.database.db import get_async_session
from app.models.photos import Photo
from app.models.users import User
from app.core.security import get_current_user_id_with_blacklist

# Schemas Pydantic (da creare separatamente)
from app.schema.photo_schemas import (
    PhotoMetadataUpdate,
    PhotoMetadataResponse,
    PhotoResponse,
    BulkMetadataUpdate,
    BulkMetadataResponse
)

router = APIRouter(
    prefix="/api/photos",
    tags=["Photo Metadata"],
)


@router.get("/{photo_id}/metadata", response_model=dict)
async def get_photo_metadata(
        photo_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera metadati di una foto

    GET /api/photos/{photo_id}/metadata
    """
    try:
        # Query async per recuperare foto
        result = await db.execute(
            select(Photo).where(
                Photo.id == photo_id,
                Photo.deleted_at.is_(None)
            )
        )
        photo = result.scalar_one_or_none()

        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto non trovata"
            )

        # TODO: Verifica permessi accesso al sito
        # if photo.site_id not in user_accessible_sites:
        #     raise HTTPException(status_code=403, detail="Accesso negato")

        return {
            "photo_id": str(photo.id),
            "metadata": photo.metadata or {},
            "updated_at": photo.updated_at.isoformat() if photo.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Errore recupero metadati: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore interno server"
        )


@router.put("/{photo_id}/metadata", response_model=dict)
async def update_photo_metadata(
        photo_id: UUID,
        metadata: PhotoMetadataUpdate,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna metadati di una foto

    PUT /api/photos/{photo_id}/metadata

    Body: JSON con campi metadati da aggiornare
    """
    try:
        # Recupera foto
        result = await db.execute(
            select(Photo).where(
                Photo.id == photo_id,
                Photo.deleted_at.is_(None)
            )
        )
        photo = result.scalar_one_or_none()

        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto non trovata"
            )

        # TODO: Verifica permessi modifica

        # Merge metadati esistenti con nuovi
        current_metadata = photo.metadata.copy() if photo.metadata else {}

        # Estrai solo campi non None dal payload
        update_data = metadata.dict(exclude_unset=True, exclude_none=True)
        current_metadata.update(update_data)

        # Aggiorna record
        await db.execute(
            update(Photo)
            .where(Photo.id == photo_id)
            .values(
                metadata=current_metadata,
                updated_at=datetime.utcnow()
            )
        )

        # Aggiorna campi diretti se presenti
        if metadata.visibility:
            photo.visibility = metadata.visibility
        if metadata.featured is not None:
            photo.featured = metadata.featured

        await db.commit()

        # Ricarica foto aggiornata
        await db.refresh(photo)

        logger.info(f"✅ Metadati foto {photo_id} aggiornati da user {current_user_id}")

        return {
            "success": True,
            "photo_id": str(photo.id),
            "metadata": photo.metadata,
            "updated_at": photo.updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Errore aggiornamento metadati: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore durante l'aggiornamento"
        )


@router.post("/metadata/bulk", response_model=dict)
async def bulk_update_metadata(
        bulk_update: BulkMetadataUpdate,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiornamento bulk metadati per selezione multipla

    POST /api/photos/metadata/bulk

    Body: {
        "photo_ids": ["uuid1", "uuid2", ...],
        "metadata": { ... campi da aggiornare ... }
    }
    """
    logger.info(f"📦 Bulk update per {len(bulk_update.photo_ids)} foto")

    successful = []
    errors = []

    try:
        for photo_id in bulk_update.photo_ids:
            try:
                # Recupera foto
                result = await db.execute(
                    select(Photo).where(
                        Photo.id == photo_id,
                        Photo.deleted_at.is_(None)
                    )
                )
                photo = result.scalar_one_or_none()

                if not photo:
                    errors.append({
                        'photo_id': str(photo_id),
                        'error': 'Foto non trovata'
                    })
                    continue

                # Merge metadati
                current_metadata = photo.metadata.copy() if photo.metadata else {}
                update_data = bulk_update.metadata.dict(exclude_unset=True, exclude_none=True)
                current_metadata.update(update_data)

                # Aggiorna
                await db.execute(
                    update(Photo)
                    .where(Photo.id == photo_id)
                    .values(
                        metadata=current_metadata,
                        updated_at=datetime.utcnow()
                    )
                )

                # Aggiorna campi diretti
                if bulk_update.metadata.visibility:
                    photo.visibility = bulk_update.metadata.visibility
                if bulk_update.metadata.featured is not None:
                    photo.featured = bulk_update.metadata.featured

                successful.append(photo_id)

            except Exception as e:
                logger.error(f"❌ Errore foto {photo_id}: {e}")
                errors.append({
                    'photo_id': str(photo_id),
                    'error': str(e)
                })

        await db.commit()

        logger.info(f"✅ Bulk update: {len(successful)} ok, {len(errors)} errori")

        return {
            "total_requested": len(bulk_update.photo_ids),
            "successful": len(successful),
            "failed": len(errors),
            "errors": errors,
            "updated_ids": [str(pid) for pid in successful]
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Errore bulk update: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore durante bulk update"
        )


@router.delete("/{photo_id}/metadata", status_code=status.HTTP_204_NO_CONTENT)
async def clear_photo_metadata(
        photo_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Cancella tutti i metadati archeologici (mantiene EXIF)

    DELETE /api/photos/{photo_id}/metadata
    """
    try:
        result = await db.execute(
            select(Photo).where(
                Photo.id == photo_id,
                Photo.deleted_at.is_(None)
            )
        )
        photo = result.scalar_one_or_none()

        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto non trovata"
            )

        # Cancella metadati archeologici (mantiene EXIF)
        await db.execute(
            update(Photo)
            .where(Photo.id == photo_id)
            .values(
                metadata={},
                updated_at=datetime.utcnow()
            )
        )

        await db.commit()

        logger.info(f"🗑️  Metadati foto {photo_id} cancellati")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Errore cancellazione metadati: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore durante cancellazione"
        )
