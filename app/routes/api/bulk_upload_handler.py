# app/routes/api/bulk_upload_handler.py - Bulk upload processing handler

from typing import Dict, Any
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timezone
import json

async def process_queued_bulk_upload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process queued bulk upload request"""

    from app.services.storage_service import storage_service
    from app.services.photo_metadata_service import photo_metadata_service
    from app.services.deep_zoom_background_service import deep_zoom_background_service
    from app.models import Photo, UserActivity
    from sqlalchemy import select
    import uuid
    import aiofiles

    logger.info(f"Processing queued bulk upload for site {payload['site_id']}")

    try:
        site_id = uuid.UUID(payload['site_id'])
        user_id = uuid.UUID(payload['user_id'])
        metadata = payload.get('metadata', {})
        temp_files = payload.get('temp_files', [])

        # Process each photo in bulk
        uploaded_photos = []
        photos_needing_tiles = []
        failed_photos = []

        for temp_file in temp_files:
            try:
                # Check if temp file exists before moving
                temp_file_exists = await storage_service.file_exists(temp_file['file_path'])
                if not temp_file_exists:
                    logger.error(f"Temp file not found: {temp_file['file_path']}")
                    failed_photos.append({
                        'filename': temp_file.get('original_filename', 'Unknown'),
                        'error': 'Temp file not found'
                    })
                    continue

                # Move temp file to permanent location
                permanent_path = await storage_service.move_temp_file(
                    temp_file['file_path'],
                    str(site_id),
                    str(user_id)
                )

                # Extract metadata from the actual file
                file_metadata = {}
                try:
                    # Read file as bytes for metadata extraction
                    async with aiofiles.open(permanent_path, 'rb') as f:
                        content = await f.read()
                        
                        # Use refactored bytes-based method
                        exif_data, extracted_metadata = await photo_metadata_service.extract_metadata_from_bytes(
                            content, temp_file['original_filename']
                        )
                        file_metadata = extracted_metadata
                except Exception as metadata_error:
                    logger.warning(f"Failed to extract metadata for {temp_file.get('filename')}: {metadata_error}")
                    # Continue with empty metadata if extraction fails

                # Create photo record with archaeological metadata
                photo_record = await photo_metadata_service.create_photo_record(
                    filename=temp_file['filename'],
                    original_filename=temp_file['original_filename'],
                    file_path=permanent_path,
                    file_size=temp_file['file_size'],
                    site_id=str(site_id),
                    uploaded_by=str(user_id),
                    metadata=file_metadata,
                    archaeological_metadata=metadata
                )

                # Save to database
                # Import from centralized database engine
                from app.database.engine import AsyncSessionLocal as async_session_maker
                async with async_session_maker() as db:
                    db.add(photo_record)
                    await db.commit()
                    await db.refresh(photo_record)

                    # Generate thumbnail after database save
                    try:
                        async with aiofiles.open(permanent_path, 'rb') as f:
                            content = await f.read()
                            file_like = BytesIO(content)
                            file_like.filename = temp_file['original_filename']

                            thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                                file_like, str(photo_record.id)
                            )

                            if thumbnail_path:
                                photo_record.thumbnail_path = thumbnail_path
                                await db.commit()
                                logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
                            else:
                                logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")
                    except Exception as thumbnail_error:
                        logger.error(f"Thumbnail generation error for photo {photo_record.id}: {thumbnail_error}")
                        # Don't fail the upload if thumbnail generation fails

                uploaded_photos.append({
                    'photo_id': str(photo_record.id),
                    'filename': temp_file['filename'],
                    'original_filename': temp_file['original_filename'],
                    'file_size': temp_file['file_size'],
                    'file_path': permanent_path,
                    'metadata': {
                        'width': photo_record.width,
                        'height': photo_record.height,
                        'photo_date': photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                        'camera_model': photo_record.camera_model
                    },
                    'archaeological_metadata': {
                        'inventory_number': photo_record.inventory_number,
                        'excavation_area': photo_record.excavation_area,
                        'material': photo_record.material,
                        'chronology_period': photo_record.chronology_period,
                        'photo_type': photo_record.photo_type,
                        'photographer': photo_record.photographer,
                        'description': photo_record.description,
                        'keywords': photo_record.keywords
                    }
                })

                # Check if tiles are needed (larger files or high resolution)
                width = photo_record.width or 0
                height = photo_record.height or 0
                max_dimension = max(width, height)
                file_size_mb = temp_file['file_size'] / (1024 * 1024)

                if max_dimension > 2000 or file_size_mb > 5:  # Large images need tiles
                    photos_needing_tiles.append({
                        'photo_id': str(photo_record.id),
                        'file_path': permanent_path,
                        'width': width,
                        'height': height,
                        'archaeological_metadata': metadata
                    })

                logger.info(f"Bulk upload: Successfully processed photo {photo_record.id} ({temp_file['original_filename']})")

            except Exception as e:
                logger.error(f"Error processing queued bulk photo {temp_file.get('original_filename')}: {e}")
                failed_photos.append({
                    'filename': temp_file.get('original_filename', 'Unknown'),
                    'error': str(e)
                })
                continue

        # Schedule tile processing if needed
        if photos_needing_tiles:
            try:
                await deep_zoom_background_service.schedule_batch_processing(
                    photos_list=photos_needing_tiles,
                    site_id=str(site_id)
                )
                logger.info(f"Scheduled deep zoom processing for {len(photos_needing_tiles)} photos")
            except Exception as tile_error:
                logger.error(f"Failed to schedule tile processing: {tile_error}")
                # Don't fail entire bulk upload if tile scheduling fails

        # Log bulk upload activity
        try:
            # Import from centralized database engine
            from app.database.engine import AsyncSessionLocal as async_session_maker
            async with async_session_maker() as db:
                activity = UserActivity(
                    user_id=user_id,
                    site_id=site_id,
                    activity_type="BULK_UPLOAD",
                    activity_desc=f"Caricamento massivo di {len(uploaded_photos)} foto",
                    extra_data=json.dumps({
                        "bulk_operation": True,
                        "uploaded_count": len(uploaded_photos),
                        "failed_count": len(failed_photos),
                        "total_files": len(temp_files)
                    })
                )
                db.add(activity)
                await db.commit()
        except Exception as activity_error:
            logger.error(f"Failed to log bulk upload activity: {activity_error}")
            # Don't fail operation if activity logging fails

        # Prepare response
        response = {
            'status': 'completed',
            'message': f'Bulk upload processed: {len(uploaded_photos)} photos uploaded successfully',
            'uploaded_photos': uploaded_photos,
            'photos_needing_tiles': len(photos_needing_tiles),
            'processed_at': datetime.now().isoformat(),
            'total_files': len(temp_files),
            'successful_count': len(uploaded_photos),
            'failed_count': len(failed_photos)
        }

        # Include failed photos information if any
        if failed_photos:
            response['failed_photos'] = failed_photos

        logger.info(f"Bulk upload completed: {len(uploaded_photos)} successful, {len(failed_photos)} failed")
        return response

    except Exception as e:
        logger.error(f"Error processing queued bulk upload: {e}")
        raise Exception(f"Bulk upload processing failed: {str(e)}")