# app/routes/view/documentation.py - Documentation view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.models.form_schemas import FormSchema
from app.models.documents import Document
from app.templates import templates

# Import helper functions unificati
from app.services.view_helpers import (
    get_current_user_with_profile,
    get_form_schemas_safe,
    get_base_template_context
)

documentation_router = APIRouter(prefix="/view", tags=["documentation"])

# Le funzioni helper sono state spostate in app/services/view_helpers.py


@documentation_router.get("/{site_id}/documentation", response_class=HTMLResponse)
async def site_documentation(
        request: Request,
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione documentazione e rapporti del sito"""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == str(current_user_id),
            UserSitePermission.site_id == str(site_id),
            UserSitePermission.is_active == True
        )
    )
    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    current_user = await get_current_user_with_profile(current_user_id, db)

    # Recupera documenti del sito
    try:
        documents_query = select(Document).where(
            and_(
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        ).order_by(Document.uploaded_at.desc())
        
        documents_result = await db.execute(documents_query)
        documents_list = documents_result.scalars().all()
        
        # Formatta documenti per il template
        documents = []
        for doc in documents_list:
            documents.append({
                "id": str(doc.id),
                "title": doc.title,
                "description": doc.description,
                "category": doc.category,
                "doc_type": doc.doc_type,
                "filename": doc.filename,
                "file_size": doc.filesize,
                "mime_type": doc.mimetype,
                "tags": doc.tags.split(",") if doc.tags else [],
                "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
                "author": doc.author,
                "is_public": doc.is_public,
                "uploaded_at": doc.uploaded_at.isoformat(),
                "uploaded_by": str(doc.uploaded_by),
                "version": doc.version,
                "created_at": doc.uploaded_at.isoformat()
            })
    except Exception as e:
        documents = []

    # Form schemas del sito con gestione errori centralizzata
    form_schemas = await get_form_schemas_safe(db, site_id)

    # Prepara context per il template
    context = await get_base_template_context(
        request, current_user_id, user_sites, db, site, permission, "documentation"
    )
    context.update({
        "documents": documents,
        "form_schemas": form_schemas
    })

    return templates.TemplateResponse("sites/documentation.html", context)