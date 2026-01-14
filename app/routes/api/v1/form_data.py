from fastapi import APIRouter, Depends, HTTPException, Body, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List, Dict, Any, Optional
import logging

from app.core.dependencies import get_database_session
from app.core.security import get_current_user_id
from app.models import FormData, FormSchema
from app.routes.api.dependencies import get_site_access, get_normalized_site_id
from app.core.domain_exceptions import InsufficientPermissionsError, ResourceNotFoundError

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/sites/{site_id}/forms/{schema_id}/submit")
async def submit_form_data(
    site_id: UUID,
    schema_id: UUID,
    data: Dict[str, Any] = Body(...),
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Invia dati compilati per un form specifico.
    """
    site, permission = site_access
    if not permission.can_write():
        raise InsufficientPermissionsError("Permessi di scrittura richiesti")
        
    # Verify schema exists and belongs to site
    schema = await db.execute(
        select(FormSchema).where(
            FormSchema.id == str(schema_id),
            FormSchema.site_id == str(site_id)
        )
    )
    schema = schema.scalar_one_or_none()
    
    if not schema:
        raise ResourceNotFoundError("FormSchema", str(schema_id))

    try:
        new_submission = FormData(
            site_id=str(site_id),
            schema_id=str(schema_id),
            data=data,
            submitted_by=str(current_user_id)
        )
        
        db.add(new_submission)
        await db.commit()
        await db.refresh(new_submission)

        logger.info(f"Form data submitted: {new_submission.id} for schema {schema_id}")
        
        return {
            "id": new_submission.id,
            "message": "Dati inviati con successo",
            "created_at": new_submission.created_at
        }
        
    except Exception as e:
        logger.error(f"Error submitting form data: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Errore nel salvataggio dei dati")

@router.get("/sites/{site_id}/forms/{schema_id}/data")
async def get_form_submissions(
    site_id: UUID,
    schema_id: UUID,
    site_access: tuple = Depends(get_site_access),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Ottiene tutte le compilazioni per un determinato form.
    """
    site, permission = site_access
    if not permission.can_read():
        raise InsufficientPermissionsError("Permessi di lettura richiesti")
        
    try:
        result = await db.execute(
            select(FormData).where(
                FormData.schema_id == str(schema_id),
                FormData.site_id == str(site_id)
            ).order_by(FormData.created_at.desc())
        )
        submissions = result.scalars().all()
        
        return [
            {
                "id": sub.id,
                "data": sub.data,
                "created_at": sub.created_at,
                "submitted_by": sub.submitted_by
            }
            for sub in submissions
        ]
        
    except Exception as e:
        logger.error(f"Error fetching form submissions: {e}")
        raise HTTPException(status_code=500, detail="Errore nel recupero dei dati")
