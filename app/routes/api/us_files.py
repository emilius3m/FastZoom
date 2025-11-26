# app/routes/api/us_files.py
"""
API Endpoints per gestione file US/USM
Integrazione con sistema upload FastZoom esistente
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, status
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

def normalize_uuid_string(uuid_str: str) -> str:
    """
    Normalize UUID string from 32-char hex to full UUID format with hyphens
    Example: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
    """
    if '-' not in uuid_str and len(uuid_str) == 32:
        return f"{uuid_str[0:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:32]}"
    return uuid_str

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.services.us_file_service import USFileService
from app.services.photo_serving_service import photo_serving_service
from app.models.stratigraphy import USFile

router = APIRouter(prefix="/api/us-files", tags=["us-files"])

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica accesso utente al sito"""
    return any(s["site_id"] == str(site_id) for s in user_sites)

# ===== UPLOAD FILE US =====

@router.post("/us/{us_id}/upload/{file_type}")
async def upload_us_file(
    us_id: str,
    file_type: str,  # 'pianta', 'sezione', 'prospetto', 'fotografia', 'documento'
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tavola_number: Optional[str] = Form(None),
    scale_ratio: Optional[str] = Form(None),
    photographer: Optional[str] = Form(None),
    photo_date: Optional[str] = Form(None),
    ordine: int = Form(0),
    is_published: bool = Form(False),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Upload file per US con metadati"""
    
    # Normalize UUID if needed
    normalized_us_id = normalize_uuid_string(us_id)
    us_id_uuid = UUID(normalized_us_id)
    
    try:
        us_file_service = USFileService(db)
        
        # Prepara metadati
        metadata = {
            'title': title or '',
            'description': description or '',
            'tavola_number': tavola_number or '',
            'scale_ratio': scale_ratio or '',
            'photographer': photographer or '',
            'ordine': ordine,
            'is_published': is_published
        }
        
        # Parse photo_date se fornita
        if photo_date:
            try:
                from datetime import datetime
                metadata['photo_date'] = datetime.fromisoformat(photo_date).date()
            except ValueError:
                logger.warning(f"Formato data non valido: {photo_date}")
        
        # Upload file
        us_file = await us_file_service.upload_us_file(
            us_id=us_id_uuid,
            file=file,
            file_type=file_type,
            user_id=current_user_id,
            metadata=metadata
        )
        
        logger.info(f"File {file_type} caricato per US {us_id_uuid}: {us_file.filename}")
        
        return {
            'message': f'File {file_type} caricato con successo',
            'file': us_file.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload file US: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel caricamento del file: {str(e)}"
        )

# ===== UPLOAD FILE USM =====

@router.post("/usm/{usm_id}/upload/{file_type}")
async def upload_usm_file(
    usm_id: str,
    file_type: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tavola_number: Optional[str] = Form(None),
    scale_ratio: Optional[str] = Form(None),
    photographer: Optional[str] = Form(None),
    photo_date: Optional[str] = Form(None),
    ordine: int = Form(0),
    is_published: bool = Form(False),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Upload file per USM"""
    
    # Normalize UUID if needed
    normalized_usm_id = normalize_uuid_string(usm_id)
    usm_id_uuid = UUID(normalized_usm_id)
    
    try:
        us_file_service = USFileService(db)
        
        metadata = {
            'title': title or '',
            'description': description or '',
            'tavola_number': tavola_number or '',
            'scale_ratio': scale_ratio or '',
            'photographer': photographer or '',
            'ordine': ordine,
            'is_published': is_published
        }
        
        if photo_date:
            try:
                from datetime import datetime
                metadata['photo_date'] = datetime.fromisoformat(photo_date).date()
            except ValueError:
                pass
        
        us_file = await us_file_service.upload_usm_file(
            usm_id=usm_id_uuid,
            file=file,
            file_type=file_type,
            user_id=current_user_id,
            metadata=metadata
        )
        
        logger.info(f"File {file_type} caricato per USM {usm_id_uuid}: {us_file.filename}")
        
        return {
            'message': f'File {file_type} caricato con successo',
            'file': us_file.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload file USM: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore caricamento: {str(e)}")

# ===== GET FILE US =====

@router.get("/us/{us_id}/files")
async def get_us_files(
    us_id: str,
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni tutti i file di una US, opzionalmente filtrati per tipo"""
    
    # Normalize UUID if needed
    normalized_us_id = normalize_uuid_string(us_id)
    us_id_uuid = UUID(normalized_us_id)
    
    try:
        us_file_service = USFileService(db)
        files = await us_file_service.get_us_files(us_id_uuid, file_type)
        
        files_data = [file.to_dict() for file in files]
        
        return {
            'us_id': str(us_id_uuid),
            'file_type': file_type,
            'files': files_data,
            'count': len(files_data)
        }
        
    except Exception as e:
        logger.error(f"Errore recupero file US {us_id_uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore recupero file: {str(e)}")

# ===== GET FILE USM =====

@router.get("/usm/{usm_id}/files")
async def get_usm_files(
    usm_id: str,
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni file USM"""
    
    # Normalize UUID if needed
    normalized_usm_id = normalize_uuid_string(usm_id)
    usm_id_uuid = UUID(normalized_usm_id)
    
    try:
        us_file_service = USFileService(db)
        files = await us_file_service.get_usm_files(usm_id_uuid, file_type)
        
        files_data = [file.to_dict() for file in files]
        
        return {
            'usm_id': str(usm_id_uuid),
            'file_type': file_type,
            'files': files_data,
            'count': len(files_data)
        }
        
    except Exception as e:
        logger.error(f"Errore recupero file USM {usm_id_uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore recupero file: {str(e)}")

# ===== GET FILES SUMMARY =====

@router.get("/us/{us_id}/files/summary")
async def get_us_files_summary(
    us_id: str,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Riassunto file US raggruppati per tipo"""
    
    # Normalize UUID if needed
    logger.info(f"DEBUG: Original us_id parameter: {us_id}")
    normalized_us_id = normalize_uuid_string(us_id)
    logger.info(f"DEBUG: Normalized us_id: {normalized_us_id}")
    us_id_uuid = UUID(normalized_us_id)
    logger.info(f"DEBUG: Final UUID object: {us_id_uuid}")
    
    try:
        us_file_service = USFileService(db)
        logger.info(f"DEBUG: Calling get_files_summary_for_us with UUID: {us_id_uuid}")
        summary = await us_file_service.get_files_summary_for_us(us_id_uuid)
        logger.info(f"DEBUG: Summary result keys: {list(summary.keys()) if summary else 'None'}")
        if summary and 'fotografie' in summary:
            logger.info(f"DEBUG: Fotografie count: {len(summary['fotografie'])}")
        
        return {
            'us_id': str(us_id_uuid),
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"Errore summary file US {us_id_uuid}: {str(e)}")
        logger.exception(f"DEBUG: Full exception traceback for US summary:")
        raise HTTPException(status_code=500, detail=f"Errore summary: {str(e)}")

@router.get("/usm/{usm_id}/files/summary")
async def get_usm_files_summary(
    usm_id: str,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Riassunto file USM raggruppati per tipo"""
    
    # Normalize UUID if needed
    normalized_usm_id = normalize_uuid_string(usm_id)
    usm_id_uuid = UUID(normalized_usm_id)
    
    try:
        us_file_service = USFileService(db)
        summary = await us_file_service.get_files_summary_for_usm(usm_id_uuid)
        
        return {
            'usm_id': str(usm_id_uuid),
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"Errore summary file USM {usm_id_uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore summary: {str(e)}")

# ===== SERVE FILE CONTENT =====

@router.get("/{file_id}/view")
async def view_us_file(
    file_id: str,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Visualizza file US/USM (stream per immagini)"""
    
    # Normalize UUID if needed
    normalized_file_id = normalize_uuid_string(file_id)
    file_id_uuid = UUID(normalized_file_id)
    
    try:
        # Get USFile record from database
        from sqlalchemy import select
        from app.models.stratigraphy import USFile
        
        us_file_query = select(USFile).where(USFile.id == file_id_uuid)
        us_file = await db.execute(us_file_query)
        us_file = us_file.scalar_one_or_none()
        
        if not us_file:
            raise HTTPException(status_code=404, detail="File US non trovato")
        
        # Verify user has access to the site
        if not verify_site_access(us_file.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Serve the file using the appropriate method based on filepath
        if us_file.filepath:
            # Use the archaeological_minio_service directly for US files
            from app.services.archaeological_minio_service import archaeological_minio_service
            import io
            
            try:
                # Construct proper MinIO path with bucket prefix
                # The filepath in DB is stored as "site_id/filename", we need to prefix with bucket
                minio_path = f"minio://{archaeological_minio_service.buckets['photos']}/{us_file.filepath}"
                
                # Get file data from MinIO
                file_data = await archaeological_minio_service.get_file(minio_path)
                
                if file_data and isinstance(file_data, bytes):
                    return StreamingResponse(
                        io.BytesIO(file_data),
                        media_type=us_file.mimetype or "image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                else:
                    logger.error(f"File found in DB but missing in MinIO: {us_file.filepath}")
                    raise HTTPException(
                        status_code=404,
                        detail=f"File exists in database but is missing from storage. File may have been deleted or upload may have failed. Path: {us_file.filepath}"
                    )
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error serving US file from MinIO: {e}")
                raise HTTPException(status_code=500, detail=f"Errore nel servire file: {str(e)}")
        
        # If no filepath, return 404
        raise HTTPException(status_code=404, detail="File non disponibile")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore serving file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore visualizzazione file: {str(e)}")

@router.get("/{file_id}/thumbnail")
async def get_us_file_thumbnail(
    file_id: str,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni thumbnail file US/USM"""
    
    # Normalize UUID if needed
    normalized_file_id = normalize_uuid_string(file_id)
    file_id_uuid = UUID(normalized_file_id)
    
    try:
        # Get USFile record from database
        from sqlalchemy import select
        from app.models.stratigraphy import USFile
        
        us_file_query = select(USFile).where(USFile.id == file_id_uuid)
        us_file = await db.execute(us_file_query)
        us_file = us_file.scalar_one_or_none()
        
        if not us_file:
            raise HTTPException(status_code=404, detail="File US non trovato")
        
        # Verify user has access to the site
        if not verify_site_access(us_file.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Check if thumbnail exists
        if us_file.thumbnail_path:
            # Use the archaeological_minio_service directly for US file thumbnails
            from app.services.archaeological_minio_service import archaeological_minio_service
            import io
            
            try:
                # Construct proper MinIO path with bucket prefix for thumbnail
                minio_thumbnail_path = f"minio://{archaeological_minio_service.buckets['thumbnails']}/{us_file.thumbnail_path}"
                
                # Get thumbnail data from MinIO
                thumbnail_data = await archaeological_minio_service.get_file(minio_thumbnail_path)
                
                if thumbnail_data and isinstance(thumbnail_data, bytes):
                    return StreamingResponse(
                        io.BytesIO(thumbnail_data),
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                else:
                    raise HTTPException(status_code=404, detail="Thumbnail data non valido")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error serving US file thumbnail from MinIO: {e}")
                raise HTTPException(status_code=500, detail=f"Errore nel servire thumbnail: {str(e)}")
        
        # If no thumbnail, try to serve the original file (smaller)
        if us_file.filepath:
            from app.services.archaeological_minio_service import archaeological_minio_service
            import io
            
            try:
                # Construct proper MinIO path with bucket prefix (fallback to original if no thumbnail)
                minio_path = f"minio://{archaeological_minio_service.buckets['photos']}/{us_file.filepath}"
                
                # Get file data from MinIO
                file_data = await archaeological_minio_service.get_file(minio_path)
                
                if file_data and isinstance(file_data, bytes):
                    return StreamingResponse(
                        io.BytesIO(file_data),
                        media_type=us_file.mimetype or "image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                else:
                    raise HTTPException(status_code=404, detail="File data non valido")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error serving US file from MinIO: {e}")
                raise HTTPException(status_code=500, detail=f"Errore nel servire file: {str(e)}")
        
        # If no filepath, return 404
        raise HTTPException(status_code=404, detail="File non disponibile")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore thumbnail file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore thumbnail")

@router.get("/{file_id}/download")
async def download_us_file(
    file_id: str,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Download file US/USM"""
    
    # Normalize UUID if needed
    normalized_file_id = normalize_uuid_string(file_id)
    file_id_uuid = UUID(normalized_file_id)
    
    try:
        # Get USFile record from database
        from sqlalchemy import select
        from app.models.stratigraphy import USFile
        
        us_file_query = select(USFile).where(USFile.id == file_id_uuid)
        us_file = await db.execute(us_file_query)
        us_file = us_file.scalar_one_or_none()
        
        if not us_file:
            raise HTTPException(status_code=404, detail="File US non trovato")
        
        # Verify user has access to the site
        if not verify_site_access(us_file.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Serve the file for download using the archaeological_minio_service
        if us_file.filepath:
            from app.services.archaeological_minio_service import archaeological_minio_service
            import io
            
            try:
                # Construct proper MinIO path with bucket prefix for download
                minio_path = f"minio://{archaeological_minio_service.buckets['photos']}/{us_file.filepath}"
                
                # Get file data from MinIO
                file_data = await archaeological_minio_service.get_file(minio_path)
                
                if file_data and isinstance(file_data, bytes):
                    # Determine filename for download
                    filename = us_file.original_filename or us_file.filename or f"us_file_{file_id_uuid}"
                    
                    return StreamingResponse(
                        io.BytesIO(file_data),
                        media_type=us_file.mimetype or "application/octet-stream",
                        headers={
                            "Content-Disposition": f"attachment; filename=\"{filename}\"",
                            "Cache-Control": "private, max-age=0"
                        }
                    )
                else:
                    raise HTTPException(status_code=404, detail="File data non valido")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error downloading US file from MinIO: {e}")
                raise HTTPException(status_code=500, detail=f"Errore nel download: {str(e)}")
        
        # If no filepath, return 404
        raise HTTPException(status_code=404, detail="File non disponibile per il download")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore download file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore download")

# ===== UPDATE FILE METADATA =====

@router.put("/{file_id}/metadata")
async def update_us_file_metadata(
    file_id: str,
    metadata: Dict[str, Any],
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Aggiorna metadati file US/USM"""
    
    # Normalize UUID if needed
    normalized_file_id = normalize_uuid_string(file_id)
    file_id_uuid = UUID(normalized_file_id)
    
    try:
        us_file_service = USFileService(db)
        updated_file = await us_file_service.update_file_metadata(
            file_id=file_id_uuid,
            metadata=metadata,
            user_id=current_user_id
        )
        
        return {
            'message': 'Metadati aggiornati con successo',
            'file': updated_file.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento metadati {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore aggiornamento: {str(e)}")

# ===== DELETE FILE =====

@router.delete("/us/{us_id}/files/{file_id}")
async def delete_us_file(
    us_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Elimina file da US"""
    
    # Normalize UUIDs if needed
    normalized_us_id = normalize_uuid_string(us_id)
    normalized_file_id = normalize_uuid_string(file_id)
    us_id_uuid = UUID(normalized_us_id)
    file_id_uuid = UUID(normalized_file_id)
    
    try:
        us_file_service = USFileService(db)
        success = await us_file_service.delete_us_file(
            us_id=us_id_uuid,
            file_id=file_id_uuid,
            user_id=current_user_id
        )
        
        if success:
            return {'message': 'File eliminato con successo'}
        else:
            raise HTTPException(status_code=500, detail="Eliminazione fallita")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione file {file_id_uuid} da US {us_id_uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")

@router.delete("/usm/{usm_id}/files/{file_id}")
async def delete_usm_file(
    usm_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Elimina file da USM"""
    
    # Normalize UUIDs if needed
    normalized_usm_id = normalize_uuid_string(usm_id)
    normalized_file_id = normalize_uuid_string(file_id)
    usm_id_uuid = UUID(normalized_usm_id)
    file_id_uuid = UUID(normalized_file_id)
    
    try:
        us_file_service = USFileService(db)
        success = await us_file_service.delete_usm_file(
            usm_id=usm_id_uuid,
            file_id=file_id_uuid,
            user_id=current_user_id
        )
        
        if success:
            return {'message': 'File eliminato con successo'}
        else:
            raise HTTPException(status_code=500, detail="Eliminazione fallita")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione file {file_id_uuid} da USM {usm_id_uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")

# ===== UTILITY ENDPOINTS =====

@router.get("/supported-types")
async def get_supported_file_types():
    """Ottieni tipi di file supportati per US/USM"""
    
    return {
        'supported_types': USFileService.SUPPORTED_FILE_TYPES,
        'file_categories': {
            'disegni_tecnici': ['pianta', 'sezione', 'prospetto'],
            'documentazione': ['fotografia', 'documento']
        }
    }

@router.get("/us/{us_id}/files/{file_type}/next-order")
async def get_next_file_order(
    us_id: str,
    file_type: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni prossimo numero d'ordine per tipo file in US"""
    
    # Normalize UUID if needed
    normalized_us_id = normalize_uuid_string(us_id)
    us_id_uuid = UUID(normalized_us_id)
    
    try:
        us_file_service = USFileService(db)
        files = await us_file_service.get_us_files(us_id_uuid, file_type)
        
        # Trova ordine massimo + 1
        max_order = 0
        if files:
            # Query per ottenere ordini dalla tabella associativa
            from sqlalchemy import select, func, and_
            from app.models.stratigraphy import us_files_association
            
            max_query = select(func.max(us_files_association.c.ordine)).where(
                and_(
                    us_files_association.c.us_id == us_id_uuid,
                    us_files_association.c.file_type == file_type
                )
            )
            result = await db.execute(max_query)
            max_order = result.scalar() or 0
        
        return {'next_order': max_order + 1}
        
    except Exception as e:
        logger.error(f"Errore calcolo next order: {str(e)}")
        return {'next_order': 1}  # Fallback