# importing the required modules
import json
import uuid
from datetime import datetime

import nh3
from loguru import logger
from fastapi import Depends, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.routing import APIRouter
from fastapi_csrf_protect import CsrfProtect

from app.database.db import CurrentAsyncSession
from app.database.security import current_active_user
from app.models.users import Role as RoleModelDB
from app.models.users import User as UserModelDB
from app.models.user_profiles import UserProfile as UserProfileModelDB
from app.routes.view.errors import handle_error
from app.routes.view.view_crud import SQLAlchemyCRUD
from app.schema.users import ProfileUpdate

# from app.schema.users import RoleCreate
from app.templates import templates
from app.core.security import get_current_user_sites_with_blacklist

# Create an APIRouter
user_view_route = APIRouter()


user_crud = SQLAlchemyCRUD[UserModelDB](
    UserModelDB, related_models={RoleModelDB: "role", UserProfileModelDB: "profile"}
)
user_profile_crud = SQLAlchemyCRUD[UserProfileModelDB](UserProfileModelDB)

role_crud = SQLAlchemyCRUD[RoleModelDB](RoleModelDB)


@user_view_route.get("/user", response_class=HTMLResponse)
async def get_users(
    request: Request,
    db: CurrentAsyncSession,
    skip: int = 0,
    limit: int = 100,
    current_user: UserModelDB = Depends(current_active_user),
    csrf_protect: CsrfProtect = Depends(),
):
    """
    Route handler function to get the create user page.

    Args:
        request (Request): The request object.
        current_user (UserModelDB): The current user object obtained from the current_active_user dependency.

    Returns:
        TemplateResponse: The HTML response containing the "partials/add_user.html" template.

    Raises:
        HTTPException: If the current user is not a superuser, with a 403 Forbidden status code.
    """
    try:
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=403, detail="Not authorized to view this page"
            )
        # Access the cookies using the Request object

        token = request.cookies.get("fastapiusersauth")
        users = await user_crud.read_all(db, skip, limit, join_relationships=True)

        csrf_token, signed_token = csrf_protect.generate_csrf_tokens()

        response = templates.TemplateResponse(
            "pages/user.html",
            {
                "request": request,
                "users": users,
                "token": token,
                "csrf_token": csrf_token,
                "user_type": current_user.is_superuser,
            },
        )

        csrf_protect.set_csrf_cookie(signed_token, response)

        return response
    except Exception as e:
        token = request.cookies.get("fastapiusersauth")
        csrf_token = request.headers.get("X-CSRF-Token")
        return handle_error(
            "pages/user.html",
            {
                "request": request,
                "csrf_token": csrf_token,
                "token": token,
                "user_type": current_user.is_superuser,
            },
            e,
        )


@user_view_route.get("/profile/", response_class=HTMLResponse)
async def profile_view(
    request: Request,
    db: CurrentAsyncSession,
    current_user: UserModelDB = Depends(current_active_user),
):
    """
    Route handler for user profile modal partial.
    Returns partial HTML for HTMX integration in dashboard.
    """
    try:
        # Get user sites (adapt to project security)
        from app.core.security import get_current_user_sites_with_blacklist
        user_sites = await get_current_user_sites_with_blacklist(request, db)
        
        # Get user profile if exists
        user_profile = current_user.profile if current_user.profile else None
        
        context = {
            "request": request,
            "current_user": current_user,
            "user_profile": user_profile,
            "user_sites": user_sites,
            "sites_count": len(user_sites),
            "csrf_token": request.headers.get("X-CSRF-Token", ""),
            "current_page": "profile"
        }
        
        return templates.TemplateResponse("partials/profile_modal.html", context)
        
    except Exception as e:
        return HTMLResponse(content=f"<div class='alert alert-danger'>Error loading profile: {str(e)}</div>", status_code=500)


