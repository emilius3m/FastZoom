"""
Document Management API Router - Gestione documenti archeologici
File: app/routes/api/documents.py
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional
from uuid import UUID
from datetime import datetime
import os
import json
from pathlib import Path

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist
from app.models.documents import Document
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.users import UserActivity
from app.routes.sites_router import get_site_access
from app.core.config import get_settings

settings = get_settings()

documents_router = APIRouter(prefix="/api", tags=["documents"])


@documents_router.post("/site/{site_id}/documents")
async def upload_document(
        site_id: UUID,
        file: UploadFile = File(...),
        title: str = Form(...),
        description: Optional[str] = Form(None),
        category: str = Form(...),
        doc_type: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        doc_date: Optional[str] = Form(None),
        author: Optional[str] = Form(None),
        is_public: bool = Form(True),
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Upload nuovo documento"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Validazione file
        if file.size > 52428800:  # 50MB
            raise HTTPException(status_code=400, detail="File troppo grande (max 50MB)")

        # Genera path sicuro per il file
        upload_dir = Path(settings.upload_dir) / "documents" / str(site_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Nome file univoco
        file_extension = Path(file.filename).suffix
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"
        file_path = upload_dir / safe_filename

        # Salva file su disco
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Crea record nel database
        new_document = Document(
            site_id=site_id,
            title=title,
            description=description,
            category=category,
            doc_type=doc_type or file.content_type,
            filename=file.filename,
            file_path=str(file_path),
            file_size=file.size,
            mime_type=file.content_type,
            tags=tags,
            doc_date=datetime.fromisoformat(doc_date) if doc_date else None,
            author=author,
            is_public=is_public,
            uploaded_by=current_user_id
        )

        db.add(new_document)
        await db.commit()
        await db.refresh(new_document)

        # Log attività
        await log_document_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="UPLOAD",
            activity_desc=f"Caricato documento: {title}",
            extra_data={
                "document_id": str(new_document.id),
                "filename": file.filename,
                "category": category
            }
        )

        return JSONResponse({
            "message": "Documento caricato con successo",
            "document_id": str(new_document.id),
            "document": {
                "id": str(new_document.id),
                "title": new_document.title,
                "filename": new_document.filename,
                "uploaded_at": new_document.uploaded_at.isoformat()
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        # Cleanup file if exists
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Errore nel caricamento: {str(e)}")


@documents_router.get("/site/{site_id}/documents")
async def get_documents(
        site_id: UUID,
        category: Optional[str] = None,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Recupera tutti i documenti del sito"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        # Query base
        query = select(Document).where(
            and_(
                Document.site_id == site_id,
                Document.is_deleted == False
            )
        )

        # Filtra per categoria se specificata
        if category:
            query = query.where(Document.category == category)

        query = query.order_by(Document.uploaded_at.desc())

        result = await db.execute(query)
        documents = result.scalars().all()

        # Formatta risultati
        documents_list = []
        for doc in documents:
            documents_list.append({
                "id": str(doc.id),
                "title": doc.title,
                "description": doc.description,
                "category": doc.category,
                "doc_type": doc.doc_type,
                "filename": doc.filename,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "tags": doc.tags,
                "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
                "author": doc.author,
                "is_public": doc.is_public,
                "uploaded_at": doc.uploaded_at.isoformat(),
                "uploaded_by": str(doc.uploaded_by),
                "version": doc.version
            })

        return JSONResponse({
            "documents": documents_list,
            "total": len(documents_list)
        })

    except Exception as e:
        logger.error(f"Error fetching documents: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero documenti: {str(e)}")


@documents_router.get("/site/{site_id}/documents/{document_id}")
async def get_document(
        site_id: UUID,
        document_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Recupera singolo documento"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.site_id == site_id,
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        return JSONResponse({
            "id": str(doc.id),
            "title": doc.title,
            "description": doc.description,
            "category": doc.category,
            "doc_type": doc.doc_type,
            "filename": doc.filename,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "tags": doc.tags,
            "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
            "author": doc.author,
            "is_public": doc.is_public,
            "uploaded_at": doc.uploaded_at.isoformat(),
            "uploaded_by": str(doc.uploaded_by),
            "version": doc.version
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero: {str(e)}")


@documents_router.put("/site/{site_id}/documents/{document_id}")
async def update_document(
        site_id: UUID,
        document_id: UUID,
        title: str = Form(...),
        description: Optional[str] = Form(None),
        category: str = Form(...),
        doc_type: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        doc_date: Optional[str] = Form(None),
        author: Optional[str] = Form(None),
        is_public: bool = Form(True),
        file: Optional[UploadFile] = File(None),
        version_notes: Optional[str] = Form(None),
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna documento esistente"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Recupera documento
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.site_id == site_id,
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        # Aggiorna metadati
        doc.title = title
        doc.description = description
        doc.category = category
        doc.doc_type = doc_type or doc.doc_type
        doc.tags = tags
        doc.doc_date = datetime.fromisoformat(doc_date) if doc_date else None
        doc.author = author
        doc.is_public = is_public
        doc.updated_at = datetime.utcnow()

        # Se c'è un nuovo file, sostituisci
        if file:
            # Elimina vecchio file
            old_path = Path(doc.file_path)
            if old_path.exists():
                old_path.unlink()

            # Salva nuovo file
            upload_dir = Path(settings.upload_dir) / "documents" / str(site_id)
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_extension = Path(file.filename).suffix
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{file.filename}"
            file_path = upload_dir / safe_filename

            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            doc.filename = file.filename
            doc.file_path = str(file_path)
            doc.file_size = file.size
            doc.mime_type = file.content_type
            doc.version += 1
            doc.version_notes = version_notes

        await db.commit()
        await db.refresh(doc)

        # Log attività
        await log_document_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="UPDATE",
            activity_desc=f"Aggiornato documento: {title}",
            extra_data={
                "document_id": str(doc.id),
                "new_version": doc.version if file else None
            }
        )

        return JSONResponse({
            "message": "Documento aggiornato con successo",
            "document_id": str(doc.id)
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'aggiornamento: {str(e)}")


@documents_router.delete("/site/{site_id}/documents/{document_id}")
async def delete_document(
        site_id: UUID,
        document_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Elimina documento (soft delete)"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.site_id == site_id,
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        doc_title = doc.title

        # Soft delete
        doc.is_deleted = True
        doc.deleted_at = datetime.utcnow()
        doc.deleted_by = current_user_id

        await db.commit()

        # Log attività
        await log_document_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="DELETE",
            activity_desc=f"Eliminato documento: {doc_title}",
            extra_data={"document_id": str(document_id)}
        )

        return JSONResponse({
            "message": "Documento eliminato con successo",
            "document_id": str(document_id)
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'eliminazione: {str(e)}")


@documents_router.get("/site/{site_id}/documents/{document_id}/download")
async def download_document(
        site_id: UUID,
        document_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Download documento"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.site_id == site_id,
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File non trovato su disco")

        def file_iterator():
            with open(file_path, "rb") as f:
                yield from f

        return StreamingResponse(
            file_iterator(),
            media_type=doc.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={doc.filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel download: {str(e)}")


async def log_document_activity(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        activity_type: str,
        activity_desc: str,
        extra_data: dict = None
):
    """Log attività documento"""
    try:
        activity = UserActivity(
            user_id=user_id,
            site_id=site_id,
            activity_type=activity_type,
            activity_desc=activity_desc,
            extra_data=json.dumps(extra_data) if extra_data else None
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Document activity logged: {activity_type} by {user_id}")

    except Exception as e:
        logger.error(f"Error logging document activity: {e}")
        await db.rollback()
