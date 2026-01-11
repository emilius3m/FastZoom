# app/services/photos/bulk_service.py - Photo Bulk Operations Service

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
import json

from app.models import Photo, PhotoType, MaterialType, ConservationStatus, UserActivity, USFile
from app.services.archaeological_minio_service import archaeological_minio_service
from app.schemas.photos import BulkUpdateRequest, BulkDeleteRequest


class PhotoBulkService:
    """Service for handling bulk photo operations (update/delete)"""
    
    def __init__(self):
        self.logger = logger.bind(service="photo_bulk_service")
    
    async def bulk_update_photos(
        self,
        site_id: str,
        update_request: BulkUpdateRequest,
        current_user_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Perform bulk update of photos with comprehensive metadata support
        
        Args:
            site_id: Site identifier (already normalized)
            update_request: Pydantic model with update data
            current_user_id: User performing the operation
            db: Database session
            
        Returns:
            Dictionary with update results and statistics
            
        Raises:
            HTTPException: For validation or operation errors
        """
        try:
            self.logger.info(f"Starting bulk update for {len(update_request.photo_ids)} photos in site {site_id}")
            
            # Validate and convert photo IDs
            photo_ids = self._validate_and_convert_photo_ids(update_request.photo_ids)
            if not photo_ids:
                raise HTTPException(status_code=400, detail="Nessun ID foto valido")
            
            # Query photos for update
            photos = await self._get_photos_for_bulk_operation(
                db, str(site_id), photo_ids, operation_type="update"
            )
            
            if not photos:
                raise HTTPException(status_code=404, detail="Nessuna foto trovata con gli ID specificati")
            
            # Prepare filtered metadata
            filtered_metadata = self._prepare_bulk_update_metadata(update_request.metadata)
            
            # Perform the bulk update
            update_result = await self._execute_bulk_update(
                db, photos, filtered_metadata, update_request.add_tags, 
                update_request.remove_tags, current_user_id, site_id
            )
            
            self.logger.info(f"Bulk update completed: {update_result['updated_count']} photos updated")
            
            return {
                "message": f"{update_result['updated_count']} foto aggiornate con successo",
                "updated_count": update_result['updated_count'],
                "updated_fields": update_result['updated_fields']
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Bulk update error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Errore aggiornamento in blocco: {str(e)}"
            )
    
    async def bulk_delete_photos(
        self,
        site_id: str,
        delete_request: BulkDeleteRequest,
        current_user_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Perform bulk deletion of photos with US file protection
        
        Args:
            site_id: Site identifier (already normalized)
            delete_request: Pydantic model with delete data
            current_user_id: User performing the operation
            db: Database session
            
        Returns:
            Dictionary with deletion results
            
        Raises:
            HTTPException: For validation or operation errors
        """
        try:
            self.logger.info(f"Starting bulk delete for {len(delete_request.photo_ids)} photos in site {site_id}")
            
            # Validate and convert photo IDs
            photo_ids = self._validate_and_convert_photo_ids(delete_request.photo_ids)
            if not photo_ids:
                raise HTTPException(status_code=400, detail="Nessun ID foto valido")
            
            # Check for US photos protection
            await self._check_us_photos_protection(db, site_id, photo_ids)
            
            # Query photos for deletion
            photos = await self._get_photos_for_bulk_operation(
                db, site_id, photo_ids, operation_type="delete"
            )
            
            if not photos:
                raise HTTPException(status_code=404, detail="Nessuna foto trovata con gli ID specificati")
            
            # Perform the bulk deletion
            deletion_result = await self._execute_bulk_deletion(
                db, photos, current_user_id, site_id
            )
            
            self.logger.info(f"Bulk deletion completed: {deletion_result['deleted_count']} photos deleted")
            
            return {
                "message": f"{deletion_result['deleted_count']} foto eliminate con successo",
                "deleted_count": deletion_result['deleted_count']
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Bulk delete error: {e}")
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Errore eliminazione in blocco: {str(e)}"
            )
    
    def _validate_and_convert_photo_ids(self, photo_ids_raw: List[Any]) -> List[UUID]:
        """Validate and convert photo IDs to UUID format"""
        photo_ids = []
        for photo_id in photo_ids_raw:
            if isinstance(photo_id, str):
                try:
                    photo_ids.append(UUID(photo_id))
                except ValueError:
                    self.logger.warning(f"Invalid UUID format: {photo_id}")
                    continue
            elif isinstance(photo_id, UUID):
                photo_ids.append(photo_id)
            else:
                self.logger.warning(f"Unexpected photo_id type: {type(photo_id)} - {photo_id}")
        
        return photo_ids
    
    async def _get_photos_for_bulk_operation(
        self,
        db: AsyncSession,
        site_id: str,
        photo_ids: List[UUID],
        operation_type: str
    ) -> List[Photo]:
        """Query photos for bulk operations"""
        # Convert to strings for database comparison (Photo.id is stored as string)
        photo_ids_str = [str(pid) for pid in photo_ids]
        
        photos_query = select(Photo).where(and_(
            Photo.site_id == site_id,
            Photo.id.in_(photo_ids_str)
        ))
        
        photos = await db.execute(photos_query)
        photos = photos.scalars().all()
        
        if not photos:
            # Debug information
            all_photos_query = select(Photo).where(Photo.site_id == site_id)
            all_photos_result = await db.execute(all_photos_query)
            all_photos = all_photos_result.scalars().all()
            self.logger.debug(f"All photos in site {site_id}: {[str(p.id) for p in all_photos]}")
            
            any_photos_query = select(Photo).where(Photo.id.in_(photo_ids_str))
            any_photos_result = await db.execute(any_photos_query)
            any_photos = any_photos_result.scalars().all()
            self.logger.debug(f"Photos with requested IDs in ANY site: {[str(p.id) + ' (site: ' + p.site_id + ')' for p in any_photos]}")
        
        return photos
    
    async def _check_us_photos_protection(
        self,
        db: AsyncSession,
        site_id: str,
        photo_ids: List[UUID]
    ) -> None:
        """Check if any photos are US files and should be protected"""
        photo_ids_str = [str(pid) for pid in photo_ids]
        
        us_files_query = select(USFile).where(
            and_(USFile.site_id == site_id, USFile.id.in_(photo_ids_str))
        )
        us_files = await db.execute(us_files_query)
        us_files_list = us_files.scalars().all()
        
        if us_files_list:
            us_count = len(us_files_list)
            raise HTTPException(
                status_code=403,
                detail=f"{us_count} foto appartengono a US/USM e non possono essere eliminate da qui"
            )
    
    def _prepare_bulk_update_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare and filter metadata for bulk update"""
        updatable_fields = {
            'title', 'description', 'keywords', 'photo_type', 'photographer',
            'inventory_number', 'catalog_number',
            'excavation_area', 'stratigraphic_unit', 'grid_square', 'depth_level',
            'find_date', 'finder', 'excavation_campaign',
            'material', 'material_details', 'object_type', 'object_function',
            'length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams',
            'chronology_period', 'chronology_culture',
            'dating_from', 'dating_to', 'dating_notes',
            'conservation_status', 'conservation_notes', 'restoration_history',
            'bibliography', 'comparative_references', 'external_links',
            'copyright_holder', 'license_type', 'usage_rights',
            'validation_notes'
        }
        
        filtered_metadata = {}
        for field in updatable_fields:
            if field in metadata and metadata[field] is not None and metadata[field] != '':
                value = metadata[field]
                
                # Handle numeric fields
                if field in ['length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams', 'depth_level']:
                    try:
                        filtered_metadata[field] = float(value) if value else None
                    except (ValueError, TypeError):
                        filtered_metadata[field] = None
                else:
                    filtered_metadata[field] = value
        
        # Convert enum fields
        filtered_metadata = self._convert_enum_fields(filtered_metadata)
        
        # Handle date fields
        filtered_metadata = self._convert_date_fields(filtered_metadata)
        
        # Handle JSON fields
        filtered_metadata = self._convert_json_fields(filtered_metadata)
        
        return filtered_metadata
    
    def _convert_enum_fields(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert enum fields using centralized conversion system"""
        try:
            from app.utils.enum_mappings import enum_converter, log_conversion_attempt
            
            # Convert photo_type
            if 'photo_type' in metadata and metadata['photo_type']:
                converted_photo_type = enum_converter.convert_to_enum(PhotoType, metadata['photo_type'])
                if converted_photo_type is None:
                    raise HTTPException(status_code=400, detail=f"Tipo foto non valido: {metadata['photo_type']}")
                metadata['photo_type'] = converted_photo_type
                log_conversion_attempt(PhotoType, str(metadata['photo_type']), converted_photo_type, True)
            
            # Convert material
            if 'material' in metadata and metadata['material']:
                converted_material = enum_converter.convert_to_enum(MaterialType, metadata['material'])
                if converted_material is None:
                    raise HTTPException(status_code=400, detail=f"Materiale non valido: {metadata['material']}")
                metadata['material'] = converted_material
                log_conversion_attempt(MaterialType, str(metadata['material']), converted_material, True)
            
            # Convert conservation_status
            if 'conservation_status' in metadata and metadata['conservation_status']:
                converted_conservation = enum_converter.convert_to_enum(
                    ConservationStatus, metadata['conservation_status']
                )
                if converted_conservation is None:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Stato di conservazione non valido: {metadata['conservation_status']}"
                    )
                metadata['conservation_status'] = converted_conservation
                log_conversion_attempt(ConservationStatus, str(metadata['conservation_status']), converted_conservation, True)
                
        except ImportError:
            # Fallback to basic conversion if enum_mappings is not available
            self.logger.warning("enum_mappings not available, using basic enum conversion")
            metadata = self._fallback_enum_conversion(metadata)
        
        return metadata
    
    def _fallback_enum_conversion(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback enum conversion when enum_mappings is not available"""
        if 'photo_type' in metadata and metadata['photo_type']:
            try:
                metadata['photo_type'] = PhotoType(metadata['photo_type'])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Tipo foto non valido: {metadata['photo_type']}")
        
        if 'material' in metadata and metadata['material']:
            try:
                metadata['material'] = MaterialType(metadata['material'])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Materiale non valido: {metadata['material']}")
        
        if 'conservation_status' in metadata and metadata['conservation_status']:
            try:
                metadata['conservation_status'] = ConservationStatus(metadata['conservation_status'])
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Stato di conservazione non valido: {metadata['conservation_status']}"
                )
        
        return metadata
    
    def _convert_date_fields(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert date fields to datetime objects"""
        if 'find_date' in metadata and metadata['find_date']:
            try:
                if isinstance(metadata['find_date'], str):
                    if metadata['find_date'] in ['', 'null', 'None']:
                        metadata['find_date'] = None
                    else:
                        try:
                            metadata['find_date'] = datetime.fromisoformat(metadata['find_date'])
                        except ValueError:
                            try:
                                metadata['find_date'] = datetime.strptime(metadata['find_date'], '%Y-%m-%d')
                            except ValueError:
                                raise HTTPException(status_code=400, detail="Formato data non valido per find_date")
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato data non valido per find_date")
        
        return metadata
    
    def _convert_json_fields(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert JSON fields to proper format"""
        if 'keywords' in metadata:
            if isinstance(metadata['keywords'], str) and metadata['keywords']:
                keywords_list = [kw.strip() for kw in metadata['keywords'].split(',') if kw.strip()]
                metadata['keywords'] = json.dumps(keywords_list)
            elif isinstance(metadata['keywords'], list):
                metadata['keywords'] = json.dumps(metadata['keywords'])
        
        if 'external_links' in metadata and isinstance(metadata['external_links'], list):
            metadata['external_links'] = json.dumps(metadata['external_links'])
        
        return metadata
    
    async def _execute_bulk_update(
        self,
        db: AsyncSession,
        photos: List[Photo],
        filtered_metadata: Dict[str, Any],
        add_tags: List[str],
        remove_tags: List[str],
        current_user_id: UUID,
        site_id: str
    ) -> Dict[str, Any]:
        """Execute the actual bulk update operation"""
        import time
        start_time = time.time()
        updated_count = 0
        updated_fields = []
        
        with logger.contextualize(
            operation="bulk_update",
            site_id=site_id,
            user_id=str(current_user_id),
            photo_count=len(photos)
        ):
            logger.info("Starting bulk update operation")
            
            async with db.begin():  # Auto-commit on success, auto-rollback on exception
                # Update all photos within the transaction
                for photo in photos:
                    try:
                        # Apply metadata updates
                        for field, value in filtered_metadata.items():
                            old_value = getattr(photo, field, None)
                            setattr(photo, field, value)
                            if field not in updated_fields:
                                updated_fields.append(field)
                            logger.debug("Field updated",
                                        photo_id=str(photo.id),
                                        field=field,
                                        old_value=old_value,
                                        new_value=value)
                        
                        # Handle tag updates
                        if add_tags or remove_tags:
                            tag_fields = self._update_photo_tags(photo, add_tags, remove_tags)
                            updated_fields.extend(tag_fields)
                        
                        # Update timestamp
                        photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
                        updated_count += 1
                        
                    except Exception as e:
                        logger.warning("Error updating photo", photo_id=str(photo.id), error=str(e))
                        continue
                
                # Log activity after all updates within the same transaction
                if updated_count > 0:
                    activity = UserActivity(
                        user_id=str(current_user_id),
                        site_id=str(site_id),
                        activity_type="BULK_UPDATE",
                        activity_desc=f"Aggiornamento massivo di {updated_count} foto",
                        extra_data=json.dumps({
                            "photo_count": updated_count,
                            "photo_ids": [str(p.id) for p in photos[:updated_count]],
                            "updated_fields": updated_fields,
                            "metadata_fields": list(filtered_metadata.keys()),
                            "add_tags": add_tags,
                            "remove_tags": remove_tags
                        })
                    )
                    db.add(activity)
                    logger.debug("Activity log added", updated_count=updated_count)
            
            duration = time.time() - start_time
            logger.info("Bulk update completed",
                       updated_count=updated_count,
                       updated_fields=len(updated_fields),
                       duration=duration)
        
        return {
            'updated_count': updated_count,
            'updated_fields': updated_fields
        }
    
    def _update_photo_tags(self, photo: Photo, add_tags: List[str], remove_tags: List[str]) -> List[str]:
        """Update photo tags and return fields that were modified"""
        updated_fields = []
        
        current_tags = getattr(photo, 'tags', None) or []
        if isinstance(current_tags, str):
            try:
                current_tags = json.loads(current_tags)
            except:
                current_tags = []
        
        # Add new tags
        for tag in add_tags:
            if tag not in current_tags:
                current_tags.append(tag)
        
        # Remove tags
        for tag in remove_tags:
            if tag in current_tags:
                current_tags.remove(tag)
        
        # Update photo tags if they exist as a field
        if hasattr(photo, 'tags'):
            photo.tags = current_tags
            if 'tags' not in updated_fields:
                updated_fields.append('tags')
        
        return updated_fields
    
    async def _execute_bulk_deletion(
        self,
        db: AsyncSession,
        photos: List[Photo],
        current_user_id: UUID,
        site_id: str
    ) -> Dict[str, Any]:
        """Execute the actual bulk deletion operation"""
        deleted_count = 0
        
        try:
            # Delete all photos with storage cleanup
            for photo in photos:
                try:
                    await self._cleanup_photo_storage(photo)
                    
                    # Log activity before deletion
                    activity = UserActivity(
                        user_id=str(current_user_id),
                        site_id=str(site_id),
                        activity_type="DELETE",
                        activity_desc=f"Eliminazione massiva foto {photo.filename}",
                        extra_data=json.dumps({
                            "photo_id": str(photo.id),
                            "bulk_operation": True,
                            "filename": photo.filename
                        })
                    )
                    db.add(activity)
                    
                    # Delete from database
                    await db.delete(photo)
                    deleted_count += 1
                    
                except Exception as e:
                    self.logger.warning(f"Error deleting photo {photo.id}: {e}")
                    continue
            
            # Commit all deletions at once
            await db.commit()
            self.logger.info(f"Bulk delete transaction committed successfully for {deleted_count} photos")
            
            # Send WebSocket notifications for each deleted photo
            try:
                from app.routes.api.notifications_ws import notification_manager
                for photo in photos:
                    await notification_manager.broadcast_photo_deleted(
                        site_id=site_id,
                        photo_id=str(photo.id),
                        photo_filename=photo.filename,
                        user_id=str(current_user_id)
                    )
                self.logger.info(f"WebSocket notifications sent for {deleted_count} deleted photos")
            except Exception as ws_error:
                self.logger.warning(f"Failed to send WebSocket notifications for bulk delete: {ws_error}")
            
        except Exception as e:
            self.logger.error(f"Bulk delete transaction error: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Errore eliminazione in blocco: {str(e)}")
        
        return {
            'deleted_count': deleted_count
        }
    
    async def _cleanup_photo_storage(self, photo: Photo) -> None:
        """Clean up photo storage (MinIO and local files)"""
        photo_path = photo.filepath
        thumbnail_path = photo.thumbnail_path
        
        try:
            # Delete main photo file from MinIO
            if photo_path and '/' in photo_path:
                try:
                    success = await archaeological_minio_service.remove_file(photo_path)
                    if success:
                        self.logger.info(f"File deleted from MinIO: {photo_path}")
                    else:
                        self.logger.warning(f"Could not delete file: {photo_path}")
                except Exception as e:
                    self.logger.warning(f"Error deleting file {photo_path}: {e}")
            
            # Delete thumbnail from MinIO
            if thumbnail_path and thumbnail_path.startswith("thumbnails/"):
                try:
                    success = await archaeological_minio_service.remove_object_from_bucket(
                        archaeological_minio_service.buckets["thumbnails"],
                        thumbnail_path
                    )
                    if success:
                        self.logger.info(f"Thumbnail deleted from MinIO: {thumbnail_path}")
                    else:
                        self.logger.warning(f"Could not delete thumbnail: {thumbnail_path}")
                except Exception as e:
                    self.logger.warning(f"Error deleting thumbnail {thumbnail_path}: {e}")
            
            # NUOVO: Delete Deep Zoom tiles from MinIO
            if photo.has_deep_zoom:
                try:
                    # Construct tiles path for this photo
                    site_id = photo.site_id
                    photo_id = str(photo.id)
                    tiles_prefix = f"{site_id}/tiles/{photo_id}/"
                    
                    # List all tiles for this photo
                    from minio.error import S3Error
                    import asyncio
                    
                    def _list_tiles():
                        return archaeological_minio_service._client.list_objects(
                            bucket_name=archaeological_minio_service.buckets['tiles'],
                            prefix=tiles_prefix,
                            recursive=True
                        )
                    
                    tiles_objects = await asyncio.to_thread(_list_tiles)
                    tiles_to_delete = [obj for obj in tiles_objects if not obj.is_dir]
                    
                    # Delete all tiles
                    deleted_tiles_count = 0
                    for tile_obj in tiles_to_delete:
                        try:
                            def _delete_tile():
                                archaeological_minio_service._client.remove_object(
                                    bucket_name=archaeological_minio_service.buckets['tiles'],
                                    object_name=tile_obj.object_name
                                )
                            
                            await asyncio.to_thread(_delete_tile)
                            deleted_tiles_count += 1
                            
                        except Exception as tile_error:
                            self.logger.warning(f"Error deleting tile {tile_obj.object_name}: {tile_error}")
                    
                    # Delete metadata and processing status files
                    metadata_files = [
                        f"{tiles_prefix}metadata.json",
                        f"{tiles_prefix}processing_status.json"
                    ]
                    
                    for metadata_file in metadata_files:
                        try:
                            def _delete_metadata():
                                archaeological_minio_service._client.remove_object(
                                    bucket_name=archaeological_minio_service.buckets['tiles'],
                                    object_name=metadata_file
                                )
                            
                            await asyncio.to_thread(_delete_metadata)
                            
                        except Exception as meta_error:
                            self.logger.warning(f"Error deleting metadata {metadata_file}: {meta_error}")
                    
                    self.logger.info(f"Deleted {deleted_tiles_count} Deep Zoom tiles for photo {photo_id}")
                    
                except Exception as e:
                    self.logger.error(f"Error deleting Deep Zoom tiles for photo {photo.id}: {e}")
            
        except Exception as e:
            self.logger.warning(f"Error during photo storage cleanup: {e}")

    async def update_single_photo(
        self,
        site_id: str,
        photo_id: str,
        user_id: str,
        update_data: dict,
        db: AsyncSession
    ) -> dict:
        """
        Update a single photo with comprehensive metadata handling
        
        Args:
            site_id: Site identifier
            photo_id: Photo identifier
            user_id: User performing the update
            update_data: Dictionary of fields to update
            
        Returns:
            dict: Updated photo information
        """
        try:
            self.logger.info(f"Updating single photo {photo_id} in site {site_id}")
            
            # Get photo
            photo_query = select(Photo).where(
                and_(Photo.id == photo_id, Photo.site_id == site_id)
            )
            photo_result = await db.execute(photo_query)
            photo = photo_result.scalar_one_or_none()
            
            if not photo:
                raise HTTPException(status_code=404, detail="Foto non trovata nel sito")
            
            # Define updatable fields
            updatable_fields = {
                'title', 'description', 'keywords', 'photo_type', 'photographer',
                'inventory_number', 'catalog_number',
                'excavation_area', 'stratigraphic_unit', 'grid_square', 'depth_level',
                'find_date', 'finder', 'excavation_campaign',
                'material', 'material_details', 'object_type', 'object_function',
                'length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams',
                'chronology_period', 'chronology_culture',
                'dating_from', 'dating_to', 'dating_notes',
                'conservation_status', 'conservation_notes', 'restoration_history',
                'bibliography', 'comparative_references', 'external_links',
                'copyright_holder', 'license_type', 'usage_rights',
                'validation_notes'
            }
            
            # Filter and validate data
            filtered_data = {}
            for field in updatable_fields:
                if field in update_data and update_data[field] is not None:
                    value = update_data[field]
                    
                    # Handle numeric fields
                    if field in ['length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams', 'depth_level']:
                        if value == '' or value == 'null' or value == 'None':
                            filtered_data[field] = None
                        else:
                            try:
                                filtered_data[field] = float(value) if value else None
                            except (ValueError, TypeError):
                                filtered_data[field] = None
                    else:
                        filtered_data[field] = value
            
            # Convert enums using the centralized system
            filtered_data = self._convert_enum_fields(filtered_data)
            
            # Handle date fields
            filtered_data = self._convert_date_fields(filtered_data)
            
            # Handle JSON fields
            filtered_data = self._convert_json_fields(filtered_data)
            
            # Apply updates
            updated_fields = []
            for field, value in filtered_data.items():
                old_value = getattr(photo, field, None)
                if value == '' or value == 'null' or value == 'None':
                    setattr(photo, field, None)
                    updated_fields.append(field)
                elif old_value != value:
                    setattr(photo, field, value)
                    updated_fields.append(field)
            
            # Update timestamp
            photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Log activity
            activity = UserActivity(
                user_id=user_id,
                site_id=site_id,
                activity_type="UPDATE",
                activity_desc=f"Aggiornati metadati foto: {photo.filename}",
                extra_data=json.dumps({
                    "photo_id": photo_id,
                    "fields_updated": updated_fields
                })
            )
            db.add(activity)
            
            # Commit transaction
            await db.commit()
            await db.refresh(photo)
            
            # Broadcast WebSocket notification
            try:
                from app.routes.api.notifications_ws import notification_manager
                await notification_manager.broadcast_photo_updated(
                    site_id=site_id,
                    photo_id=photo_id,
                    updated_fields=updated_fields,
                    photo_filename=photo.filename,
                    user_id=user_id
                )
                self.logger.info(f"WebSocket notification sent for photo update: {photo_id}")
            except Exception as ws_error:
                self.logger.warning(f"Failed to send WebSocket notification for photo update: {ws_error}")
            
            response_data = {
                "message": "Foto aggiornata con successo",
                "photo_id": photo_id,
                "updated_fields": updated_fields,
                "photo_data": photo.to_dict()
            }
            
            self.logger.info(f"Single photo {photo_id} updated successfully: {updated_fields}")
            return response_data
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Single photo update error: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Errore aggiornamento foto: {str(e)}")


# Remove global instance - services should be instantiated with db parameter