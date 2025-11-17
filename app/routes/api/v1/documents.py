"""
API v1 - Document Management
Endpoints per gestione documenti archeologici.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session

# Import existing document functions for backward compatibility
from app.routes.api.documents import (
    upload_document_api_site__site_id__documents_post,
    get_documents_api_site__site_id__documents_get,
    get_document_api_site__site_id__documents__document_id__get,
    update_document_api_site__site_id__documents__document_id__put,
    delete_document_api_site__site_id__documents__document_id__delete,
    download_document_api_site__site_id__documents__document_id__download_get
)

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
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )
    
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
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti i documenti del sito con filtri opzionali.
    
    Supporta ricerca per categoria, testo e paginazione.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Simula request con query params
    class MockRequest:
        def __init__(self, query_params: dict):
            self.query_params = query_params
    
    mock_request = MockRequest({
        "category": category,
        "search": search,
        "limit": limit,
        "offset": offset
    })
    
    result = await get_documents_api_site__site_id__documents_get(
        site_id, mock_request, current_user_id, user_sites, db
    )
    
    # Aggiungi informazioni sito
    if isinstance(result, dict):
        result["site_info"] = site_info
    
    return result

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
    db: AsyncSession = Depends(get_async_session)
):
    """
    Upload nuovo documento al sito archeologico.
    
    Supporta formati PDF, DOC, DOCX, immagini e altro.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di upload
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per upload documenti sul sito {site_id}"
        )
    
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
    
    mock_request = MockRequest(form_data, file)
    return await upload_document_api_site__site_id__documents_post(
        site_id, mock_request, current_user_id, user_sites, db
    )

@router.get("/sites/{site_id}/documents/{document_id}", summary="Dettagli documento", tags=["Documents"])
async def v1_get_document(
    site_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera dettagli completi di un documento specifico.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    return await get_document_api_site__site_id__documents__document_id__get(
        site_id, document_id, current_user_id, user_sites, db
    )

@router.put("/sites/{site_id}/documents/{document_id}", summary="Aggiorna documento", tags=["Documents"])
async def v1_update_document(
    site_id: UUID,
    document_id: UUID,
    document_data: DocumentUpdate,
    file: Optional[UploadFile] = File(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna documento esistente con metadati e/o file.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di modifica
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per modificare documenti sul sito {site_id}"
        )
    
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
    
    return await update_document_api_site__site_id__documents__document_id__put(
        site_id, document_id, mock_request, current_user_id, user_sites, db
    )

@router.delete("/sites/{site_id}/documents/{document_id}", summary="Elimina documento", tags=["Documents"])
async def v1_delete_document(
    site_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Elimina documento (soft delete).
    
    Il documento viene marcato come eliminato ma non rimosso fisicamente.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di eliminazione
    if site_info.get("permission_level") not in ["admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per eliminare documenti dal sito {site_id}"
        )
    
    return await delete_document_api_site__site_id__documents__document_id__delete(
        site_id, document_id, current_user_id, user_sites, db
    )

@router.get("/sites/{site_id}/documents/{document_id}/download", summary="Download documento", tags=["Documents"])
async def v1_download_document(
    site_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Download file originale del documento.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    return await download_document_api_site__site_id__documents__document_id__download_get(
        site_id, document_id, current_user_id, user_sites, db
    )

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/documents/{site_id}", summary="[DEPRECATED] Documenti sito legacy", tags=["Documents - Legacy"])
async def legacy_get_site_documents(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    ⚠️ DEPRECATED: Lista documenti sito endpoint legacy.
    
    Usa /api/v1/documents/sites/{site_id}/documents invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning(f"Legacy documents endpoint used for site {site_id} - deprecated")
    response = await get_documents_api_site__site_id__documents_get(
        site_id, request, current_user_id, user_sites, db
    )
    add_deprecation_headers(response, f"/api/v1/documents/sites/{site_id}/documents")
    return response

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
            "changes": [
                "Standardizzazione URL patterns",
                "Separazione endpoints documenti da altri domini",
                "Miglioramento filtri e ricerca",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints documenti"
        }
    }