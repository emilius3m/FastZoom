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
from app.models import UserSitePermission
from app.models.iccd_records import ICCDBaseRecord, ICCDAuthorityFile
from app.models import User

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
    
    # Query gerarchica per tutti i tipi di scheda (SQLite compatible)
    # Cerchiamo tutti i record senza genitore come radice
    hierarchy_query = """
    WITH RECURSIVE hierarchy AS (
        -- Radice: tutti i record senza genitore
        SELECT
            r.id, r.schema_type, r.nct_region, r.nct_number, r.nct_suffix,
            r.iccd_data, r.parent_id, r.site_id, 0 as level,
            r.id as path
        FROM iccd_base_records r
        WHERE r.site_id = :site_id AND r.parent_id IS NULL
        
        UNION ALL
        
        -- Ricorsiva: tutti i figli
        SELECT
            r.id, r.schema_type, r.nct_region, r.nct_number, r.nct_suffix,
            r.iccd_data, r.parent_id, r.site_id, h.level + 1,
            h.path || ',' || r.id
        FROM iccd_base_records r
        INNER JOIN hierarchy h ON r.parent_id = h.id
        WHERE r.site_id = :site_id
    )
    SELECT * FROM hierarchy ORDER BY level, schema_type, nct_number;
    """
    
    result = await db.execute(text(hierarchy_query), {"site_id": str(site_id)})
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
    
    # Prima passata: organizza tutti i record tranne i record SI
    other_records = []
    si_records_from_hierarchy = []
    
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
        
        if record.schema_type == 'SI':
            si_records_from_hierarchy.append(record_data)
        else:
            other_records.append((record_data, record.schema_type))
    
    # Assegna il primo record SI trovato come record del sito (se esiste nella gerarchia)
    if si_records_from_hierarchy:
        organized["site"] = si_records_from_hierarchy[0] # Prendi il primo record SI trovato nella gerarchia
    else:
        # Se non abbiamo trovato record SI nella gerarchia, cerchiamo esplicitamente
        # LA scheda SI per questo sito (ogni sito archeologico ha una sola scheda SI)
        si_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.site_id == site_id,
                ICCDBaseRecord.schema_type == 'SI'
            )
        )
        si_result = await db.execute(si_query)
        si_db_record = si_result.scalar_one_or_none()  # Ogni sito ha una sola scheda SI
        
        if si_db_record:
            organized["site"] = {
                "id": str(si_db_record.id),
                "schema_type": si_db_record.schema_type,
                "nct_region": si_db_record.nct_region,
                "nct_number": si_db_record.nct_number,
                "nct_suffix": si_db_record.nct_suffix,
                "iccd_data": si_db_record.iccd_data,
                "level": 0,  # Lo trattiamo come livello 0 anche se ha un genitore
                "nct": f"{si_db_record.nct_region}{si_db_record.nct_number}{si_db_record.nct_suffix or ''}"
            }
    
    # Assegna gli altri record alle categorie appropriate
    for record_data, schema_type in other_records:
        if schema_type == 'CA':
            organized["complexes"].append(record_data)
        elif schema_type == 'MA':
            organized["monuments"].append(record_data)
        elif schema_type == 'SAS':
            organized["stratigraphic_surveys"].append(record_data)
        elif schema_type == 'RA':
            organized["artifacts"].append(record_data)
        elif schema_type == 'NU':
            organized["numismatics"].append(record_data)
        elif schema_type == 'TMA':
            organized["material_tables"].append(record_data)
        elif schema_type == 'AT':
            organized["anthropology"].append(record_data)
    
    # Se non ci sono record SI, ma ci sono altri record, comunque mostriamo un placeholder
    # per indicare che il sito esiste, ma potrebbe non avere un record SI
    if organized["site"] is None and (
        organized["complexes"] or organized["monuments"] or
        organized["stratigraphic_surveys"] or organized["artifacts"] or
        organized["numismatics"] or organized["material_tables"] or
        organized["anthropology"]
    ):
        # Tuttavia, in questo caso non creiamo un record fittizio ma lasciamo come None
        # permettere al frontend di gestire la situazione
        pass
    elif organized["site"] is None:
        # Se non ci sono proprio record di alcun tipo, possiamo considerare di mostrare
        # informazioni base sul sito
        pass
    
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
        # Ensure UUID conversion for parent_id and site_id
        parent_id_value = None
        if record_data.get('parent_id'):
            if isinstance(record_data['parent_id'], str):
                parent_id_value = UUID(record_data['parent_id'])
            else:
                parent_id_value = record_data['parent_id']
        
        site_id_value = record_data['site_id']
        if isinstance(site_id_value, str):
            site_id_value = UUID(site_id_value)
        
        db_record = ICCDBaseRecord(
            nct_region='12',  # Lazio
            nct_number=nct_number,
            nct_suffix=record_data.get('nct_suffix'),
            schema_type=record_data['schema_type'],
            iccd_data=record_data['data'],
            parent_id=parent_id_value,
            site_id=site_id_value,
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


# Endpoint rimosso: le relazioni sono gestite direttamente tramite parent_id in ICCDBaseRecord
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
        
        # Ensure UUID conversion for site_id
        site_id_value = authority_data['site_id']
        if isinstance(site_id_value, str):
            site_id_value = UUID(site_id_value)
        
        db_authority = ICCDAuthorityFile(
            authority_type=authority_data['authority_type'],
            authority_code=authority_code,
            name=authority_data['name'],
            description=authority_data.get('description'),
            authority_data=authority_data.get('data', {}),
            site_id=site_id_value,
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