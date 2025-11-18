# app/routes/view_redirect.py - Route per gestire reindirizzamenti da URL con prefisso /view/

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from uuid import UUID
from loguru import logger

router = APIRouter(prefix="/view", tags=["View Redirects"])



# @router.get("/{site_id}/giornale", response_class=RedirectResponse)
# async def view_site_giornale_redirect(site_id: UUID):
#     """
#     Reindirizza dalla vecchia URL /view/{site_id}/giornale
#     alla nuova URL corretta /giornale-cantiere/site/{site_id}
#     """
#     logger.info(f"Redirecting from /view/{site_id}/giornale to /giornale-cantiere/site/{site_id}")
#     return RedirectResponse(
#         url=f"/giornale-cantiere/site/{site_id}",
#         status_code=302
#     )
#
# @router.get("/{site_id}/iccd", response_class=RedirectResponse)
# async def view_site_iccd_redirect(site_id: UUID):
#     """
#     Reindirizza dalla vecchia URL /view/{site_id}/iccd
#     alla nuova URL corretta /iccd?site={site_id}
#     """
#     logger.info(f"Redirecting from /view/{site_id}/iccd to /iccd?site={site_id}")
#     return RedirectResponse(
#         url=f"/iccd?site={site_id}",
#         status_code=302
#     )
#
#
#
# @router.get("/{site_id}/geographic-map", response_class=RedirectResponse)
# async def view_site_geographic_map_redirect(site_id: UUID):
#     """
#     Reindirizza dalla vecchia URL /view/{site_id}/geographic-map
#     alla nuova URL corretta /geographic-map?site={site_id}
#     """
#     logger.info(f"Redirecting from /view/{site_id}/geographic-map to /geographic-map?site={site_id}")
#     return RedirectResponse(
#         url=f"/geographic-map?site={site_id}",
#         status_code=302
#     )

