# Photo Upload SQLite Fixes Summary

This document summarizes the SQLite-specific fixes identified for the photo upload service to improve compatibility with SQLite databases.

## Key Issues Identified

1. **Transaction Handling**: SQLite has specific requirements for transaction management that differ from other databases.

2. **Refresh Inside Transactions**: Using `await task_db.refresh(photo_record)` inside transactions can cause issues with SQLite.

3. **Nested Transactions**: SQLite doesn't handle nested transactions well, which can lead to locking issues.

4. **Error Handling**: Enhanced error logging with stack traces is critical for debugging SQLite-specific issues.

## Proposed Fixes

### 1. SQLite-Aware Transaction Handling

```python
# Instead of always using async with task_db.begin():
# Check if there's already an active transaction
if task_db.in_transaction():
    logger.debug("Using existing transaction")
    # Use the existing transaction
    task_db.add(photo_record)
    await task_db.flush()
    # CRITICAL FIX: Don't use refresh inside transaction with SQLite
    photo_id = photo_record.id
    logger.debug(f"Photo flushed in existing transaction: {photo_id}")
else:
    # Create new transaction only if necessary
    logger.debug("Creating new transaction")
    async with task_db.begin():
        task_db.add(photo_record)
        await task_db.flush()
        photo_id = photo_record.id
        logger.debug(f"Photo flushed in new transaction: {photo_id}")
```

### 2. Separate Commits for Different Operations

```python
# Generate thumbnail (outside main transaction)
try:
    await file.seek(0)
    thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
        file, str(photo_record.id)
    )
    
    if thumbnail_path:
        photo_record.thumbnail_path = thumbnail_path
        # Separate commit for thumbnail
        try:
            await task_db.commit()
            logger.debug(f"Thumbnail path updated: {thumbnail_path}")
        except Exception as commit_error:
            logger.error(
                "Thumbnail commit failed",
                photo_id=str(photo_record.id),
                error=str(commit_error),
                exc_info=True
            )
            # Don't fail for thumbnail
except Exception as thumbnail_error:
    logger.error(
        "Thumbnail generation error",
        photo_id=str(photo_record.id),
        error=str(thumbnail_error),
        exc_info=True
    )
    # Don't fail upload for thumbnail

# Log activity in separate transaction
try:
    activity = UserActivity(
        user_id=str(user_id),
        site_id=str(site_id),
        activity_type="UPLOAD",
        activity_desc=f"Caricata foto: {file.filename}",
        extra_data=json.dumps({
            "photo_id": str(photo_record.id),
            "filename": filename,
            "file_size": file_size
        })
    )
    task_db.add(activity)
    await task_db.commit()  # Explicit commit for activity
    logger.debug(f"Activity logged for photo {photo_record.id}")
except Exception as activity_error:
    logger.error(
        "Activity logging failed",
        photo_id=str(photo_record.id),
        error=str(activity_error),
        exc_info=True
    )
    # Don't fail upload for activity log
```

### 3. Enhanced Error Handling with Stack Traces

```python
except Exception as photo_error:
    # CRITICAL FIX: Complete log with stack trace
    import traceback
    error_details = traceback.format_exc()
    
    logger.error(
        "Unexpected error processing photo",
        error=str(photo_error),
        error_type=type(photo_error).__name__,
        filename=file.filename if file else "Unknown",
        site_id=str(site_id),
        user_id=str(user_id),
        file_path=file_path if file_path else "Unknown",
        file_size=file_size if 'file_size' in locals() else "Unknown",
        exc_info=True  # CRITICAL: Shows full stack trace
    )
    
    # Separate log for complete traceback
    logger.error(
        "Full traceback for debugging",
        traceback=error_details
    )
    
    # Explicit rollback for SQLite
    if task_db.in_transaction():
        try:
            await task_db.rollback()
            logger.debug("Transaction rolled back")
        except Exception as rollback_error:
            logger.error(
                "Rollback failed",
                error=str(rollback_error),
                exc_info=True
            )
    
    # Clean up file if it exists
    if file_path:
        try:
            await storage_service.delete_file(file_path)
            logger.info(f"Cleaned up file: {file_path}")
        except Exception as cleanup_error:
            logger.error(
                "File cleanup failed",
                file_path=file_path,
                error=str(cleanup_error),
                exc_info=True
            )
    
    # Return None to indicate failure but don't crash entire batch
    return None
```

### 4. Data Access Before Method Exit

```python
# Access all necessary data BEFORE exiting the method
# to avoid lazy loading issues with SQLite
return {
    "photo_id": str(photo_record.id),
    "filename": filename,
    "file_size": file_size,
    "file_path": file_path,
    "metadata": {
        "width": photo_record.width,
        "height": photo_record.height,
        "photo_date": photo_record.photo_date.isoformat() if photo_record.photo_date else None,
        "camera_model": photo_record.camera_model
    },
    "archaeological_metadata": {
        'inventory_number': photo_record.inventory_number,
        'excavation_area': photo_record.excavation_area,
        'material': photo_record.material,
        'chronology_period': photo_record.chronology_period,
        'photo_type': photo_record.photo_type,
        'photographer': photo_record.photographer,
        'description': photo_record.description,
        'keywords': photo_record.keywords
    }
}
```

## Benefits of These Fixes

1. **Better SQLite Compatibility**: Avoids nested transactions and refresh issues
2. **Improved Error Handling**: Comprehensive logging with stack traces for debugging
3. **Data Integrity**: Proper transaction management ensures data consistency
4. **Graceful Failure Handling**: Individual photo failures don't crash entire batch
5. **Resource Cleanup**: Proper file cleanup on errors

## Implementation Notes

- These fixes are specifically designed for SQLite databases
- The transaction handling approach checks for existing transactions to avoid nesting
- Error logging includes comprehensive context and stack traces
- Separate commits for different operations reduce transaction scope
- Data access patterns avoid lazy loading issues with SQLite

## Testing Recommendations

1. Test with concurrent uploads to verify transaction handling
2. Test error scenarios to ensure proper cleanup and rollback
3. Verify thumbnail generation doesn't affect main transaction
4. Test activity logging independence from main photo transaction
5. Verify error logs contain sufficient detail for debugging