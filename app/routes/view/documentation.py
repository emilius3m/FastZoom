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

documentation_router = APIRouter(prefix="/view", tags=["documentation"])

async def get_current_user_with_context(current_user_id: UUID, db: AsyncSession):
    """Recupera informazioni utente corrente"""
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    return user.scalar_one_or_none()


async def get_form_schemas_safe(db: AsyncSession, site_id: UUID) -> List[Dict[str, Any]]:
    """Recupera form schemas con gestione errori centralizzata"""
    try:
        import json

        form_schemas_query = select(FormSchema).where(
            and_(FormSchema.site_id == site_id, FormSchema.is_active == True)
        ).order_by(FormSchema.created_at.desc())

        form_schemas = await db.execute(form_schemas_query)
        form_schemas = form_schemas.scalars().all()

        schemas_list = []
        for schema in form_schemas:
            try:
                schema_json = json.loads(schema.schema_json)
                schemas_list.append({
                    "id": str(schema.id),
                    "name": schema.name,
                    "description": schema.description,
                    "category": schema.category,
                    "created_at": schema.created_at.isoformat(),
                    "updated_at": schema.updated_at.isoformat(),
                    "schemas": schema_json
                })
            except json.JSONDecodeError:
                continue

        return schemas_list

    except Exception:
        return []


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
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == current_user_id,
            UserSitePermission.site_id == site_id,
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

    current_user = await get_current_user_with_context(current_user_id, db)

    # Recupera documenti del sito
    try:
        documents_query = select(Document).where(
            and_(
                Document.site_id == site_id,
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
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "current_page": "documentation",
        "documents": documents,
        "form_schemas": form_schemas
    }

    return templates.TemplateResponse("sites/documentation.html", context)