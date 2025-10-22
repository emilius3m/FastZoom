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

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.services.us_file_service import USFileService
from app.services.photo_serving_service import photo_serving_service
from app.models.stratigraphy import USFile

router = APIRouter(prefix="/api/us-files", tags=["us-files"])

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica accesso utente al sito"""
    return any(s["id"] == str(site_id) for s in user_sites)

# ===== UPLOAD FILE US =====

@router.post("/us/{us_id}/upload/{file_type}")
async def upload_us_file(
    us_id: UUID,
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
            us_id=us_id,
            file=file,
            file_type=file_type,
            user_id=current_user_id,
            metadata=metadata
        )
        
        logger.info(f"File {file_type} caricato per US {us_id}: {us_file.filename}")
        
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
    usm_id: UUID,
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
            usm_id=usm_id,
            file=file,
            file_type=file_type,
            user_id=current_user_id,
            metadata=metadata
        )
        
        logger.info(f"File {file_type} caricato per USM {usm_id}: {us_file.filename}")
        
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
    us_id: UUID,
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni tutti i file di una US, opzionalmente filtrati per tipo"""
    
    try:
        us_file_service = USFileService(db)
        files = await us_file_service.get_us_files(us_id, file_type)
        
        files_data = [file.to_dict() for file in files]
        
        return {
            'us_id': str(us_id),
            'file_type': file_type,
            'files': files_data,
            'count': len(files_data)
        }
        
    except Exception as e:
        logger.error(f"Errore recupero file US {us_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore recupero file: {str(e)}")

# ===== GET FILE USM =====

@router.get("/usm/{usm_id}/files")
async def get_usm_files(
    usm_id: UUID,
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni file USM"""
    
    try:
        us_file_service = USFileService(db)
        files = await us_file_service.get_usm_files(usm_id, file_type)
        
        files_data = [file.to_dict() for file in files]
        
        return {
            'usm_id': str(usm_id),
            'file_type': file_type,
            'files': files_data,
            'count': len(files_data)
        }
        
    except Exception as e:
        logger.error(f"Errore recupero file USM {usm_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore recupero file: {str(e)}")

# ===== GET FILES SUMMARY =====

@router.get("/us/{us_id}/files/summary")
async def get_us_files_summary(
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Riassunto file US raggruppati per tipo"""
    
    try:
        us_file_service = USFileService(db)
        summary = await us_file_service.get_files_summary_for_us(us_id)
        
        return {
            'us_id': str(us_id),
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"Errore summary file US {us_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore summary: {str(e)}")

@router.get("/usm/{usm_id}/files/summary")
async def get_usm_files_summary(
    usm_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Riassunto file USM raggruppati per tipo"""
    
    try:
        us_file_service = USFileService(db)
        summary = await us_file_service.get_files_summary_for_usm(usm_id)
        
        return {
            'usm_id': str(usm_id),
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"Errore summary file USM {usm_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore summary: {str(e)}")

# ===== SERVE FILE CONTENT =====

@router.get("/{file_id}/view")
async def view_us_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Visualizza file US/USM (stream per immagini)"""
    
    try:
        # Get USFile record from database
        from sqlalchemy import select
        from app.models.stratigraphy import USFile
        
        us_file_query = select(USFile).where(USFile.id == file_id)
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
                # Get file data from MinIO
                file_data = await archaeological_minio_service.get_file(us_file.filepath)
                
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
        logger.error(f"Errore serving file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore visualizzazione file: {str(e)}")

@router.get("/{file_id}/thumbnail")
async def get_us_file_thumbnail(
    file_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni thumbnail file US/USM"""
    
    try:
        # Get USFile record from database
        from sqlalchemy import select
        from app.models.stratigraphy import USFile
        
        us_file_query = select(USFile).where(USFile.id == file_id)
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
                # Get thumbnail data from MinIO
                thumbnail_data = await archaeological_minio_service.get_file(us_file.thumbnail_path)
                
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
                # Get file data from MinIO
                file_data = await archaeological_minio_service.get_file(us_file.filepath)
                
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
    file_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Download file US/USM"""
    
    try:
        # Get USFile record from database
        from sqlalchemy import select
        from app.models.stratigraphy import USFile
        
        us_file_query = select(USFile).where(USFile.id == file_id)
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
                # Get file data from MinIO
                file_data = await archaeological_minio_service.get_file(us_file.filepath)
                
                if file_data and isinstance(file_data, bytes):
                    # Determine filename for download
                    filename = us_file.original_filename or us_file.filename or f"us_file_{file_id}"
                    
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
    file_id: UUID,
    metadata: Dict[str, Any],
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Aggiorna metadati file US/USM"""
    
    try:
        us_file_service = USFileService(db)
        updated_file = await us_file_service.update_file_metadata(
            file_id=file_id,
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
    us_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Elimina file da US"""
    
    try:
        us_file_service = USFileService(db)
        success = await us_file_service.delete_us_file(
            us_id=us_id,
            file_id=file_id,
            user_id=current_user_id
        )
        
        if success:
            return {'message': 'File eliminato con successo'}
        else:
            raise HTTPException(status_code=500, detail="Eliminazione fallita")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione file {file_id} da US {us_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")

@router.delete("/usm/{usm_id}/files/{file_id}")
async def delete_usm_file(
    usm_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Elimina file da USM"""
    
    try:
        us_file_service = USFileService(db)
        success = await us_file_service.delete_usm_file(
            usm_id=usm_id,
            file_id=file_id,
            user_id=current_user_id
        )
        
        if success:
            return {'message': 'File eliminato con successo'}
        else:
            raise HTTPException(status_code=500, detail="Eliminazione fallita")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione file {file_id} da USM {usm_id}: {str(e)}")
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
    us_id: UUID,
    file_type: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni prossimo numero d'ordine per tipo file in US"""
    
    try:
        us_file_service = USFileService(db)
        files = await us_file_service.get_us_files(us_id, file_type)
        
        # Trova ordine massimo + 1
        max_order = 0
        if files:
            # Query per ottenere ordini dalla tabella associativa
            from sqlalchemy import select, func, and_
            from app.models.stratigraphy import us_files_association
            
            max_query = select(func.max(us_files_association.c.ordine)).where(
                and_(
                    us_files_association.c.us_id == us_id,
                    us_files_association.c.file_type == file_type
                )
            )
            result = await db.execute(max_query)
            max_order = result.scalar() or 0
        
        return {'next_order': max_order + 1}
        
    except Exception as e:
        logger.error(f"Errore calcolo next order: {str(e)}")
        return {'next_order': 1}  # Fallback