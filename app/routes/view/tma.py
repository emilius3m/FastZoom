from typing import List, Dict, Any, Tuple
from uuid import UUID

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_sites_with_blacklist
from app.database.session import get_async_session
from app.routes.view.view_dependencies import get_site_read_access
from app.services.view_helpers import get_base_template_context
from app.templates import templates


tma_view_router = APIRouter(prefix="/view", tags=["tma"])


@tma_view_router.get("/{site_id}/tma", response_class=HTMLResponse)
async def tma_view(
    request: Request,
    site_id: UUID,
    site_access: Tuple = Depends(get_site_read_access),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session),
):
    site, permission, current_user, is_superuser = site_access

    context = await get_base_template_context(
        request, current_user.id, user_sites, db, site, permission, "tma"
    )
    context.update({
        "site_id": str(site_id),
        "user_role": permission.permission_level if hasattr(permission, "permission_level") else ("admin" if is_superuser else "none"),
        "is_superuser": is_superuser,
    })

    return templates.TemplateResponse("pages/tma/index.html", context)

