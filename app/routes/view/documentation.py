# app/routes/view/documentation.py - Documentation view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any
from loguru import logger

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


def _map_us_file_category(file_type: str) -> str:
    """Mappa tipi file US/USM a categorie documenti"""
    mapping = {
        'pianta': 'planimetrie',
        'sezione': 'planimetrie',
        'prospetto': 'planimetrie',
        'fotografia': 'documentazione',
        'documento': 'relazioni'
    }
    return mapping.get(file_type, 'altro')


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

    # Recupera documenti del sito (inclusi US/USM)
    try:
        # 1. Documenti standard dalla tabella Document
        documents_query = select(Document).where(
            and_(
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        ).order_by(Document.uploaded_at.desc())
        
        documents_result = await db.execute(documents_query)
        documents_list = documents_result.scalars().all()
        
        # Formatta documenti standard per il template
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
                "created_at": doc.uploaded_at.isoformat(),
                "source": "document"  # Identifica provenienza
            })
        
        # 2. Aggiungi file US/USM come documenti
        from app.models.stratigraphy import USFile, UnitaStratigrafica, UnitaStratigraficaMuraria
        from app.models.stratigraphy import us_files_association, usm_files_association
        
        # Query per file US associati
        us_files_query = select(USFile).join(
            us_files_association, USFile.id == us_files_association.c.file_id
        ).join(
            UnitaStratigrafica, us_files_association.c.us_id == UnitaStratigrafica.id
        ).where(
            and_(
                UnitaStratigrafica.site_id == str(site_id),
                UnitaStratigrafica.is_deleted == False
            )
        ).distinct()
        
        us_files_result = await db.execute(us_files_query)
        us_files = us_files_result.scalars().all()
        
        # Aggiungi file US come documenti
        for us_file in us_files:
            # Trova le US associate
            us_assoc_query = select(us_files_association).where(
                us_files_association.c.file_id == us_file.id
            )
            us_assoc_result = await db.execute(us_assoc_query)
            us_associations = us_assoc_result.all()
            
            for assoc in us_associations:
                # Trova dettagli US
                us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == assoc.us_id)
                us_result = await db.execute(us_query)
                us = us_result.scalar_one_or_none()
                
                if us:
                    documents.append({
                        "id": f"us_{us_file.id}",  # Prefisso per distinguere
                        "title": us_file.title or f"File US {us.us_code}",
                        "description": us_file.description or f"File associato a US {us.us_code}",
                        "category": _map_us_file_category(assoc.file_type),
                        "doc_type": us_file.mimetype,
                        "filename": us_file.original_filename,
                        "file_size": us_file.filesize,
                        "mime_type": us_file.mimetype,
                        "tags": [f"US {us.us_code}", assoc.file_type],
                        "doc_date": us_file.photo_date.isoformat() if us_file.photo_date else None,
                        "author": us_file.photographer,
                        "is_public": us_file.is_published,
                        "uploaded_at": us_file.created_at.isoformat(),
                        "uploaded_by": str(us_file.uploaded_by),
                        "version": 1,
                        "created_at": us_file.created_at.isoformat(),
                        "source": "us_file",  # Identifica provenienza
                        "us_reference": us.us_code,
                        "us_id": str(us.id),
                        "file_type": assoc.file_type,
                        "download_url": f"/api/us-files/{us_file.id}/download",
                        "view_url": f"/api/us-files/{us_file.id}/view"
                    })
        
        # 3. Aggiungi file USM associati
        usm_files_query = select(USFile).join(
            usm_files_association, USFile.id == usm_files_association.c.file_id
        ).join(
            UnitaStratigraficaMuraria, usm_files_association.c.usm_id == UnitaStratigraficaMuraria.id
        ).where(
            and_(
                UnitaStratigraficaMuraria.site_id == str(site_id),
                UnitaStratigraficaMuraria.is_deleted == False
            )
        ).distinct()
        
        usm_files_result = await db.execute(usm_files_query)
        usm_files = usm_files_result.scalars().all()
        
        # Aggiungi file USM come documenti
        for usm_file in usm_files:
            # Trova le USM associate
            usm_assoc_query = select(usm_files_association).where(
                usm_files_association.c.file_id == usm_file.id
            )
            usm_assoc_result = await db.execute(usm_assoc_query)
            usm_associations = usm_assoc_result.all()
            
            for assoc in usm_associations:
                # Trova dettagli USM
                usm_query = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == assoc.usm_id)
                usm_result = await db.execute(usm_query)
                usm = usm_result.scalar_one_or_none()
                
                if usm:
                    documents.append({
                        "id": f"usm_{usm_file.id}",  # Prefisso per distinguere
                        "title": usm_file.title or f"File USM {usm.usm_code}",
                        "description": usm_file.description or f"File associato a USM {usm.usm_code}",
                        "category": _map_us_file_category(assoc.file_type),
                        "doc_type": usm_file.mimetype,
                        "filename": usm_file.original_filename,
                        "file_size": usm_file.filesize,
                        "mime_type": usm_file.mimetype,
                        "tags": [f"USM {usm.usm_code}", assoc.file_type],
                        "doc_date": usm_file.photo_date.isoformat() if usm_file.photo_date else None,
                        "author": usm_file.photographer,
                        "is_public": usm_file.is_published,
                        "uploaded_at": usm_file.created_at.isoformat(),
                        "uploaded_by": str(usm_file.uploaded_by),
                        "version": 1,
                        "created_at": usm_file.created_at.isoformat(),
                        "source": "usm_file",  # Identifica provenienza
                        "usm_reference": usm.usm_code,
                        "usm_id": str(usm.id),
                        "file_type": assoc.file_type,
                        "download_url": f"/api/us-files/{usm_file.id}/download",
                        "view_url": f"/api/us-files/{usm_file.id}/view"
                    })
        
        # Ordina tutti i documenti per data di upload (decrescente)
        documents.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        
    except Exception as e:
        logger.error(f"Errore recupero documenti unificati: {e}")
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