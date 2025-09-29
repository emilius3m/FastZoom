"""API endpoints per Sistema Gerarchico ICCD - Gestione Completa Hierarchica."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, text, func
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
from app.models.iccd_records import ICCDBaseRecord, ICCDRelation, ICCDAuthorityFile
from app.models.users import User

iccd_hierarchy_router = APIRouter(prefix="/api/iccd", tags=["iccd_hierarchy"])


async def get_site_access_for_iccd_hierarchy(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito per operazioni ICCD gerarchiche."""
    
    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site_result = await db.execute(site_query)
    site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")
    
    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == current_user_id,
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        )
    )
    
    permission_result = await db.execute(permission_query)
    permission = permission_result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )
    
    return site, permission


@iccd_hierarchy_router.get("/hierarchy")
async def get_iccd_hierarchy(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_iccd_hierarchy),
    db: AsyncSession = Depends(get_async_session)
):
    """Recupera gerarchia completa ICCD per sito."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query gerarchica per tutti i tipi di scheda
    hierarchy_query = """
    WITH RECURSIVE hierarchy AS (
        -- Radice: Schede SI (sito)
        SELECT 
            r.id, r.schema_type, r.nct_region, r.nct_number, r.nct_suffix,
            r.iccd_data, r.parent_id, r.site_id, 0 as level,
            ARRAY[r.id] as path
        FROM iccd_base_records r 
        WHERE r.site_id = :site_id AND r.schema_type = 'SI'
        
        UNION ALL
        
        -- Ricorsiva: tutti i figli
        SELECT 
            r.id, r.schema_type, r.nct_region, r.nct_number, r.nct_suffix,
            r.iccd_data, r.parent_id, r.site_id, h.level + 1,
            h.path || r.id
        FROM iccd_base_records r
        INNER JOIN hierarchy h ON r.parent_id = h.id
        WHERE r.site_id = :site_id
    )
    SELECT * FROM hierarchy ORDER BY level, schema_type, nct_number;
    """
    
    result = await db.execute(text(hierarchy_query), {"site_id": site_id})
    records = result.fetchall()
    
    # Organizza per livelli ICCD
    organized = {
        "site": None,
        "complexes": [],
        "monuments": [],
        "stratigraphic_surveys": [],
        "artifacts": [],
        "numismatics": [],
        "material_tables": [],
        "anthropology": []
    }
    
    for record in records:
        record_data = {
            "id": record.id,
            "schema_type": record.schema_type,
            "nct_region": record.nct_region,
            "nct_number": record.nct_number,
            "nct_suffix": record.nct_suffix,
            "iccd_data": record.iccd_data,
            "level": record.level,
            "nct": f"{record.nct_region}{record.nct_number}{record.nct_suffix or ''}"
        }
        
        # Assegna alla categoria corretta
        if record.schema_type == 'SI':
            organized["site"] = record_data
        elif record.schema_type == 'CA':
            organized["complexes"].append(record_data)
        elif record.schema_type == 'MA':
            organized["monuments"].append(record_data)
        elif record.schema_type == 'SAS':
            organized["stratigraphic_surveys"].append(record_data)
        elif record.schema_type == 'RA':
            organized["artifacts"].append(record_data)
        elif record.schema_type == 'NU':
            organized["numismatics"].append(record_data)
        elif record.schema_type == 'TMA':
            organized["material_tables"].append(record_data)
        elif record.schema_type == 'AT':
            organized["anthropology"].append(record_data)
    
    return JSONResponse(organized)


@iccd_hierarchy_router.post("/records")
async def create_iccd_record(
    record_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea nuova scheda ICCD con gestione gerarchia."""
    
    # Validazione dati base
    required_fields = ['schema_type', 'site_id', 'data']
    for field in required_fields:
        if field not in record_data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    try:
        # Genera NCT unico
        nct_number = generate_nct_number()
        
        # Crea record
        db_record = ICCDBaseRecord(
            nct_region='12',  # Lazio
            nct_number=nct_number,
            nct_suffix=record_data.get('nct_suffix'),
            schema_type=record_data['schema_type'],
            iccd_data=record_data['data'],
            parent_id=record_data.get('parent_id'),
            site_id=record_data['site_id'],
            created_by=current_user_id
        )
        
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)
        
        return JSONResponse({
            "id": str(db_record.id),
            "nct": f"{db_record.nct_region}{db_record.nct_number}{db_record.nct_suffix or ''}",
            "schema_type": db_record.schema_type
        })
        
    except Exception as e:
        logger.error(f"Error creating ICCD record: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione scheda ICCD: {str(e)}")


