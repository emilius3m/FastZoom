# Photo Upload SQLite Error Fixes

## Problem Analysis

The photo upload service is experiencing a silent error after creating the Photo record. The logs show "Photo record created successfully" but then immediately "Unexpected error processing photo" without proper stack trace details.

## Critical Issues Identified

### 1. **SQLite Transaction Issue (Line 297)**
```python
# PROBLEMATIC CODE
async with task_db.begin():
    task_db.add(photo_record)
    await task_db.flush()
    await task_db.refresh(photo_record)  # ❌ This causes SQLite issues
```

**Root Cause**: SQLite has specific transaction behavior that makes `refresh()` unreliable inside transactions, especially with async operations.

### 2. **Missing Stack Trace in Error Logging (Lines 373-379)**
```python
# PROBLEMATIC CODE
except Exception as photo_error:
    logger.error("Unexpected error processing photo", error=str(photo_error))
    # ❌ Missing exc_info=True
```

**Root Cause**: Without `exc_info=True`, the actual error details are not logged, making debugging impossible.

## Required Fixes

### Fix 1: SQLite-Compatible Transaction Handling

Replace the problematic transaction block:

```python
# ✅ FIXED: SQLite-compatible transaction handling
try:
    # Check if there's already an active transaction
    if task_db.in_transaction():
        logger.debug("Using existing transaction")
        # Use the existing transaction
        task_db.add(photo_record)
        await task_db.flush()
        # ✅ CRITICAL FIX: Don't use refresh inside transaction with SQLite
        photo_id = photo_record.id
        logger.debug(f"✅ Photo flushed in existing transaction: {photo_id}")
    else:
        # Create new transaction only if necessary
        logger.debug("Creating new transaction")
        async with task_db.begin():
            task_db.add(photo_record)
            await task_db.flush()
            photo_id = photo_record.id
            logger.debug(f"✅ Photo flushed in new transaction: {photo_id}")
    
    # ✅ FIX: Don't use refresh() - data is accessible after flush()
    
except Exception as db_error:
    logger.error(
        "Database operation failed",
        error=str(db_error),
        error_type=type(db_error).__name__,
        photo_id=photo_record.id if photo_record else "unknown",
        exc_info=True  # ✅ CRITICAL: Added stack trace
    )
    raise

# 5. Generate thumbnail (outside main transaction)
try:
    await file.seek(0)
    thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
        file, str(photo_record.id)
    )
    
    if thumbnail_path:
        photo_record.thumbnail_path = thumbnail_path
        # ✅ FIX: Separate update for thumbnail
        try:
            await task_db.commit()
            logger.debug(f"✅ Thumbnail path updated: {thumbnail_path}")
        except Exception as commit_error:
            logger.error(
                "Thumbnail commit failed",
                photo_id=str(photo_record.id),
                error=str(commit_error),
                exc_info=True
            )
            # Don't fail upload for thumbnail
    else:
        logger.warning(f"Thumbnail generation failed for {photo_record.id}")
        
except Exception as thumbnail_error:
    logger.error(
        "Thumbnail generation error",
        photo_id=str(photo_record.id),
        error=str(thumbnail_error),
        exc_info=True
    )
    # Don't fail upload for thumbnail

# 6. Log activity in separate transaction
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
    await task_db.commit()  # ✅ Explicit commit for activity
    logger.debug(f"✅ Activity logged for photo {photo_record.id}")
    
except Exception as activity_error:
    logger.error(
        "Activity logging failed",
        photo_id=str(photo_record.id),
        error=str(activity_error),
        exc_info=True
    )
    # Don't fail upload for activity log
```

### Fix 2: Complete Error Logging with Stack Traces

Replace the problematic error handling:

```python
# ✅ FIXED: Complete logging with stack trace
except Exception as photo_error:
    # ✅ CRITICAL FIX: Complete logging with stack trace
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
        exc_info=True  # ✅ CRITICAL - shows complete stack trace
    )
    
    # Separate log for full traceback
    logger.error(
        "Full traceback for debugging",
        traceback=error_details
    )
    
    # Rollback for SQLite
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
            logger.info(f"✅ Cleaned up file: {file_path}")
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

## Why These Fixes Work

### SQLite Transaction Compatibility
1. **Refresh Issue**: SQLite's transaction isolation makes `refresh()` unreliable inside async transactions
2. **Transaction State**: The code now checks `task_db.in_transaction()` to avoid nested transactions
3. **Data Access**: Photo record data is accessible after `flush()` without needing `refresh()`

### Improved Error Handling
1. **Stack Traces**: `exc_info=True` provides complete error details for debugging
2. **Transaction Safety**: Proper rollback handling prevents database corruption
3. **Resource Cleanup**: File cleanup on error prevents orphaned files

### Separated Operations
1. **Thumbnail Generation**: Moved outside main transaction to prevent failures from affecting photo creation
2. **Activity Logging**: Separate transaction ensures photo creation isn't blocked by logging failures

## Implementation Steps

1. **Replace lines 292-328** with the SQLite-compatible transaction handling
2. **Replace lines 391-397** with the complete error handling block
3. **Test** with a photo upload to verify stack traces now appear in logs
4. **Monitor** for any remaining SQLite transaction issues

## Expected Results

After implementing these fixes:
- ✅ Photo records will be created successfully without silent failures
- ✅ Complete error details will be logged for debugging
- ✅ SQLite transactions will handle correctly
- ✅ Thumbnail generation failures won't affect photo creation
- ✅ Activity logging won't block the upload process

## Additional Notes

- The fixes maintain backward compatibility
- No changes to API responses are required
- Error handling is more granular and debuggable
- Transaction boundaries are clearer and more reliable