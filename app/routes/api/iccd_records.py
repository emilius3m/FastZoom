"""API endpoints per gestione schede ICCD - Standard Catalogazione Archeologica."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.iccd_records import ICCDRecord, ICCDSchemaTemplate, ICCDValidationRule
from app.models.users import User

iccd_router = APIRouter(prefix="/api/iccd", tags=["iccd_records"])


async def get_site_access_for_iccd(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito per operazioni ICCD."""
    
    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")
    
    # Verifica permessi utente
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
    
    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )
    
    return site, permission


# === GESTIONE SCHEDE ICCD ===

@iccd_router.get("/sites/{site_id}/records")
async def get_site_iccd_records(
    site_id: UUID,
    schema_type: Optional[str] = Query(None, description="Filtro per tipo schema (RA, CA, SI, etc.)"),
    level: Optional[str] = Query(None, description="Filtro per livello (P, C, A)"),
    status: Optional[str] = Query(None, description="Filtro per status (draft, submitted, approved, published)"),
    is_validated: Optional[bool] = Query(None, description="Filtro per validazione"),
    page: int = Query(1, ge=1, description="Numero pagina"),
    size: int = Query(20, ge=1, le=100, description="Elementi per pagina"),
    site_access: tuple = Depends(get_site_access_for_iccd),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni tutte le schede ICCD di un sito."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Costruisci query con filtri
    query = select(ICCDRecord).options(
        joinedload(ICCDRecord.creator),
        joinedload(ICCDRecord.validator)
    ).where(ICCDRecord.site_id == site_id)
    
    # Applica filtri
    if schema_type:
        query = query.where(ICCDRecord.schema_type == schema_type)
    if level:
        query = query.where(ICCDRecord.level == level)
    if status:
        query = query.where(ICCDRecord.status == status)
    if is_validated is not None:
        query = query.where(ICCDRecord.is_validated == is_validated)
    
    # Conta totale
    count_query = select(func.count(ICCDRecord.id)).where(ICCDRecord.site_id == site_id)
    if schema_type:
        count_query = count_query.where(ICCDRecord.schema_type == schema_type)
    if level:
        count_query = count_query.where(ICCDRecord.level == level)
    if status:
        count_query = count_query.where(ICCDRecord.status == status)
    if is_validated is not None:
        count_query = count_query.where(ICCDRecord.is_validated == is_validated)
    
    total = await db.execute(count_query)
    total = total.scalar()
    
    # Applica paginazione e ordinamento
    query = query.order_by(desc(ICCDRecord.updated_at))
    query = query.offset((page - 1) * size).limit(size)
    
    records = await db.execute(query)
    records = records.scalars().all()
    
    # Prepara dati response
    records_data = []
    for record in records:
        record_dict = record.to_dict()
        # Aggiungi informazioni utente
        if record.creator:
            record_dict["creator_name"] = f"{record.creator.first_name} {record.creator.last_name}"
        if record.validator:
            record_dict["validator_name"] = f"{record.validator.first_name} {record.validator.last_name}"
        records_data.append(record_dict)
    
    return JSONResponse({
        "site_id": str(site_id),
        "records": records_data,
        "pagination": {
            "page": page,
            "size": size,
            "total": total,
            "pages": (total + size - 1) // size
        },
        "filters": {
            "schema_type": schema_type,
            "level": level,
            "status": status,
            "is_validated": is_validated
        }
    })


@iccd_router.post("/sites/{site_id}/records")
async def create_iccd_record(
    site_id: UUID,
    record_data: dict,
    site_access: tuple = Depends(get_site_access_for_iccd),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea una nuova scheda ICCD."""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Log dei dati ricevuti per debug
        logger.info(f"Creating ICCD record for site {site_id} by user {current_user_id}")
        logger.info(f"Record data keys: {list(record_data.keys())}")

        # Validazione dati base
        required_fields = ['schema_type', 'level', 'iccd_data', 'cataloging_institution']
        for field in required_fields:
            if field not in record_data:
                logger.error(f"Missing required field: {field}")
                raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")

        # Validazione aggiuntiva dei dati ICCD
        if not isinstance(record_data['iccd_data'], dict):
            raise HTTPException(status_code=400, detail="iccd_data deve essere un oggetto JSON")
        
        # Genera NCT se non fornito
        nct_data = record_data.get('iccd_data', {}).get('CD', {}).get('NCT', {})
        
        if not nct_data.get('NCTR'):
            nct_data['NCTR'] = '12'  # Default Lazio per Domus Flavia
        
        if not nct_data.get('NCTN'):
            # Genera numero progressivo basato su timestamp
            now = datetime.utcnow()
            year = now.year % 100  # Ultime 2 cifre dell'anno
            sequence = now.microsecond % 1000000  # Microseconds per unicità
            nct_data['NCTN'] = f"{year:02d}{sequence:06d}"
        
        # Verifica unicità NCT
        existing_query = select(ICCDRecord).where(
            and_(
                ICCDRecord.nct_region == nct_data['NCTR'],
                ICCDRecord.nct_number == nct_data['NCTN'],
                ICCDRecord.nct_suffix == nct_data.get('NCTS')
            )
        )
        existing = await db.execute(existing_query)
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Codice NCT già esistente")
        
        # Aggiorna i dati ICCD con NCT generato
        record_data['iccd_data']['CD']['NCT'] = nct_data
        
        # Crea record ICCD
        iccd_record = ICCDRecord(
            nct_region=nct_data['NCTR'],
            nct_number=nct_data['NCTN'],
            nct_suffix=nct_data.get('NCTS'),
            schema_type=record_data['schema_type'],
            level=record_data['level'],
            iccd_data=record_data['iccd_data'],
            cataloging_institution=record_data['cataloging_institution'],
            cataloger_name=record_data.get('cataloger_name'),
            survey_date=datetime.fromisoformat(record_data['survey_date']) if record_data.get('survey_date') else None,
            site_id=site_id,
            created_by=current_user_id
        )

        db.add(iccd_record)
        await db.flush()  # Flush per ottenere l'ID senza commit
        await db.refresh(iccd_record)

        # Verifica che il record sia stato creato correttamente
        if not iccd_record.id:
            raise HTTPException(status_code=500, detail="Errore creazione record nel database")

        await db.commit()
        
        logger.info(f"ICCD record created: {iccd_record.get_nct()} for site {site_id}")
        
        return JSONResponse({
            "message": "Scheda ICCD creata con successo",
            "record_id": str(iccd_record.id),
            "nct": iccd_record.get_nct(),
            "record": iccd_record.to_dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating ICCD record: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione scheda ICCD: {str(e)}")


@iccd_router.get("/sites/{site_id}/records/{record_id}")
async def get_iccd_record(
    site_id: UUID,
    record_id: UUID,
    site_access: tuple = Depends(get_site_access_for_iccd),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni dettagli di una scheda ICCD specifica."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query record con relazioni
    record_query = select(ICCDRecord).options(
        joinedload(ICCDRecord.creator),
        joinedload(ICCDRecord.validator)
    ).where(
        and_(
            ICCDRecord.id == record_id,
            ICCDRecord.site_id == site_id
        )
    )
    
    record = await db.execute(record_query)
    record = record.scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
    
    record_data = record.to_dict()
    
    # Aggiungi informazioni utente
    if record.creator:
        record_data["creator_name"] = f"{record.creator.first_name} {record.creator.last_name}"
    if record.validator:
        record_data["validator_name"] = f"{record.validator.first_name} {record.validator.last_name}"
    
    return JSONResponse(record_data)


@iccd_router.put("/sites/{site_id}/records/{record_id}")
async def update_iccd_record(
    site_id: UUID,
    record_id: UUID,
    record_data: dict,
    site_access: tuple = Depends(get_site_access_for_iccd),
    db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna una scheda ICCD esistente."""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    # Trova record
    record = await db.execute(
        select(ICCDRecord).where(
            and_(
                ICCDRecord.id == record_id,
                ICCDRecord.site_id == site_id
            )
        )
    )
    record = record.scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
    
    try:
        # Campi aggiornabili
        updatable_fields = [
            'level', 'iccd_data', 'cataloging_institution', 'cataloger_name',
            'survey_date', 'status', 'validation_notes'
        ]
        
        for field in updatable_fields:
            if field in record_data:
                value = record_data[field]
                
                # Gestione date
                if field == 'survey_date' and value:
                    if isinstance(value, str):
                        try:
                            value = datetime.fromisoformat(value)
                        except ValueError:
                            value = datetime.strptime(value, '%Y-%m-%d')
                
                setattr(record, field, value)
        
        record.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(record)
        
        return JSONResponse({
            "message": "Scheda ICCD aggiornata con successo",
            "record": record.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error updating ICCD record: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore aggiornamento scheda: {str(e)}")


@iccd_router.post("/sites/{site_id}/records/{record_id}/validate")
async def validate_iccd_record(
    site_id: UUID,
    record_id: UUID,
    validation_data: dict,
    site_access: tuple = Depends(get_site_access_for_iccd),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Valida una scheda ICCD."""
    site, permission = site_access
    
    if not permission.can_admin():  # Solo admin possono validare
        raise HTTPException(status_code=403, detail="Permessi di amministratore richiesti per validazione")
    
    # Trova record
    record = await db.execute(
        select(ICCDRecord).where(
            and_(
                ICCDRecord.id == record_id,
                ICCDRecord.site_id == site_id
            )
        )
    )
    record = record.scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
    
    try:
        # Verifica completezza per livello
        is_complete, missing_sections = record.is_complete_for_level()
        
        if not is_complete:
            raise HTTPException(
                status_code=400, 
                detail=f"Scheda incompleta per livello {record.level}. Sezioni mancanti: {', '.join(missing_sections)}"
            )
        
        # Aggiorna validazione
        record.is_validated = validation_data.get('is_valid', True)
        record.validation_date = datetime.utcnow()
        record.validated_by = current_user_id
        record.validation_notes = validation_data.get('notes')
        
        if record.is_validated:
            record.status = 'approved'
        
        await db.commit()
        await db.refresh(record)
        
        logger.info(f"ICCD record validated: {record.get_nct()} by user {current_user_id}")
        
        return JSONResponse({
            "message": "Scheda ICCD validata con successo",
            "record": record.to_dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating ICCD record: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore validazione scheda: {str(e)}")


# === TEMPLATE SCHEMI ICCD ===

@iccd_router.get("/schema-templates")
async def get_iccd_schema_templates(
    schema_type: Optional[str] = Query(None, description="Filtro per tipo schema"),
    category: Optional[str] = Query(None, description="Filtro per categoria"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni template schemi ICCD disponibili."""
    
    query = select(ICCDSchemaTemplate).where(ICCDSchemaTemplate.is_active == True)
    
    if schema_type:
        query = query.where(ICCDSchemaTemplate.schema_type == schema_type)
    if category:
        query = query.where(ICCDSchemaTemplate.category == category)
    
    query = query.order_by(ICCDSchemaTemplate.schema_type, ICCDSchemaTemplate.name)
    
    templates = await db.execute(query)
    templates = templates.scalars().all()
    
    templates_data = [template.to_dict() for template in templates]
    
    return JSONResponse({
        "templates": templates_data,
        "total": len(templates_data)
    })


@iccd_router.get("/schema-templates/{schema_type}")
async def get_iccd_schema_template(
    schema_type: str,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni template schema ICCD specifico."""
    
    template = await db.execute(
        select(ICCDSchemaTemplate).where(
            and_(
                ICCDSchemaTemplate.schema_type == schema_type,
                ICCDSchemaTemplate.is_active == True
            )
        )
    )
    template = template.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template schema ICCD non trovato")
    
    return JSONResponse(template.to_dict())


# === GENERAZIONE PDF ===

@iccd_router.get("/sites/{site_id}/records/{record_id}/pdf")
async def generate_iccd_pdf(
    site_id: UUID,
    record_id: UUID,
    site_access: tuple = Depends(get_site_access_for_iccd),
    db: AsyncSession = Depends(get_async_session)
):
    """Genera PDF della scheda ICCD conforme agli standard."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Trova record
    record = await db.execute(
        select(ICCDRecord).options(
            joinedload(ICCDRecord.creator),
            joinedload(ICCDRecord.site)
        ).where(
            and_(
                ICCDRecord.id == record_id,
                ICCDRecord.site_id == site_id
            )
        )
    )
    record = record.scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
    
    try:
        # Genera PDF usando il servizio ICCD
        from app.services.iccd_pdf_service import generate_iccd_pdf_quick
        
        pdf_content = generate_iccd_pdf_quick(record, record.site.name if record.site else "")
        
        filename = f"ICCD_{record.schema_type}_{record.get_nct()}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error generating ICCD PDF: {e}")
        raise HTTPException(status_code=500, detail="Errore generazione PDF")


# === STATISTICHE ICCD ===

@iccd_router.get("/sites/{site_id}/statistics")
async def get_iccd_statistics(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_iccd),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni statistiche schede ICCD del sito."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Statistiche base
    total_records = await db.execute(
        select(func.count(ICCDRecord.id)).where(ICCDRecord.site_id == site_id)
    )
    total_records = total_records.scalar()
    
    # Per tipo schema
    by_schema = await db.execute(
        select(ICCDRecord.schema_type, func.count(ICCDRecord.id))
        .where(ICCDRecord.site_id == site_id)
        .group_by(ICCDRecord.schema_type)
    )
    by_schema = {row[0]: row[1] for row in by_schema.fetchall()}
    
    # Per livello
    by_level = await db.execute(
        select(ICCDRecord.level, func.count(ICCDRecord.id))
        .where(ICCDRecord.site_id == site_id)
        .group_by(ICCDRecord.level)
    )
    by_level = {row[0]: row[1] for row in by_level.fetchall()}
    
    # Per status
    by_status = await db.execute(
        select(ICCDRecord.status, func.count(ICCDRecord.id))
        .where(ICCDRecord.site_id == site_id)
        .group_by(ICCDRecord.status)
    )
    by_status = {row[0]: row[1] for row in by_status.fetchall()}
    
    # Validate
    validated_count = await db.execute(
        select(func.count(ICCDRecord.id))
        .where(and_(ICCDRecord.site_id == site_id, ICCDRecord.is_validated == True))
    )
    validated_count = validated_count.scalar()
    
    return JSONResponse({
        "site_id": str(site_id),
        "statistics": {
            "total_records": total_records,
            "validated_records": validated_count,
            "validation_percentage": round((validated_count / total_records * 100) if total_records > 0 else 0, 2),
            "by_schema_type": by_schema,
            "by_level": by_level,
            "by_status": by_status
        }
    })


# === VALIDAZIONE DATI ICCD ===

@iccd_router.post("/validate")
async def validate_iccd_data(
    validation_request: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Valida dati ICCD secondo standard ministeriali."""
    
    try:
        schema_type = validation_request.get('schema_type')
        level = validation_request.get('level')
        iccd_data = validation_request.get('iccd_data')
        
        if not all([schema_type, level, iccd_data]):
            raise HTTPException(status_code=400, detail="schema_type, level e iccd_data sono obbligatori")
        
        # Crea servizio validazione
        from app.services.iccd_validation_service import ICCDValidationService
        validation_service = ICCDValidationService(db)
        
        # Valida dati
        is_valid, errors = await validation_service.validate_record(schema_type, level, iccd_data)
        
        return JSONResponse({
            "valid": is_valid,
            "errors": errors,
            "schema_type": schema_type,
            "level": level,
            "validation_timestamp": datetime.utcnow().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating ICCD data: {e}")
        raise HTTPException(status_code=500, detail=f"Errore validazione: {str(e)}")


# === INTEGRAZIONE CON SISTEMA FASTZOOM ===

@iccd_router.post("/sites/{site_id}/initialize")
async def initialize_iccd_for_site(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_iccd),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Inizializza sistema ICCD per un sito archeologico."""
    site, permission = site_access
    
    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Permessi di amministratore richiesti")
    
    try:
        from app.services.iccd_integration_service import ICCDIntegrationService, auto_setup_iccd_for_new_site
        
        # Configurazione automatica ICCD
        setup_result = await auto_setup_iccd_for_new_site(site_id, current_user_id, db)
        
        if setup_result["success"]:
            logger.info(f"ICCD system initialized for site {site_id}")
            return JSONResponse({
                "message": "Sistema ICCD inizializzato con successo",
                "site_id": str(site_id),
                "setup_result": setup_result,
                "iccd_enabled": setup_result["iccd_enabled"]
            })
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Errore inizializzazione ICCD: {setup_result.get('errors', ['Unknown error'])}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing ICCD for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore inizializzazione: {str(e)}")


@iccd_router.get("/sites/{site_id}/integration-status")
async def get_iccd_integration_status(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_iccd),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni status integrazione ICCD per un sito."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    try:
        from app.services.iccd_integration_service import ICCDIntegrationService
        
        service = ICCDIntegrationService(db)
        validation_result = await service.validate_iccd_integration(site_id)
        
        return JSONResponse(validation_result)
        
    except Exception as e:
        logger.error(f"Error getting ICCD integration status: {e}")
        raise HTTPException(status_code=500, detail=f"Errore verifica integrazione: {str(e)}")