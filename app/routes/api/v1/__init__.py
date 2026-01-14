"""
API v1 - Riorganizzazione del Sistema Archeologico Multi-Sito
Struttura RESTful con domini funzionali chiari e backward compatibility.
"""

from fastapi import APIRouter
from app.routes.api.v1.auth import router as auth_router
# Enable sites and photos routers for v1 API
from app.routes.api.v1.sites import router as sites_router
from app.routes.api.v1.photos import router as photos_router  # Now includes consolidated photo endpoints
# Temporarily comment out problematic routers to resolve import issues
# from app.routes.api.v1.metadata import router as metadata_router
# Temporarily comment out deepzoom router due to syntax issues
from app.routes.api.v1.deepzoom import router as deepzoom_router
from app.routes.api.v1.documents import router as documents_router
# from app.routes.api.v1.iccd import router as iccd_router
from app.routes.api.v1.us import router as us_router
from app.routes.api.v1.geographic import router as geographic_router
# from app.routes.api.v1.archaeological import router as archaeological_router
from app.routes.api.v1.giornale import router as giornale_router
from app.routes.api.v1.cantieri import router as cantieri_router
from app.routes.api.v1.teams import router as teams_router
# from app.routes.api.v1.storage import router as storage_router
# from app.routes.api.v1.monitoring import router as monitoring_router
from app.routes.api.v1.admin import router as admin_router
from app.routes.api.v1.unified import router as unified_router
from app.routes.api.v1.us_files import router as us_files_router
from app.routes.api.v1.harris_matrix import router as harris_matrix_router
from app.routes.api.v1.harris_matrix_mapping import router as harris_matrix_mapping_router
from app.routes.api.v1.ocr_us_import import router as ocr_us_import_router
from app.routes.api.v1.ocr_debug import router as ocr_debug_router
from app.routes.api.v1.tus_uploads import router as tus_uploads_router

# Migrated from v0
from app.routes.api.us_word_export_api import router as us_word_export_router
from app.routes.api.database_monitoring import router as database_monitoring_router
from app.routes.api.archeologia_avanzata import router as archeologia_avanzata_router

# Router principale API v1
api_v1_router = APIRouter(
    prefix="/api/v1",
    tags=["API v1"],
    responses={404: {"description": "Not found"}}
)

# Includi tutti i domini funzionali
# Include only working routers for now
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
# Enable sites and photos routers for v1 API
api_v1_router.include_router(sites_router, tags=["Sites"])
api_v1_router.include_router(photos_router, tags=["Photos"])
# Temporarily comment out problematic routers
# api_v1_router.include_router(metadata_router, prefix="/metadata", tags=["Photo Metadata"])
api_v1_router.include_router(deepzoom_router, prefix="/deepzoom", tags=["Deep Zoom"])
api_v1_router.include_router(documents_router, tags=["Documents"])
# api_v1_router.include_router(iccd_router, prefix="/iccd", tags=["ICCD Cataloging"])
api_v1_router.include_router(us_router, prefix="/us", tags=["US/USM Units"])
api_v1_router.include_router(us_files_router, prefix="/us-files", tags=["US/USM Files"])
api_v1_router.include_router(harris_matrix_router, prefix="/harris-matrix", tags=["Harris Matrix"])
api_v1_router.include_router(harris_matrix_mapping_router, prefix="/harris-matrix", tags=["Harris Matrix Mapping"])
api_v1_router.include_router(geographic_router, prefix="/geographic", tags=["Geographic Maps"])
# api_v1_router.include_router(archaeological_router, prefix="/archaeological", tags=["Archaeological Plans"])
api_v1_router.include_router(giornale_router, prefix="/giornale", tags=["Giornale di Cantiere"])
api_v1_router.include_router(cantieri_router, prefix="/cantieri", tags=["Cantieri"])
api_v1_router.include_router(teams_router, prefix="/teams", tags=["Team Management"])
# api_v1_router.include_router(storage_router, prefix="/storage", tags=["Storage"])
# api_v1_router.include_router(monitoring_router, prefix="/monitoring", tags=["System Monitoring"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Administration"])
api_v1_router.include_router(unified_router, prefix="/unified", tags=["Unified Dashboard"])
api_v1_router.include_router(ocr_us_import_router, prefix="/ocr", tags=["OCR US Import"])
api_v1_router.include_router(ocr_debug_router, tags=["OCR Debug"])
api_v1_router.include_router(tus_uploads_router, tags=["TUS Uploads"])

# Moved routers from V0
from app.routes.api.v1.form_schemas import form_schemas_router
from app.routes.api.v1.form_data import router as form_data_router
from app.routes.api.v1.archaeological_plans import plans_router
from app.routes.api.v1.iccd_records import iccd_router

api_v1_router.include_router(form_schemas_router)
api_v1_router.include_router(form_data_router)
api_v1_router.include_router(plans_router)
api_v1_router.include_router(iccd_router)

# Migrated from v0
api_v1_router.include_router(us_word_export_router, prefix="/us-export", tags=["US Word Export"])
api_v1_router.include_router(database_monitoring_router, prefix="/database", tags=["Database Monitoring"])
api_v1_router.include_router(archeologia_avanzata_router, prefix="/archeologia", tags=["Archeologia Avanzata"])

# Esporta il router principale
__all__ = ["api_v1_router"]