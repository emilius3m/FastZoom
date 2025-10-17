"""API endpoints per gestione schede ICCD - Standard Catalogazione Archeologica."""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.services.iccd_records import ICCDRecordService
from app.exceptions import BusinessLogicError


def get_iccd_record_service(db: AsyncSession = Depends(get_async_session)) -> ICCDRecordService:
    """Dependency to get ICCD record service instance."""
    return ICCDRecordService(db)


iccd_router = APIRouter(prefix="/api/iccd", tags=["iccd_records"])


# === GESTIONE SCHEDE ICCD ===

@iccd_router.get("/site/{site_id}/records")
async def get_site_iccd_records(
    site_id: UUID,
    schema_type: Optional[str] = Query(None, description="Filtro per tipo schemas (RA, CA, SI, etc.)"),
    level: Optional[str] = Query(None, description="Filtro per livello (P, C, A)"),
    status: Optional[str] = Query(None, description="Filtro per status (draft, submitted, approved, published)"),
    is_validated: Optional[bool] = Query(None, description="Filtro per validazione"),
    page: int = Query(1, ge=1, description="Numero pagina"),
    size: int = Query(20, ge=1, le=100, description="Elementi per pagina"),
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni tutte le schede ICCD di un sito."""
    try:
        result = await iccd_service.get_site_records(
            site_id, current_user_id, schema_type, level, status, is_validated, page, size
        )
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@iccd_router.post("/site/{site_id}/records")
async def create_iccd_record(
    site_id: UUID,
    record_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Crea una nuova scheda ICCD."""
    try:
        result = await iccd_service.create_record(site_id, record_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@iccd_router.get("/site/{site_id}/records/{record_id}")
async def get_iccd_record(
    site_id: UUID,
    record_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni dettagli di una scheda ICCD specifica."""
    try:
        result = await iccd_service.get_record_by_id(site_id, record_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@iccd_router.put("/site/{site_id}/records/{record_id}")
async def update_iccd_record(
    site_id: UUID,
    record_id: UUID,
    record_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Aggiorna una scheda ICCD esistente."""
    try:
        result = await iccd_service.update_record(site_id, record_id, record_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@iccd_router.delete("/site/{site_id}/records/{record_id}")
async def delete_iccd_record(
    site_id: UUID,
    record_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Elimina una scheda ICCD esistente."""
    try:
        result = await iccd_service.delete_record(site_id, record_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@iccd_router.post("/site/{site_id}/records/{record_id}/validate")
async def validate_iccd_record(
    site_id: UUID,
    record_id: UUID,
    validation_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Valida una scheda ICCD."""
    try:
        result = await iccd_service.validate_record(site_id, record_id, validation_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# === TEMPLATE SCHEMI ICCD ===

@iccd_router.get("/schema-templates")
async def get_iccd_schema_templates(
    schema_type: Optional[str] = Query(None, description="Filtro per tipo schemas"),
    category: Optional[str] = Query(None, description="Filtro per categoria"),
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni template schemi ICCD disponibili."""
    try:
        result = await iccd_service.get_schema_templates(current_user_id, schema_type, category)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@iccd_router.get("/schema-templates/{schema_type}")
async def get_iccd_schema_template(
    schema_type: str,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni template schemas ICCD specifico."""
    try:
        result = await iccd_service.get_schema_template_by_type(current_user_id, schema_type)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# === GENERAZIONE PDF ===

@iccd_router.get("/site/{site_id}/records/{record_id}/pdf")
async def generate_iccd_pdf(
    site_id: UUID,
    record_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Genera PDF della scheda ICCD conforme agli standard."""
    try:
        # Get record details to pass to PDF generation service
        record_data = await iccd_service.get_record_by_id(site_id, record_id, current_user_id)
        
        # We'll need to call the PDF generation service here
        from app.services.iccd_pdf_service import generate_iccd_pdf_quick
        from sqlalchemy import select
        from app.models.sites import ArchaeologicalSite
        
        # Get site name for PDF generation
        db = iccd_service.db_session
        site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        site_result = await db.execute(site_query)
        site = site_result.scalar_one_or_none()
        
        site_name = site.name if site else ""
        
        # Create a mock record object for the PDF service (since we have the data as dict)
        class MockRecord:
            def __init__(self, data):
                self.schema_type = data.get('schema_type', '')
                self.get_nct = lambda: data.get('nct', '')
                self.iccd_data = data.get('iccd_data', {})
        
        mock_record = MockRecord(record_data)
        pdf_content = generate_iccd_pdf_quick(mock_record, site_name)
        
        filename = f"ICCD_{record_data.get('schema_type', 'unknown')}_{record_data.get('nct', 'unknown')}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Errore generazione PDF")


# === STATISTICHE ICCD ===

@iccd_router.get("/site/{site_id}/statistics")
async def get_iccd_statistics(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni statistiche schede ICCD del sito."""
    try:
        result = await iccd_service.get_record_statistics(site_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# === VALIDAZIONE DATI ICCD ===

@iccd_router.post("/validate")
async def validate_iccd_data(
    validation_request: Dict[str, Any] = Body(...),
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Valida dati ICCD secondo standard ministeriali."""
    try:
        from loguru import logger

        logger.info(f"Validate request received: {validation_request}")

        schema_type = validation_request.get('schema_type')
        level = validation_request.get('level')
        iccd_data = validation_request.get('iccd_data')

        logger.info(f"Extracted fields - schema_type: {schema_type}, level: {level}, iccd_data present: {iccd_data is not None}")

        if not all([schema_type, level, iccd_data]):
            logger.error(f"Missing required fields: schema_type={schema_type}, level={level}, iccd_data={iccd_data is not None}")
            raise BusinessLogicError("schema_type, level e iccd_data sono obbligatori", 400)
        
        # Create validation service
        from app.services.iccd_validation_service import ICCDValidationService
        validation_service = ICCDValidationService(iccd_service.db_session)
        
        # Validate data
        is_valid, errors = await validation_service.validate_record(schema_type, level, iccd_data)
        
        return JSONResponse({
            "valid": is_valid,
            "errors": errors,
            "schema_type": schema_type,
            "level": level,
            "validation_timestamp": datetime.utcnow().isoformat()
        })
        
    except BusinessLogicError as e:
        logger.error(f"Business logic error in validation: {e.message}")
        return JSONResponse(
            status_code=400,
            content={
                "valid": False,
                "errors": [{"field_path": "general", "message": e.message, "value": None}],
                "schema_type": schema_type if 'schema_type' in locals() else None,
                "level": level if 'level' in locals() else None,
                "validation_timestamp": datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error in validation: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "errors": [{"field_path": "general", "message": f"Errore validazione: {str(e)}", "value": None}],
                "schema_type": schema_type if 'schema_type' in locals() else None,
                "level": level if 'level' in locals() else None,
                "validation_timestamp": datetime.utcnow().isoformat()
            }
        )


# === INTEGRAZIONE CON SISTEMA FASTZOOM ===

@iccd_router.post("/site/{site_id}/initialize")
async def initialize_iccd_for_site(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Inizializza sistema ICCD per un sito archeologico."""
    try:
        # Check site access
        from app.models.sites import ArchaeologicalSite
        from app.models import UserSitePermission
        from sqlalchemy import select, and_, or_, func
        
        site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        site_result = await iccd_service.db_session.execute(site_query)
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise BusinessLogicError("Sito archeologico non trovato", 404)
        
        # Check user permissions
        permission_query = select(UserSitePermission).where(
            and_(
                UserSitePermission.user_id == current_user_id,
                UserSitePermission.site_id == site_id,
                UserSitePermission.is_active == True,
                or_(
                    UserSitePermission.expires_at.is_(None),
                    UserSitePermission.expires_at > func.now()
                )
            )
        )
        
        permission = await iccd_service.db_session.execute(permission_query)
        permission = permission.scalar_one_or_none()
        
        if not permission or not permission.can_admin():
            raise BusinessLogicError("Permessi di amministratore richiesti", 403)
        
        from app.services.iccd_integration_service import ICCDIntegrationService, auto_setup_iccd_for_new_site
        
        # Auto setup ICCD
        setup_result = await auto_setup_iccd_for_new_site(site_id, current_user_id, iccd_service.db_session)
        
        if setup_result["success"]:
            return JSONResponse({
                "message": "Sistema ICCD inizializzato con successo",
                "site_id": str(site_id),
                "setup_result": setup_result,
                "iccd_enabled": setup_result["iccd_enabled"]
            })
        else:
            raise BusinessLogicError(
                f"Errore inizializzazione ICCD: {setup_result.get('errors', ['Unknown error'])}", 
                500
            )
            
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore inizializzazione: {str(e)}")


@iccd_router.get("/site/{site_id}/integration-status")
async def get_iccd_integration_status(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni status integrazione ICCD per un sito."""
    try:
        # Check site access
        from app.models.sites import ArchaeologicalSite
        from app.models import UserSitePermission
        from sqlalchemy import select, and_, or_, func
        
        site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        site_result = await iccd_service.db_session.execute(site_query)
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise BusinessLogicError("Sito archeologico non trovato", 404)
        
        # Check user permissions
        permission_query = select(UserSitePermission).where(
            and_(
                UserSitePermission.user_id == current_user_id,
                UserSitePermission.site_id == site_id,
                UserSitePermission.is_active == True,
                or_(
                    UserSitePermission.expires_at.is_(None),
                    UserSitePermission.expires_at > func.now()
                )
            )
        )
        
        permission = await iccd_service.db_session.execute(permission_query)
        permission = permission.scalar_one_or_none()
        
        if not permission or not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        from app.services.iccd_integration_service import ICCDIntegrationService
        
        service = ICCDIntegrationService(iccd_service.db_session)
        validation_result = await service.validate_iccd_integration(site_id)
        
        return validation_result
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore verifica integrazione: {str(e)}")


# === GESTIONE GERARCHIA ICCD ===

@iccd_router.get("/site/{site_id}/hierarchy/validation")
async def validate_hierarchy_integrity(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Valida l'integrità della gerarchia ICCD del sito."""
    try:
        # Check site access
        site, permission = await iccd_service.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        from app.services.iccd_hierarchy_service import ICCDHierarchyService
        hierarchy_service = ICCDHierarchyService(iccd_service.db_session)
        
        result = await hierarchy_service.validate_hierarchy_integrity(site_id)
        return result
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore validazione gerarchia: {str(e)}")


@iccd_router.get("/site/{site_id}/hierarchy/tree")
async def get_hierarchy_tree(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni l'albero gerarchico completo delle schede ICCD del sito."""
    try:
        # Check site access
        site, permission = await iccd_service.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        from app.services.iccd_hierarchy_service import ICCDHierarchyService
        hierarchy_service = ICCDHierarchyService(iccd_service.db_session)
        
        result = await hierarchy_service.get_hierarchy_tree(site_id)
        return result
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore costruzione albero gerarchia: {str(e)}")


@iccd_router.get("/site/{site_id}/hierarchy/creation-options")
async def get_creation_options(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni le opzioni disponibili per la creazione di nuove schede ICCD."""
    try:
        # Check site access
        site, permission = await iccd_service.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        from app.services.iccd_hierarchy_service import ICCDHierarchyService
        hierarchy_service = ICCDHierarchyService(iccd_service.db_session)
        
        result = await hierarchy_service.get_creation_options(site_id)
        return result
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore opzioni creazione: {str(e)}")


@iccd_router.get("/site/{site_id}/hierarchy/possible-parents/{schema_type}")
async def get_possible_parents(
    site_id: UUID,
    schema_type: str,
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Ottieni i possibili padri per un tipo di scheda ICCD."""
    try:
        # Check site access
        site, permission = await iccd_service.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        from app.services.iccd_hierarchy_service import ICCDHierarchyService
        hierarchy_service = ICCDHierarchyService(iccd_service.db_session)
        
        parents = await hierarchy_service.get_possible_parents(site_id, schema_type)
        
        return {
            "site_id": str(site_id),
            "schema_type": schema_type,
            "possible_parents": parents,
            "total": len(parents)
        }
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore ricerca padri: {str(e)}")


@iccd_router.post("/site/{site_id}/hierarchy/validate-creation")
async def validate_card_creation(
    site_id: UUID,
    creation_request: Dict[str, Any] = Body(...),
    current_user_id: UUID = Depends(get_current_user_id),
    iccd_service: ICCDRecordService = Depends(get_iccd_record_service)
):
    """Valida se è possibile creare una scheda ICCD secondo le regole gerarchiche."""
    try:
        # Check site access
        site, permission = await iccd_service.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        schema_type = creation_request.get('schema_type')
        parent_id_raw = creation_request.get('parent_id')
        
        if not schema_type:
            raise BusinessLogicError("schema_type è obbligatorio", 400)
        
        # Convert parent_id to UUID if it's a string
        parent_id = None
        if parent_id_raw:
            if isinstance(parent_id_raw, str):
                try:
                    parent_id = UUID(parent_id_raw)
                except ValueError:
                    raise BusinessLogicError("parent_id deve essere un UUID valido", 400)
            else:
                parent_id = parent_id_raw
        
        from app.services.iccd_hierarchy_service import ICCDHierarchyService
        hierarchy_service = ICCDHierarchyService(iccd_service.db_session)
        
        is_valid, error_message = await hierarchy_service.validate_card_creation(
            site_id, schema_type, parent_id
        )
        
        return {
            "site_id": str(site_id),
            "schema_type": schema_type,
            "parent_id": str(parent_id) if parent_id else None,
            "is_valid": is_valid,
            "error_message": error_message if not is_valid else None,
            "validation_timestamp": datetime.utcnow().isoformat()
        }
        
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore validazione creazione: {str(e)}")