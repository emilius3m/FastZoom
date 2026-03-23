"""
API v1 - Document Management
Endpoints per gestione documenti archeologici.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from uuid import UUID, uuid4
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from loguru import logger
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import json

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)

# Import services for direct implementation
from app.services.archaeological_minio_service import archaeological_minio_service
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import UserActivity
from app.models.documents import Document

# Import error handling
from app.routes.api.service_dependencies import convert_storage_error_to_http_exception

# Schemas
class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    doc_type: Optional[str] = None
    tags: Optional[str] = None
    doc_date: Optional[str] = None
    author: Optional[str] = None
    is_public: Optional[bool] = None
    version_notes: Optional[str] = None

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["site_id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise SiteNotFoundError(str(site_id))
    
    return site_info

# NUOVI ENDPOINTS V1

@router.get("/sites/{site_id}/documents", summary="Lista documenti sito", tags=["Documents"])
async def v1_get_site_documents(
    site_id: UUID,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera tutti i documenti del sito con filtri opzionali.
    
    Supporta ricerca per categoria, testo e paginazione.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Direct implementation with filters
    try:
        # Base query
        query = select(Document).where(
            and_(
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        )

        # Apply filters
        if category:
            query = query.where(Document.category == category)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Document.title.ilike(search_term),
                    Document.description.ilike(search_term),
                    Document.author.ilike(search_term),
                    Document.tags.ilike(search_term)
                )
            )

        query = query.order_by(Document.uploaded_at.desc())
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        documents = result.scalars().all()

        # Format results
        documents_list = []
        for doc in documents:
            documents_list.append({
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
                "version": doc.version
            })

        return JSONResponse({
            "documents": documents_list,
            "total": len(documents_list),
            "site_info": site_info
        })

    except Exception as e:
        logger.error(f"Error fetching documents: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero documenti: {str(e)}")

@router.post("/sites/{site_id}/documents", summary="Upload documento", tags=["Documents"])
async def v1_upload_document(
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
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Upload nuovo documento al sito archeologico.
    
    Supporta formati PDF, DOC, DOCX, immagini e altro.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di upload
    if site_info.get("permission_level") not in ["admin", "editor", "regional_admin"]:
        raise InsufficientPermissionsError("Upload documenti richiede permessi editor, admin o regional admin")
    
    # Simula request form data
    class MockRequest:
        def __init__(self, form_data: dict, uploaded_file: UploadFile):
            self._form_data = form_data
            self._file = uploaded_file
        
        async def form(self):
            return self._form_data
        
        def files(self):
            return {"file": self._file}
    
    form_data = {
        "title": title,
        "description": description,
        "category": category,
        "doc_type": doc_type,
        "tags": tags,
        "doc_date": doc_date,
        "author": author,
        "is_public": is_public
    }
    
    # Direct implementation instead of backward compatibility
    try:
        # Validate file
        file_size = await archaeological_minio_service._get_file_size(file)
        if file_size > 52428800:  # 50MB
            raise HTTPException(status_code=400, detail="File troppo grande (max 50MB)")

        # Read file content
        content = await file.read()
        
        # Determine content type and extension
        file_extension = Path(file.filename).suffix
        content_type = file.content_type or 'application/octet-stream'
        
        # Generate unique document ID
        temp_document_id = str(uuid4())
        
        logger.info(f"Uploading document: {file.filename}, size: {len(content)}, type: {content_type}")
        
        # Prepare metadata for MinIO
        document_metadata = {
            'title': title,
            'description': description or '',
            'category': category,
            'doc_type': doc_type or content_type,
            'filename': file.filename,
            'tags': tags or '',
            'author': author or '',
            'doc_date': doc_date or '',
            'uploaded_by': str(current_user_id)
        }
        
        # Upload to MinIO
        object_name = f"{site_id}/{temp_document_id}{file_extension}"
        logger.info(f"MinIO object_name: {object_name}")
        
        minio_path = await archaeological_minio_service._upload_with_retry(
            bucket_name=archaeological_minio_service.buckets['documents'],
            object_name=object_name,
            data=content,
            content_type=content_type,
            metadata=archaeological_minio_service._merge_metadata(
                archaeological_minio_service._create_base_metadata(str(site_id), content_type),
                document_metadata
            ),
            operation_name="document upload",
            target_freed_mb=200
        )

        # Create database record
        new_document = Document(
            site_id=str(site_id),
            title=title,
            description=description,
            category=category,
            doc_type=doc_type or content_type,
            filename=file.filename,
            filepath=minio_path,
            filesize=len(content),
            mimetype=content_type,
            tags=tags,
            doc_date=datetime.fromisoformat(doc_date) if doc_date else None,
            author=author,
            is_public=is_public,
            uploaded_by=str(current_user_id),
            created_by=str(current_user_id)
        )

        db.add(new_document)
        await db.commit()
        await db.refresh(new_document)

        # Log activity
        await log_document_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="UPLOAD",
            activity_desc=f"Caricato documento: {title}",
            extra_data={
                "document_id": str(new_document.id),
                "filename": file.filename,
                "category": category,
                "minio_path": minio_path
            }
        )

        logger.info(f"Document uploaded to MinIO: {minio_path}")

        return JSONResponse({
            "message": "Documento caricato con successo",
            "document_id": str(new_document.id),
            "document": {
                "id": str(new_document.id),
                "title": new_document.title,
                "filename": new_document.filename,
                "file_path": new_document.filepath,
                "uploaded_at": new_document.uploaded_at.isoformat()
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error uploading document: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Errore nel caricamento: {str(e)}")

@router.get("/sites/{site_id}/documents/{document_id}", summary="Dettagli documento", tags=["Documents"])
async def v1_get_document(
    site_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera dettagli completi di un documento specifico.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Direct implementation instead of backward compatibility
    try:
        # Get document
        query = select(Document).where(
            and_(
                Document.id == str(document_id),
                Document.site_id == str(site_id),
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
            "file_size": doc.filesize,
            "mime_type": doc.mimetype,
            "tags": doc.tags.split(",") if doc.tags else [],
            "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
            "author": doc.author,
            "is_public": doc.is_public,
            "uploaded_at": doc.uploaded_at.isoformat(),
            "uploaded_by": str(doc.uploaded_by),
            "version": doc.version,
            "site_info": site_info
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero documento: {str(e)}")


@router.get("/sites/{site_id}/documents/{document_id}/preview", summary="Anteprima documento", tags=["Documents"])
async def v1_preview_document(
    site_id: UUID,
    document_id: UUID,
    inline: bool = Query(True, description="Se true restituisce Content-Disposition inline"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Restituisce il file documento per anteprima browser.
    Usa Content-Disposition inline per i mime supportati dal browser.
    """
    verify_site_access(site_id, user_sites)

    try:
        query = select(Document).where(
            and_(
                Document.id == str(document_id),
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        file_data = await archaeological_minio_service.get_file(doc.filepath)
        if not file_data:
            raise ResourceNotFoundError("File storage", doc.filepath)

        disposition_mode = "inline" if inline else "attachment"
        media_type = doc.mimetype or "application/octet-stream"

        response = StreamingResponse(
            iter([file_data]),
            media_type=media_type,
            headers={
                "Content-Disposition": f"{disposition_mode}; filename={doc.filename}",
                # Override CSP/X-Frame-Options to allow iframe embedding from same origin
                "X-Frame-Options": "SAMEORIGIN",
                "Content-Security-Policy": "frame-ancestors 'self';",
            }
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'anteprima: {str(e)}")

@router.put("/sites/{site_id}/documents/{document_id}", summary="Aggiorna documento", tags=["Documents"])
async def v1_update_document(
    site_id: UUID,
    document_id: UUID,
    document_data: DocumentUpdate,
    file: Optional[UploadFile] = File(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Aggiorna documento esistente con metadati e/o file.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di modifica
    if site_info.get("permission_level") not in ["admin", "editor", "regional_admin"]:
        raise InsufficientPermissionsError("Modifica documenti richiede permessi editor, admin o regional admin")
    
    # Simula request form data
    class MockRequest:
        def __init__(self, form_data: dict, uploaded_file: Optional[UploadFile]):
            self._form_data = form_data
            self._file = uploaded_file
        
        async def form(self):
            return self._form_data
        
        def files(self):
            return {"file": self._file} if self._file else {}
    
    form_data = document_data.model_dump(exclude_unset=True)
    mock_request = MockRequest(form_data, file)
    
    # Direct implementation instead of backward compatibility
    try:
        # Get document
        query = select(Document).where(
            and_(
                Document.id == str(document_id),
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        # Update document fields
        update_data = document_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(doc, field):
                setattr(doc, field, value)

        # Handle file update if provided
        if file:
            # Validate file
            file_size = await archaeological_minio_service._get_file_size(file)
            if file_size > 52428800:  # 50MB
                raise DomainValidationError("File troppo grande (max 50MB)")

            # Read file content
            content = await file.read()
            
            # Determine content type and extension
            file_extension = Path(file.filename).suffix
            content_type = file.content_type or 'application/octet-stream'
            
            # Generate unique document ID
            temp_document_id = str(uuid4())
            
            # Upload to MinIO
            object_name = f"{site_id}/{temp_document_id}{file_extension}"
            
            minio_path = await archaeological_minio_service._upload_with_retry(
                bucket_name=archaeological_minio_service.buckets['documents'],
                object_name=object_name,
                data=content,
                content_type=content_type,
                metadata=archaeological_minio_service._merge_metadata(
                    archaeological_minio_service._create_base_metadata(str(site_id), content_type),
                    {
                        'title': doc.title,
                        'description': doc.description,
                        'category': doc.category,
                        'doc_type': doc.doc_type,
                        'filename': file.filename,
                        'tags': doc.tags,
                        'author': doc.author,
                        'uploaded_by': str(current_user_id)
                    }
                ),
                operation_name="document update",
                target_freed_mb=200
            )

            # Update document file info
            doc.filename = file.filename
            doc.filepath = minio_path
            doc.filesize = len(content)
            doc.mimetype = content_type

        await db.commit()
        await db.refresh(doc)

        # Log activity
        await log_document_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="UPDATE",
            activity_desc=f"Aggiornato documento: {doc.title}",
            extra_data={"document_id": str(document_id)}
        )

        return JSONResponse({
            "message": "Documento aggiornato con successo",
            "document_id": str(doc.id),
            "document": {
                "id": str(doc.id),
                "title": doc.title,
                "filename": doc.filename,
                "updated_at": doc.uploaded_at.isoformat()
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'aggiornamento: {str(e)}")

@router.delete("/sites/{site_id}/documents/{document_id}", summary="Elimina documento", tags=["Documents"])
async def v1_delete_document(
    site_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Elimina documento (soft delete).
    
    Il documento viene marcato come eliminato ma non rimosso fisicamente.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di eliminazione
    if site_info.get("permission_level") not in ["admin", "regional_admin"]:
        raise InsufficientPermissionsError("Eliminazione documenti richiede permessi admin o regional admin")
    
    # Direct implementation
    try:
        # Verify site access
        site_info = verify_site_access(site_id, user_sites)
        
        # Get document
        query = select(Document).where(
            and_(
                Document.id == str(document_id),
                Document.site_id == str(site_id),
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

        # Log activity
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

# Funzione helper per logging attività documento
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
            user_id=str(user_id),
            site_id=str(site_id),
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

@router.get("/sites/{site_id}/documents/{document_id}/download", summary="Download documento", tags=["Documents"])
async def v1_download_document(
    site_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Download file originale del documento.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Direct implementation
    try:
        # Verify site access
        site_info = verify_site_access(site_id, user_sites)
        
        # Get document
        query = select(Document).where(
            and_(
                Document.id == str(document_id),
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Documento non trovato")

        # Download file from MinIO with proper error handling
        try:
            logger.info(f"Attempting to download document: {doc.filepath}")
            file_data = await archaeological_minio_service.get_file(doc.filepath)
            
            if not file_data:
                logger.error(f"File data is empty for document: {doc.filepath}")
                raise ResourceNotFoundError("File storage", doc.filepath)

            return StreamingResponse(
                iter([file_data]),
                media_type=doc.mimetype or "application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename={doc.filename}"
                }
            )
        except HTTPException:
            # Re-raise HTTP exceptions (like 404)
            raise
        except Exception as e:
            # Convert domain storage exceptions to HTTP exceptions
            await convert_storage_error_to_http_exception(e, "document download")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel download: {str(e)}")

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/documents/{site_id}", summary="[DEPRECATED] Documenti sito legacy", tags=["Documents - Legacy"])
async def legacy_get_site_documents(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    ⚠️ DEPRECATED: Lista documenti sito endpoint legacy.
    
    Usa /api/v1/documents/sites/{site_id}/documents invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning(f"Legacy documents endpoint used for site {site_id} - deprecated")
    # Direct implementation for legacy endpoint
    try:
        # Base query
        query = select(Document).where(
            and_(
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        )

        query = query.order_by(Document.uploaded_at.desc())
        
        result = await db.execute(query)
        documents = result.scalars().all()

        # Format results
        documents_list = []
        for doc in documents:
            documents_list.append({
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
                "version": doc.version
            })

        response = JSONResponse({
            "documents": documents_list,
            "total": len(documents_list)
        })
        
        add_deprecation_headers(response, f"/api/v1/sites/{site_id}/documents")
        return response

    except Exception as e:
        logger.error(f"Error fetching documents: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero documenti: {str(e)}")

# NUOVI ENDPOINTS V1 - Funzionalità aggiuntive dalla vecchia implementazione

@router.get("/sites/{site_id}/documents/count", summary="Conteggio documenti sito", tags=["Documents"])
async def v1_get_documents_count(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Get documents count for a specific site.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Conteggio documenti per il sito
        from app.models import Document
        documents_count = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.site_id == str(site_id),
                    Document.is_deleted == False
                )
            )
        )
        count = documents_count.scalar() or 0
        
        return JSONResponse({
            "count": count,
            "site_id": str(site_id)
        })
        
    except Exception as e:
        logger.error(f"Error getting documents count for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel conteggio documenti: {str(e)}")

@router.get("/unified/documents/count", summary="Conteggio documenti", tags=["Documents"])
async def v1_get_unified_documents_count(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Get total documents count for the current user across all accessible sites.
    """
    try:
        # Get all sites user has access to
        accessible_site_ids = [site["site_id"] for site in user_sites]
        
        if not accessible_site_ids:
            return JSONResponse({"count": 0})
        
        # Count documents across all accessible sites
        from app.models import Document
        documents_count = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.site_id.in_(accessible_site_ids),
                    Document.is_deleted == False
                )
            )
        )
        count = documents_count.scalar() or 0
        
        return JSONResponse({"count": count})
        
    except Exception as e:
        logger.error(f"Error getting unified documents count: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel conteggio documenti: {str(e)}")

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API documenti", tags=["Documents - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per i documenti.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/site/{site_id}/documents": "/api/v1/documents/sites/{site_id}/documents",
                "/api/site/{site_id}/documents/{document_id}": "/api/v1/documents/sites/{site_id}/documents/{document_id}",
                "/api/site/{site_id}/documents/{document_id}/download": "/api/v1/documents/sites/{site_id}/documents/{document_id}/download"
            },
            "new_endpoints": {
                "/api/v1/sites/{site_id}/documents/count": "Conteggio documenti sito",
                "/api/v1/unified/documents/count": "Conteggio documenti unificato"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Separazione endpoints documenti da altri domini",
                "Miglioramento filtri e ricerca",
                "Headers di deprecazione automatici",
                "Documentazione migliorata",
                "Aggiunta endpoint di conteggio documenti"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints documenti"
        }
    }
