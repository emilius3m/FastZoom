# app/services/photos/deletion_service.py - Photo Deletion Service

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import json

from app.models import Photo, UserActivity, USFile
from app.services.archaeological_minio_service import archaeological_minio_service


class PhotoDeletionService:
    """Service for handling photo deletion operations with US file protection and storage cleanup"""
    
    def __init__(self):
        self.logger = logger.bind(service="photo_deletion_service")
    
    async def delete_single_photo(
        self,
        site_id: str,
        photo_id: UUID,
        current_user_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Delete a single photo with protection against US file deletion
        
        Args:
            site_id: Site identifier (already normalized)
            photo_id: Photo ID to delete
            current_user_id: User performing the deletion
            db: Database session
            
        Returns:
            Dictionary with deletion results
            
        Raises:
            HTTPException: For validation or operation errors
        """
        try:
            self.logger.info(f"Starting photo deletion: photo_id={photo_id}, site_id={site_id}")
            
            # Check if this is a US photo (which should not be deleted from here)
            await self._check_us_photo_protection(db, site_id, str(photo_id))
            
            # Get the photo to delete
            photo = await self._get_photo_for_deletion(db, site_id, str(photo_id))
            
            if not photo:
                raise HTTPException(status_code=404, detail="Foto non trovata nel sito")
            
            # Perform the deletion with storage cleanup
            deletion_result = await self._execute_single_photo_deletion(
                db, photo, current_user_id, site_id
            )
            
            self.logger.info(f"Photo deletion completed: {photo_id}")
            
            return deletion_result
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Photo deletion error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Errore durante eliminazione foto: {str(e)}"
            )
    
    async def _check_us_photo_protection(
        self,
        db: AsyncSession,
        site_id: str,
        photo_id: str
    ) -> None:
        """Check if photo is a US file and should be protected"""
        us_file_query = select(USFile).where(
            and_(USFile.id == photo_id, USFile.site_id == site_id)
        )
        us_file = await db.execute(us_file_query)
        us_file = us_file.scalar_one_or_none()
        
        if us_file:
            raise HTTPException(
                status_code=403,
                detail="Questa foto appartiene a una US/USM e può essere eliminata solo dalla pagina US"
            )
    
    async def _get_photo_for_deletion(
        self,
        db: AsyncSession,
        site_id: str,
        photo_id: str
    ) -> Photo:
        """Get photo for deletion with proper validation"""
        photo_query = select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
        photo = await db.execute(photo_query)
        photo = photo.scalar_one_or_none()
        
        return photo
    
    async def _execute_single_photo_deletion(
        self,
        db: AsyncSession,
        photo: Photo,
        current_user_id: UUID,
        site_id: str
    ) -> Dict[str, Any]:
        """Execute the actual photo deletion with storage cleanup and activity logging"""
        photo_filename = photo.filename
        photo_path = photo.filepath
        thumbnail_path = photo.thumbnail_path
        
        try:
            # Delete from database first
            await db.delete(photo)
            await db.commit()
            
            # Clean up storage after successful database deletion
            cleanup_result = await self._cleanup_photo_storage(photo_path, thumbnail_path)
            
            # Log activity
            await self._log_deletion_activity(
                db, current_user_id, site_id, photo.id, photo_filename, 
                photo_path, thumbnail_path
            )
            
            self.logger.info(f"Photo {photo.id} deleted successfully with storage cleanup")
            
            # Send WebSocket notification for photo deletion
            try:
                from app.routes.api.notifications_ws import notification_manager
                await notification_manager.broadcast_photo_deleted(
                    site_id=site_id,
                    photo_id=str(photo.id),
                    photo_filename=photo_filename,
                    user_id=str(current_user_id)
                )
                self.logger.info(f"WebSocket notification sent for photo deletion: {photo.id}")
            except Exception as ws_error:
                self.logger.warning(f"Failed to send WebSocket notification for photo deletion: {ws_error}")
            
            return {
                "message": "Foto eliminata con successo",
                "photo_id": str(photo.id),
                "filename": photo_filename,
                "storage_cleanup": cleanup_result
            }
            
        except Exception as e:
            self.logger.error(f"Error during photo deletion: {e}")
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Errore durante eliminazione foto: {str(e)}"
            )
    
    async def _cleanup_photo_storage(
        self,
        photo_path: str,
        thumbnail_path: str
    ) -> Dict[str, Any]:
        """Clean up photo storage (MinIO and local files)"""
        import time
        start_time = time.time()
        
        cleanup_result = {
            "photo_file_deleted": False,
            "thumbnail_deleted": False,
            "errors": []
        }
        
        with logger.contextualize(
            operation="cleanup_photo_storage",
            photo_path=photo_path,
            thumbnail_path=thumbnail_path
        ):
            logger.info("Starting storage cleanup")
            
            try:
                # Delete main photo file
                if photo_path:
                    if '/' in photo_path:
                        # MinIO file
                        try:
                            success = await archaeological_minio_service.remove_file(photo_path)
                            cleanup_result["photo_file_deleted"] = success
                            if success:
                                logger.info("MinIO file deleted successfully")
                            else:
                                logger.warning("Could not delete MinIO file")
                        except Exception as e:
                            error_msg = f"Error deleting MinIO file: {e}"
                            cleanup_result["errors"].append(error_msg)
                            logger.error("MinIO file deletion error", error=str(e))
                    
                    elif photo_path.startswith("storage/") or photo_path.startswith("app/static/uploads/"):
                        # Local file
                        try:
                            from pathlib import Path
                            file_path = Path(photo_path)
                            if file_path.exists():
                                file_path.unlink()
                                cleanup_result["photo_file_deleted"] = True
                                logger.info("Local file deleted successfully")
                        except Exception as e:
                            error_msg = f"Error deleting local file: {e}"
                            cleanup_result["errors"].append(error_msg)
                            logger.error("Local file deletion error", error=str(e))
                
                # Delete thumbnail
                if thumbnail_path:
                    if thumbnail_path.startswith("thumbnails/"):
                        # MinIO thumbnail
                        try:
                            success = await archaeological_minio_service.remove_object_from_bucket(
                                archaeological_minio_service.buckets["thumbnails"],
                                thumbnail_path
                            )
                            cleanup_result["thumbnail_deleted"] = success
                            if success:
                                logger.info("MinIO thumbnail deleted successfully")
                            else:
                                logger.warning("Could not delete MinIO thumbnail")
                        except Exception as e:
                            error_msg = f"Error deleting MinIO thumbnail: {e}"
                            cleanup_result["errors"].append(error_msg)
                            logger.error("MinIO thumbnail deletion error", error=str(e))
                    
                    elif thumbnail_path.startswith("storage/thumbnails/"):
                        # Local thumbnail
                        try:
                            from pathlib import Path
                            thumbnail_file_path = Path(thumbnail_path)
                            if thumbnail_file_path.exists():
                                thumbnail_file_path.unlink()
                                cleanup_result["thumbnail_deleted"] = True
                                logger.info("Local thumbnail deleted successfully")
                        except Exception as e:
                            error_msg = f"Error deleting local thumbnail: {e}"
                            cleanup_result["errors"].append(error_msg)
                            logger.error("Local thumbnail deletion error", error=str(e))
                
            except Exception as e:
                error_msg = f"General error during storage cleanup: {e}"
                cleanup_result["errors"].append(error_msg)
                logger.error("Storage cleanup error", error=str(e))
            
            duration = time.time() - start_time
            logger.info("Storage cleanup completed",
                       photo_file_deleted=cleanup_result["photo_file_deleted"],
                       thumbnail_deleted=cleanup_result["thumbnail_deleted"],
                       errors_count=len(cleanup_result["errors"]),
                       duration=duration)
        
        return cleanup_result
    
    async def _log_deletion_activity(
        self,
        db: AsyncSession,
        current_user_id: UUID,
        site_id: str,
        photo_id: UUID,
        photo_filename: str,
        photo_path: str,
        thumbnail_path: str
    ) -> None:
        """Log photo deletion activity"""
        try:
            activity = UserActivity(
                user_id=str(current_user_id),
                site_id=site_id,
                activity_type="DELETE",
                activity_desc=f"Eliminata foto: {photo_filename}",
                extra_data=json.dumps({
                    "photo_id": str(photo_id),
                    "filename": photo_filename,
                    "file_path": photo_path,
                    "thumbnail_path": thumbnail_path
                })
            )
            
            db.add(activity)
            await db.commit()
            
            self.logger.info(f"Activity logged for photo deletion: {photo_id}")
            
        except Exception as e:
            self.logger.warning(f"Failed to log photo deletion activity: {e}")
            # Don't fail the operation if activity logging fails
    
    async def verify_photo_access(
        self,
        site_id: str,
        photo_id: UUID,
        current_user_id: UUID,
        db: AsyncSession,
        required_permission: str = "read"
    ) -> Photo:
        """
        Verify photo access and return photo object
        
        Args:
            site_id: Site identifier (already normalized)
            photo_id: Photo ID to verify
            current_user_id: User requesting access
            db: Database session
            required_permission: Permission type required
            
        Returns:
            Photo object if access is valid
            
        Raises:
            HTTPException: If access is denied or photo not found
        """
        try:
            # Check if photo exists and belongs to the site
            photo = await self._get_photo_for_deletion(db, site_id, str(photo_id))
            
            if not photo:
                raise HTTPException(
                    status_code=404, 
                    detail="Foto non trovata nel sito"
                )
            
            # Additional access checks can be added here based on permissions
            # For now, basic existence check is sufficient
            
            return photo
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Photo access verification error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Errore verifica accesso foto: {str(e)}"
            )
    
    async def get_photo_info(
        self,
        site_id: str,
        photo_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get comprehensive photo information for serving operations
        
        Args:
            site_id: Site identifier (already normalized)
            photo_id: Photo ID to get info for
            db: Database session
            
        Returns:
            Dictionary with photo information
            
        Raises:
            HTTPException: If photo not found
        """
        try:
            photo = await self._get_photo_for_deletion(db, site_id, str(photo_id))
            
            if not photo:
                raise HTTPException(
                    status_code=404,
                    detail="Foto non trovata nel sito"
                )
            
            return {
                "id": str(photo.id),
                "site_id": photo.site_id,
                "filename": photo.filename,
                "filepath": photo.filepath,
                "thumbnail_path": photo.thumbnail_path,
                "file_size": photo.file_size,
                "width": photo.width,
                "height": photo.height,
                "photo_type": photo.photo_type,
                "photographer": photo.photographer,
                "is_published": photo.is_published,
                "is_validated": photo.is_validated,
                "has_deep_zoom": photo.has_deep_zoom,
                "deepzoom_status": photo.deepzoom_status,
                "created_at": photo.created_at.isoformat() if photo.created_at else None,
                "updated_at": photo.updated.isoformat() if photo.updated else None
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Photo info retrieval error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Errore recupero informazioni foto: {str(e)}"
            )


# Create global instance
photo_deletion_service = PhotoDeletionService()