@iccd_hierarchy_router.post("/relations")
async def create_iccd_relation(
    relation_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea relazione tra schede ICCD."""
    
    required_fields = ['source_record_id', 'target_record_id', 'relation_type']
    for field in required_fields:
        if field not in relation_data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    try:
        db_relation = ICCDRelation(
            source_record_id=relation_data['source_record_id'],
            target_record_id=relation_data['target_record_id'],
            relation_type=relation_data['relation_type'],
            relation_level=relation_data.get('relation_level', '1'),
            notes=relation_data.get('notes'),
            created_by=current_user_id
        )
        
        db.add(db_relation)
        await db.commit()
        await db.refresh(db_relation)
        
        return JSONResponse({
            "id": str(db_relation.id),
            "relation_type": db_relation.relation_type,
            "message": "Relazione creata con successo"
        })
        
    except Exception as e:
        logger.error(f"Error creating ICCD relation: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione relazione: {str(e)}")


@iccd_hierarchy_router.get("/authority-files")
async def get_authority_files(
    site_id: UUID,
    authority_type: Optional[str] = Query(None, description="Filtro per tipo authority"),
    site_access: tuple = Depends(get_site_access_for_iccd_hierarchy),
    db: AsyncSession = Depends(get_async_session)
):
    """Recupera authority files per un sito."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    query = select(ICCDAuthorityFile).where(ICCDAuthorityFile.site_id == site_id)
    
    if authority_type:
        query = query.where(ICCDAuthorityFile.authority_type == authority_type)
    
    query = query.order_by(ICCDAuthorityFile.authority_type, ICCDAuthorityFile.name)
    
    result = await db.execute(query)
    authority_files = result.scalars().all()
    
    organized = {
        "excavations": [],  # DSC
        "surveys": [],      # RCG
        "bibliography": [], # BIB
        "authors": []       # AUT
    }
    
    for af in authority_files:
        af_data = {
            "id": str(af.id),
            "authority_type": af.authority_type,
            "authority_code": af.authority_code,
            "name": af.name,
            "description": af.description,
            "authority_data": af.authority_data
        }
        
        if af.authority_type == 'DSC':
            organized["excavations"].append(af_data)
        elif af.authority_type == 'RCG':
            organized["surveys"].append(af_data)
        elif af.authority_type == 'BIB':
            organized["bibliography"].append(af_data)
        elif af.authority_type == 'AUT':
            organized["authors"].append(af_data)
    
    return JSONResponse(organized)


@iccd_hierarchy_router.post("/authority-files")
async def create_authority_file(
    authority_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea nuovo authority file."""
    
    required_fields = ['authority_type', 'site_id', 'name']
    for field in required_fields:
        if field not in authority_data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    try:
        # Genera codice authority
        authority_code = f"{authority_data['authority_type']}-{datetime.now().year}-{datetime.now().microsecond % 1000:03d}"
        
        db_authority = ICCDAuthorityFile(
            authority_type=authority_data['authority_type'],
            authority_code=authority_code,
            name=authority_data['name'],
            description=authority_data.get('description'),
            authority_data=authority_data.get('data', {}),
            site_id=authority_data['site_id'],
            created_by=current_user_id
        )
        
        db.add(db_authority)
        await db.commit()
        await db.refresh(db_authority)
        
        return JSONResponse({
            "id": str(db_authority.id),
            "authority_code": db_authority.authority_code,
            "message": f"Authority File {db_authority.authority_type} creato"
        })
        
    except Exception as e:
        logger.error(f"Error creating authority file: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione authority file: {str(e)}")


def generate_nct_number() -> str:
    """Genera numero NCT unico basato su timestamp."""
    now = datetime.now()
    year = now.year % 100  # Ultime 2 cifre dell'anno
    timestamp = now.microsecond % 1000000  # Microseconds per unicità
    return f"{year:02d}{timestamp:06d}"