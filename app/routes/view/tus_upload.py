"""
TUS Upload View Routes
Web interface for TUS resumable uploads
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from loguru import logger

from app.core.security import get_current_user_id_with_blacklist
from app.database.db import get_async_session
from app.templates import templates


router = APIRouter()


@router.get("/tus-upload", response_class=HTMLResponse)
async def tus_upload_view(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    TUS Upload interface page
    """
    try:
        # Get user info for template
        from sqlalchemy import select
        from app.models.users import User
        
        user_result = await db.execute(select(User).where(User.id == str(current_user_id)))
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        context = {
            "request": request,
            "title": "TUS Upload | FastZoom",
            "user": user,
            "current_page": "tus_upload"
        }
        
        return templates.TemplateResponse("pages/tus_upload.html", context)
        
    except Exception as e:
        logger.error(f"Error rendering TUS upload page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")