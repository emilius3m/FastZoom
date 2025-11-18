"""
API v1 - Giornale di Cantiere Management
Endpoints per gestione giornale di cantiere archeologico.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from datetime import datetime

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session

router = APIRouter()

def normalize_site_id(site_id: str) -> Optional[str]:
    """
    Normalizza l'ID del sito per supportare diversi formati.
    
    Supporta:
    - UUID standard con trattini: eb8d88e1-74e3-46d3-8e86-81f926c01cab
    - Hash esadecimali senza trattini: eeedd3ceda34bf3b47d749a971b22ba
    
    Returns:
        str: L'ID normalizzato o None se non valido
    """
    if not site_id:
        return None
    
    # Rimuovi spazi bianchi
    site_id = site_id.strip()
    
    # Se è un UUID standard con trattini, valida e restituiscilo
    if '-' in site_id:
        try:
            # Crea un oggetto UUID per validare il formato
            uuid_obj = UUID(site_id)
            # Restituisci la stringa originale (già nel formato corretto)
            return site_id
        except (ValueError, AttributeError):
            return None
    
    # Se è un hash esadecimale senza trattini
    if len(site_id) == 32:
        try:
            # Verifica che sia esadecimale
            int(site_id, 16)
            # Converti in formato UUID standard (inserisci trattini)
            uuid_formatted = f"{site_id[0:8]}-{site_id[8:12]}-{site_id[12:16]}-{site_id[16:20]}-{site_id[20:32]}"
            # Valida il formato UUID risultante
            UUID(uuid_formatted)
            return uuid_formatted
        except (ValueError, AttributeError):
            return None
    
    # Altri formati non supportati
    return None

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verifica accesso al sito e restituisce informazioni sul sito
    
    🔧 ENHANCED: Improved UUID format handling with comprehensive logging
    Handles various UUID formats and provides detailed debugging information
    """
    from loguru import logger
    
    # 🔍 DEBUG: Log input parameters
    logger.info(f"🐛 [DEBUG] verify_site_access - site_id: {site_id}, type: {type(site_id)}")
    logger.info(f"🐛 [DEBUG] verify_site_access - user_sites count: {len(user_sites)}")
    
    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(str(site_id))
    if not normalized_site_id:
        logger.warning(f"🐛 [DEBUG] Invalid site_id format: {site_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID sito non valido: {site_id}"
        )
    
    # 🔍 DEBUG: Log all UUID format variations
    logger.info(f"🐛 [DEBUG] verify_site_access - site_id_str: {str(site_id)}")
    logger.info(f"🐛 [DEBUG] verify_site_access - normalized_site_id: {normalized_site_id}")
    
    # 🔍 DEBUG: Log all user sites for comparison
    for i, site in enumerate(user_sites):
        logger.info(f"🐛 [DEBUG] user_site[{i}]: id={site.get('id', 'MISSING')}, name={site.get('name', 'MISSING')}")
        if site.get('id'):
            site_id_from_user = str(site["id"])
            logger.info(f"🐛 [DEBUG] user_site[{i}] - raw: {site_id_from_user}")
            logger.info(f"🐛 [DEBUG] user_site[{i}] - no_hyphens: {site_id_from_user.replace('-', '')}")
            logger.info(f"🐛 [DEBUG] user_site[{i}] - lower: {site_id_from_user.lower()}")
    
    # Enhanced matching with multiple format variations
    site_info = None
    for site in user_sites:
        if not site.get("id"):
            logger.warning(f"🐛 [DEBUG] Site missing 'id' field: {site}")
            continue
        
        site_user_id = str(site["id"])
        
        # Try multiple matching strategies with normalized ID
        if (site_user_id == normalized_site_id or
            site_user_id == str(site_id) or
            site_user_id.replace("-", "") == normalized_site_id.replace("-", "")):
        
            site_info = site
            logger.info(f"🐛 [DEBUG] FOUND MATCH! Site: {site.get('name', 'Unknown')} (ID: {site_user_id})")
            break
    
    if not site_info:
        # 🔍 DEBUG: Detailed failure logging
        logger.error(f"🐛 [DEBUG] verify_site_access - NO MATCH FOUND")
        logger.error(f"🐛 [DEBUG] Looking for site_id variations:")
        logger.error(f"🐛 [DEBUG]  - Original: {str(site_id)}")
        logger.error(f"🐛 [DEBUG]  - Normalized: {normalized_site_id}")
        logger.error(f"🐛 [DEBUG] Available user sites:")
        for i, site in enumerate(user_sites):
            logger.error(f"🐛 [DEBUG]  - Site {i}: {site.get('name', 'Unknown')} (ID: {site.get('id', 'MISSING')})")
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied. User has access to {len(user_sites)} sites."
        )
    
    logger.info(f"🐛 [DEBUG] verify_site_access - SUCCESS: User has access to site '{site_info.get('name', 'Unknown')}'")
    return site_info

# Import required models and schemas
from app.models.giornale_cantiere import (
    GiornaleCantiere,
    OperatoreCantiere,
    giornale_operatori_association,
    CondizioniMeteoEnum
)
from app.schemas.giornale_cantiere import (
    OperatoreCantiereCreate,
    OperatoreCantiereOut,
    OperatoreCantiereUpdate,
)
from datetime import date, time
from sqlalchemy import select, func, and_, or_, desc, distinct
from sqlalchemy.orm import selectinload


# ===== HELPER FUNCTION FOR ENHANCED OPERATOR DATA =====

async def _get_enhanced_operator_data(db: AsyncSession, giornale_id: str, operatori_list: List) -> List[Dict[str, Any]]:
    """
    Helper function to fetch enhanced operator data including hours worked and presence notes
    from the giornale_operatori association table.
    
    Args:
        db: Database session
        giornale_id: ID of the giornale
        operatori_list: List of operator objects from the relationship
    
    Returns:
        Enhanced operator data with hours and notes
    """
    enhanced_operatori = []
    
    for op in operatori_list:
        # Query the association table to get enhanced data for this operator in this giornale
        association_result = await db.execute(
            select(giornale_operatori_association.c.ore_lavorate,
                   giornale_operatori_association.c.note_presenza)
            .where(
                and_(
                    giornale_operatori_association.c.giornale_id == str(giornale_id),
                    giornale_operatori_association.c.operatore_id == str(op.id)
                )
            )
        )
        association_data = await association_result.first()
        
        operator_dict = {
            "id": str(op.id),
            "nome": op.nome,
            "cognome": op.cognome,
            "ruolo": op.ruolo,
            "qualifica": op.qualifica,
            "ore_lavorate": float(association_data.ore_lavorate) if association_data and association_data.ore_lavorate is not None else None,
            "note_presenza": association_data.note_presenza if association_data else None,
        }
        enhanced_operatori.append(operator_dict)
    
    return enhanced_operatori

@router.get("/sites/{site_id}", summary="Lista giornali sito", tags=["Giornale di Cantiere"])
async def v1_get_site_giornali(
    site_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    data_da: Optional[date] = Query(None),
    data_a: Optional[date] = Query(None),
    responsabile: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    cantiere_id: Optional[UUID] = Query(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti i giornali di cantiere di un sito con filtri avanzati.
    
    🔧 ENHANCED: Improved error handling and comprehensive logging
    
    Args:
        site_id: ID del sito archeologico
        skip: Numero di record da saltare (paginazione)
        limit: Numero massimo di record da restituire
        data_da: Filtra giornali da questa data
        data_a: Filtra giornali fino a questa data
        responsabile: Filtra per nome responsabile
        stato: Filtra per stato (validato/in_attesa)
        cantiere_id: Filtra per cantiere specifico
    """
    try:
        # 🔍 DEBUG: Enhanced logging for troubleshooting
        logger.info(f"🐛 [DEBUG] v1_get_site_giornali - START")
        logger.info(f"🐛 [DEBUG] Current user: {current_user_id}")
        logger.info(f"🐛 [DEBUG] Requested site_id: {site_id} (type: {type(site_id)})")
        logger.info(f"🐛 [DEBUG] User sites count: {len(user_sites)}")
        
        # 🔍 DEBUG: Validate user_sites before proceeding
        if not user_sites:
            logger.warning(f"🐛 [DEBUG] User has NO accessible sites!")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no accessible sites. Please contact administrator."
            )
        
        # 🔍 DEBUG: Log user sites details
        for i, site in enumerate(user_sites):
            logger.info(f"🐛 [DEBUG] User site {i}: {site.get('name', 'Unknown')} (ID: {site.get('id', 'MISSING')})")
        
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        logger.info(f"🐛 [DEBUG] Site access verified: {site_info.get('name', 'Unknown')}")

        # 🔍 DEBUG: Prepare query with enhanced logging
        site_id_str = str(site_id)
        logger.info(f"🐛 [DEBUG] Querying journals for site_id_str: {site_id_str}")
        
        # Query base
        query = select(GiornaleCantiere).where(GiornaleCantiere.site_id == site_id_str)
        logger.info(f"🐛 [DEBUG] Base query prepared")
        
        # Filtra per cantiere specifico se specificato
        if cantiere_id:
            query = query.where(GiornaleCantiere.cantiere_id == str(cantiere_id))

        # Applica filtri
        if data_da:
            query = query.where(GiornaleCantiere.data >= data_da)
        if data_a:
            query = query.where(GiornaleCantiere.data <= data_a)
        if responsabile:
            query = query.where(
                GiornaleCantiere.responsabile_nome.ilike(f"%{responsabile}%")
            )
        if stato:
            if stato == "validato":
                query = query.where(GiornaleCantiere.validato.is_(True))
            elif stato == "in_attesa":
                query = query.where(GiornaleCantiere.validato.is_(False))

        # Load relationships (rimosso cantiere per evitare problemi di import)
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori),
        )
        
        # Ordinamento e paginazione
        query = query.order_by(
            desc(GiornaleCantiere.data), desc(GiornaleCantiere.created_at)
        )
        query = query.offset(skip).limit(limit)

        # 🔍 DEBUG: Execute query with logging
        logger.info(f"🐛 [DEBUG] Executing database query...")
        result = await db.execute(query)
        giornali = result.scalars().all()
        logger.info(f"🐛 [DEBUG] Query executed. Found {len(giornali)} giornali")

        # Prepara dati di risposta
        giornali_data = []
        for g in giornali:
            # Gestione cantiere senza relazione diretta
            cantiere_info = None
            if g.cantiere_id:
                # Query separata per ottenere informazioni del cantiere se necessario
                from app.models.cantiere import Cantiere
                cantiere_result = await db.execute(
                    select(Cantiere).where(Cantiere.id == g.cantiere_id)  # 🔥 FIX: Direct string-to-string comparison for SQLite compatibility
                )
                cantiere = cantiere_result.scalar_one_or_none()
                if cantiere:
                    cantiere_info = {
                        "id": str(cantiere.id),
                        "nome": cantiere.nome,
                        "codice": cantiere.codice,
                        # Campi per il giornale dei lavori
                        "committente": cantiere.committente,
                        "impresa_esecutrice": cantiere.impresa_esecutrice,
                        "direttore_lavori": cantiere.direttore_lavori,
                        "responsabile_procedimento": cantiere.responsabile_procedimento,
                        "oggetto_appalto": cantiere.oggetto_appalto,
                        # Campi opzionali
                        "codice_cup": cantiere.codice_cup,
                        "codice_cig": cantiere.codice_cig,
                        "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None
                    }
            
            giornale_dict = {
                "id": str(g.id),
                "data": g.data.isoformat() if g.data else None,
                "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
                "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
                "responsabile_scavo": g.responsabile_nome
                or (g.responsabile.email if g.responsabile else None),
                "descrizione_lavori": g.descrizione_lavori,
                "condizioni_meteo": g.condizioni_meteo,
                "stato": "validato" if g.validato else "in_attesa",
                "us_elaborate": g.get_us_list() if hasattr(g, "get_us_list") else [],
                "us_elaborate_input": g.us_elaborate if g.us_elaborate else "",
                "usm_elaborate": g.get_usm_list() if hasattr(g, "get_usm_list") else [],
                "usr_elaborate": g.usr_elaborate.split(",") if g.usr_elaborate else [],
                "cantiere_id": str(g.cantiere_id) if g.cantiere_id else None,
                "cantiere": cantiere_info,
                "operatori_presenti": await _get_enhanced_operator_data(db, g.id, g.operatori or []),
                "note_generali": g.note_generali,
                "problematiche": g.problematiche,
                "compilatore": g.compilatore or g.responsabile_nome,
                # New fields added from the model
                "temperatura": g.temperatura,
                "temperatura_min": g.temperatura_min,
                "temperatura_max": g.temperatura_max,
                "note_meteo": g.note_meteo,
                "modalita_lavorazioni": g.modalita_lavorazioni,
                "attrezzatura_utilizzata": g.attrezzatura_utilizzata,
                "apparecchiature_input": g.attrezzatura_utilizzata,  # Alias for frontend compatibility
                "mezzi_utilizzati": g.mezzi_utilizzati,
                "materiali_rinvenuti": g.materiali_rinvenuti,
                "documentazione_prodotta": g.documentazione_prodotta,
                "sopralluoghi": g.sopralluoghi,
                "disposizioni_rup": g.disposizioni_rup,
                "disposizioni_direttore": g.disposizioni_direttore,
                "contestazioni": g.contestazioni,
                "sospensioni": g.sospensioni,
                "incidenti": g.incidenti,
                "forniture": g.forniture,
                "data_validazione": g.data_validazione.isoformat() if g.data_validazione else None,
                "firma_digitale_hash": g.firma_digitale_hash,
                "allegati_paths": g.allegati_paths,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
                "version": g.version or 1,
            }
            giornali_data.append(giornale_dict)

        # 🔍 DEBUG: Prepare successful response with logging
        response_data = {
            "site_id": str(site_id),
            "giornali": giornali_data,
            "count": len(giornali_data),
            "site_info": site_info,
            "filters_applied": {
                "data_da": data_da.isoformat() if data_da else None,
                "data_a": data_a.isoformat() if data_a else None,
                "responsabile": responsabile,
                "stato": stato,
                "cantiere_id": str(cantiere_id) if cantiere_id else None
            }
        }
        
        logger.info(f"🐛 [DEBUG] v1_get_site_giornali - SUCCESS: Returning {len(giornali_data)} giornali")
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404 from verify_site_access)
        raise
    except Exception as e:
        # 🔍 DEBUG: Enhanced error logging
        logger.error(f"🐛 [DEBUG] v1_get_site_giornali - ERROR: {str(e)}")
        logger.error(f"🐛 [DEBUG] Error type: {type(e).__name__}")
        import traceback
        logger.error(f"🐛 [DEBUG] Full traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero dei giornali: {str(e)}",
        )
 
@router.get("/sites/{site_id}/cantieri/{cantiere_id}/giornali", summary="Lista giornali cantiere", tags=["Giornale di Cantiere"])
async def v1_get_cantiere_giornali(
    site_id: UUID,
    cantiere_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    data_da: Optional[date] = Query(None),
    data_a: Optional[date] = Query(None),
    responsabile: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti i giornali di un cantiere specifico con filtri avanzati.
    
    Args:
        site_id: ID del sito archeologico
        cantiere_id: ID del cantiere specifico
        skip: Numero di record da saltare (paginazione)
        limit: Numero massimo di record da restituire
        data_da: Filtra giornali da questa data
        data_a: Filtra giornali fino a questa data
        responsabile: Filtra per nome responsabile
        stato: Filtra per stato (validato/in_attesa)
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)

        # Query base per il cantiere specifico
        query = select(GiornaleCantiere).where(
            and_(
                GiornaleCantiere.site_id == str(site_id),
                GiornaleCantiere.cantiere_id == str(cantiere_id)
            )
        )

        # Applica filtri
        if data_da:
            query = query.where(GiornaleCantiere.data >= data_da)
        if data_a:
            query = query.where(GiornaleCantiere.data <= data_a)
        if responsabile:
            query = query.where(
                GiornaleCantiere.responsabile_nome.ilike(f"%{responsabile}%")
            )
        if stato:
            if stato == "validato":
                query = query.where(GiornaleCantiere.validato.is_(True))
            elif stato == "in_attesa":
                query = query.where(GiornaleCantiere.validato.is_(False))

        # Load relationships
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori),
        )
        
        # Ordinamento e paginazione
        query = query.order_by(
            desc(GiornaleCantiere.data), desc(GiornaleCantiere.created_at)
        )
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        giornali = result.scalars().all()

        # Prepara dati di risposta
        giornali_data = []
        for g in giornali:
            # Gestione cantiere senza relazione diretta
            cantiere_info = None
            if g.cantiere_id:
                # Query separata per ottenere informazioni del cantiere se necessario
                from app.models.cantiere import Cantiere
                cantiere_result = await db.execute(
                    select(Cantiere).where(Cantiere.id == g.cantiere_id)  # 🔥 FIX: Direct string-to-string comparison for SQLite compatibility
                )
                cantiere = cantiere_result.scalar_one_or_none()
                if cantiere:
                    cantiere_info = {
                        "id": str(cantiere.id),
                        "nome": cantiere.nome,
                        "codice": cantiere.codice,
                        # Campi per il giornale dei lavori
                        "committente": cantiere.committente,
                        "impresa_esecutrice": cantiere.impresa_esecutrice,
                        "direttore_lavori": cantiere.direttore_lavori,
                        "responsabile_procedimento": cantiere.responsabile_procedimento,
                        "oggetto_appalto": cantiere.oggetto_appalto,
                        # Campi opzionali
                        "codice_cup": cantiere.codice_cup,
                        "codice_cig": cantiere.codice_cig,
                        "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None
                    }
             
            giornale_dict = {
                "id": str(g.id),
                "data": g.data.isoformat() if g.data else None,
                "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
                "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
                "responsabile_scavo": g.responsabile_nome
                or (g.responsabile.email if g.responsabile else None),
                "descrizione_lavori": g.descrizione_lavori,
                "condizioni_meteo": g.condizioni_meteo,
                "stato": "validato" if g.validato else "in_attesa",
                "us_elaborate": g.get_us_list() if hasattr(g, "get_us_list") else [],
                "us_elaborate_input": g.us_elaborate if g.us_elaborate else "",
                "usm_elaborate": g.get_usm_list() if hasattr(g, "get_usm_list") else [],
                "usr_elaborate": g.usr_elaborate.split(",") if g.usr_elaborate else [],
                "cantiere_id": str(g.cantiere_id) if g.cantiere_id else None,
                "cantiere": cantiere_info,
                "operatori_presenti": await _get_enhanced_operator_data(db, g.id, g.operatori or []),
                "note_generali": g.note_generali,
                "problematiche": g.problematiche,
                "compilatore": g.compilatore or g.responsabile_nome,
                # New fields added from the model
                "temperatura": g.temperatura,
                "temperatura_min": g.temperatura_min,
                "temperatura_max": g.temperatura_max,
                "note_meteo": g.note_meteo,
                "modalita_lavorazioni": g.modalita_lavorazioni,
                "attrezzatura_utilizzata": g.attrezzatura_utilizzata,
                "apparecchiature_input": g.attrezzatura_utilizzata,  # Alias for frontend compatibility
                "mezzi_utilizzati": g.mezzi_utilizzati,
                "materiali_rinvenuti": g.materiali_rinvenuti,
                "documentazione_prodotta": g.documentazione_prodotta,
                "sopralluoghi": g.sopralluoghi,
                "disposizioni_rup": g.disposizioni_rup,
                "disposizioni_direttore": g.disposizioni_direttore,
                "contestazioni": g.contestazioni,
                "sospensioni": g.sospensioni,
                "incidenti": g.incidenti,
                "forniture": g.forniture,
                "data_validazione": g.data_validazione.isoformat() if g.data_validazione else None,
                "firma_digitale_hash": g.firma_digitale_hash,
                "allegati_paths": g.allegati_paths,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
                "version": g.version or 1,
            }
            giornali_data.append(giornale_dict)

        return {
            "site_id": str(site_id),
            "cantiere_id": str(cantiere_id),
            "giornali": giornali_data,
            "count": len(giornali_data),
            "site_info": site_info,
            "filters_applied": {
                "data_da": data_da.isoformat() if data_da else None,
                "data_a": data_a.isoformat() if data_a else None,
                "responsabile": responsabile,
                "stato": stato
            }
        }
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore recupero giornali cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei giornali del cantiere",
        )

@router.post("/sites/{site_id}/giornali", summary="Crea nuovo giornale", tags=["Giornale di Cantiere"])
async def v1_create_giornale(
    site_id: UUID,
    giornale_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea un nuovo giornale di cantiere per un sito specifico.
    
    🔥 NUOVA VALIDAZIONE: Verifica che gli operatori possano lavorare solo su cantieri del loro sito.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # 🔥 NUOVA VALIDAZIONE: Verifica che il cantiere appartenga al sito specificato
        cantiere_id = giornale_data.get("cantiere_id")
        if cantiere_id:
            from app.models.cantiere import Cantiere
            cantiere_result = await db.execute(
                select(Cantiere).where(
                    and_(
                        Cantiere.id == str(cantiere_id),  # 🔥 FIX: Convert UUID to string for SQLite compatibility
                        Cantiere.site_id == str(site_id)  # 🔥 CRUCIALE: Il cantiere deve appartenere al sito
                    )
                )
            )
            cantiere = cantiere_result.scalar_one_or_none()
            
            if not cantiere:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Il cantiere {cantiere_id} non appartiene al sito {site_id}"
                )
        
        # Crea nuovo giornale
        nuovo_giornale = GiornaleCantiere(
            site_id=str(site_id),  # Convert UUID to string for SQLite compatibility
            cantiere_id=str(UUID(cantiere_id)) if cantiere_id else None,
            data=date.fromisoformat(giornale_data.get("data")) if giornale_data.get("data") else date.today(),
            ora_inizio=time.fromisoformat(giornale_data["ora_inizio"]) if giornale_data.get("ora_inizio") else None,
            ora_fine=time.fromisoformat(giornale_data["ora_fine"]) if giornale_data.get("ora_fine") else None,
            descrizione_lavori=giornale_data.get("descrizione_lavori", ""),
            condizioni_meteo=giornale_data.get("condizioni_meteo"),
            note_generali=giornale_data.get("note_generali", ""),
            problematiche=giornale_data.get("problematiche", ""),
            responsabile_id=str(current_user_id),  # Convert UUID to string for SQLite compatibility
            responsabile_nome=giornale_data.get("responsabile_nome", ""),
            compilatore=giornale_data.get("compilatore", ""),
            temperatura_min=giornale_data.get("temperatura_min"),
            temperatura_max=giornale_data.get("temperatura_max"),
            us_elaborate=giornale_data.get("us_elaborate_input", ""),  # Convert input string to database field
            attrezzatura_utilizzata=giornale_data.get("apparecchiature_input", ""),  # Convert input string to database field
            validato=False
        )
        
        db.add(nuovo_giornale)
        await db.commit()
        await db.refresh(nuovo_giornale)
        
        # 🔥 NUOVA VALIDAZIONE: Verifica che gli operatori possano lavorare su questo sito
        operatori_data = giornale_data.get("operatori", [])  # Enhanced structure with hours and notes
        if operatori_data:
            for operatore_info in operatori_data:
                op_id = operatore_info.get("id")
                ore_lavorate = operatore_info.get("ore_lavorate")
                note_presenza = operatore_info.get("note_presenza")
                
                # Validate hours worked
                if ore_lavorate is not None and (not isinstance(ore_lavorate, (int, float)) or ore_lavorate < 0):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ore lavorate non valide per operatore {op_id}: deve essere un numero positivo"
                    )
                
                # Verifica che l'operatore esista e sia assegnato a questo sito
                operatore_result = await db.execute(
                    select(OperatoreCantiere).where(
                        and_(
                            OperatoreCantiere.id == str(op_id),
                            OperatoreCantiere.site_id == str(site_id)  # 🔥 CRUCIALE: L'operatore deve essere assegnato al sito
                        )
                    )
                )
                operatore = operatore_result.scalar_one_or_none()
                
                if not operatore:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"L'operatore {op_id} non è assegnato al sito {site_id} e non può lavorare su questo giornale"
                    )
                
                # Aggiungi l'operatore al giornale con enhanced data
                await db.execute(
                    giornale_operatori_association.insert().values(
                        giornale_id=str(nuovo_giornale.id),  # Convert UUID to string
                        operatore_id=str(UUID(op_id)),  # Convert UUID to string
                        ore_lavorate=float(ore_lavorate) if ore_lavorate is not None else None,
                        note_presenza=note_presenza
                    )
                )
            await db.commit()
        
        return {
            "id": str(nuovo_giornale.id),
            "message": "Giornale creato con successo con validazione operatori-sito",
            "site_info": site_info,
            "operatori_validati": len(operatori_data) if operatori_data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore creazione giornale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nella creazione del giornale"
        )

@router.put("/sites/{site_id}/giornali/{giornale_id}", summary="Aggiorna giornale", tags=["Giornale di Cantiere"])
async def v1_update_giornale(
    site_id: UUID,
    giornale_id: UUID,
    giornale_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna un giornale di cantiere esistente.
    
    🔥 NUOVA VALIDAZIONE: Verifica che cantieri e operatori appartengano al sito.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Carica giornale esistente
        result = await db.execute(
            select(GiornaleCantiere).where(
                and_(
                    GiornaleCantiere.id == str(giornale_id),
                    GiornaleCantiere.site_id == str(site_id)
                )
            )
        )
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # 🔥 NUOVA VALIDAZIONE: Verifica che il cantiere appartenga al sito
        if "cantiere_id" in giornale_data and giornale_data["cantiere_id"]:
            from app.models.cantiere import Cantiere
            cantiere_result = await db.execute(
                select(Cantiere).where(
                    and_(
                        Cantiere.id == str(giornale_data["cantiere_id"]),  # 🔥 FIX: Convert UUID to string for SQLite compatibility
                        Cantiere.site_id == str(site_id)  # 🔥 CRUCIALE: Il cantiere deve appartenere al sito
                    )
                )
            )
            cantiere = cantiere_result.scalar_one_or_none()
            
            if not cantiere:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Il cantiere {giornale_data['cantiere_id']} non appartiene al sito {site_id}"
                )
        
        # 🔥 NUOVA VALIDAZIONE: Verifica che gli operatori possano lavorare su questo sito
        if "operatori" in giornale_data:
            operatori_data = giornale_data["operatori"]
            if operatori_data:
                # Rimuovi vecchie associazioni
                await db.execute(
                    giornale_operatori_association.delete().where(
                        giornale_operatori_association.c.giornale_id == str(giornale_id)  # 🔥 FIX: Convert UUID to string for SQLite compatibility
                    )
                )
                
                # Aggiungi nuove associazioni con validazione
                for operatore_info in operatori_data:
                    op_id = operatore_info.get("id")
                    ore_lavorate = operatore_info.get("ore_lavorate")
                    note_presenza = operatore_info.get("note_presenza")
                    
                    # Validate hours worked
                    if ore_lavorate is not None and (not isinstance(ore_lavorate, (int, float)) or ore_lavorate < 0):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Ore lavorate non valide per operatore {op_id}: deve essere un numero positivo"
                        )
                    
                    operatore_result = await db.execute(
                        select(OperatoreCantiere).where(
                            and_(
                                OperatoreCantiere.id == str(op_id),
                                OperatoreCantiere.site_id == str(site_id)  # 🔥 CRUCIALE: L'operatore deve essere assegnato al sito
                            )
                        )
                    )
                    operatore = operatore_result.scalar_one_or_none()
                    
                    if not operatore:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"L'operatore {op_id} non è assegnato al sito {site_id}"
                        )
                    
                    # Aggiungi l'operatore al giornale con enhanced data
                    await db.execute(
                        giornale_operatori_association.insert().values(
                            giornale_id=str(giornale_id),  # Convert UUID to string
                            operatore_id=str(UUID(op_id)),  # Convert UUID to string
                            ore_lavorate=float(ore_lavorate) if ore_lavorate is not None else None,
                            note_presenza=note_presenza
                        )
                    )
        
        # Aggiorna campi base
        if "data" in giornale_data:
            giornale.data = date.fromisoformat(giornale_data["data"])
        if "ora_inizio" in giornale_data:
            giornale.ora_inizio = time.fromisoformat(giornale_data["ora_inizio"]) if giornale_data["ora_inizio"] else None
        if "ora_fine" in giornale_data:
            giornale.ora_fine = time.fromisoformat(giornale_data["ora_fine"]) if giornale_data["ora_fine"] else None
        if "cantiere_id" in giornale_data:
            giornale.cantiere_id = str(UUID(giornale_data["cantiere_id"])) if giornale_data["cantiere_id"] else None
        if "descrizione_lavori" in giornale_data:
            giornale.descrizione_lavori = giornale_data["descrizione_lavori"]
        if "condizioni_meteo" in giornale_data:
            giornale.condizioni_meteo = giornale_data["condizioni_meteo"]
        if "note_generali" in giornale_data:
            giornale.note_generali = giornale_data["note_generali"]
        if "problematiche" in giornale_data:
            giornale.problematiche = giornale_data["problematiche"]
        if "responsabile_nome" in giornale_data:
            giornale.responsabile_nome = giornale_data["responsabile_nome"]
        if "compilatore" in giornale_data:
            giornale.compilatore = giornale_data["compilatore"]
        if "temperatura_min" in giornale_data:
            giornale.temperatura_min = giornale_data["temperatura_min"]
        if "temperatura_max" in giornale_data:
            giornale.temperatura_max = giornale_data["temperatura_max"]
        if "us_elaborate_input" in giornale_data:
            giornale.us_elaborate = giornale_data["us_elaborate_input"]  # Convert input string to database field
        if "apparecchiature_input" in giornale_data:
            giornale.attrezzatura_utilizzata = giornale_data["apparecchiature_input"]  # Convert input string to database field
        
        await db.commit()
        
        return {
            "id": str(giornale.id),
            "message": "Giornale aggiornato con successo con validazione operatori-sito",
            "site_info": site_info,
            "operatori_validati": len(operatori_data) if "operatori" in giornale_data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento giornale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nell'aggiornamento del giornale"
        )

@router.delete("/sites/{site_id}/giornali/{giornale_id}", summary="Elimina giornale", tags=["Giornale di Cantiere"])
async def v1_delete_giornale(
    site_id: UUID,
    giornale_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Elimina un giornale di cantiere.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Carica giornale
        result = await db.execute(
            select(GiornaleCantiere).where(
                and_(
                    GiornaleCantiere.id == str(giornale_id),
                    GiornaleCantiere.site_id == str(site_id)
                )
            )
        )
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Rimuovi associazioni operatori
        await db.execute(
            giornale_operatori_association.delete().where(
                giornale_operatori_association.c.giornale_id == str(giornale_id)  # 🔥 FIX: Convert UUID to string for SQLite compatibility
            )
        )
        
        # Elimina giornale
        await db.delete(giornale)
        await db.commit()
        
        return {
            "message": "Giornale eliminato con successo",
            "site_info": site_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione giornale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nell'eliminazione del giornale"
        )

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API giornale", tags=["Giornale di Cantiere - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per giornale di cantiere.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/giornale-cantiere/sites/{site_id}": "/api/v1/giornale/sites/{site_id}",
                "/api/giornale-cantiere/giornali": "/api/v1/giornale/giornali",
                "/api/giornale-cantiere/operatori/site/{site_id}": "/api/v1/giornale/sites/{site_id}/operatori",
                "/api/giornale-cantiere/operatori": "/api/v1/giornale/operatori",
                "/api/giornale-cantiere/stats/general": "/api/v1/giornale/stats/general",
                "/api/giornale-cantiere/stats/site/{site_id}": "/api/v1/giornale/stats/site/{site_id}",
                "/api/giornale-cantiere/stats/operatori": "/api/v1/giornale/stats/operatori"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints giornale in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata",
                "Operatori specifici per sito con filtri avanzati"
            ],
            "new_features": [
                "Endpoint per operatori specifici del sito con filtri (ruolo, specializzazione, stato)",
                "Conteggio giornali per operatore specifico del sito",
                "Metadati completi del sito inclusi nella risposta"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints giornale"
        }
    }

@router.get("/sites/{site_id}/operatori", summary="Operatori specifici sito", tags=["Giornale di Cantiere"])
async def v1_get_site_operatori(
    site_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    ruolo: Optional[str] = Query(None),
    specializzazione: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti gli operatori assegnati a un sito archeologico specifico.
    
    🔥 NUOVA LOGICA: Restituisce SOLO gli operatori con site_id == site_id.
    Gli operatori possono lavorare solo su cantieri del loro sito di assegnazione.
    
    Args:
        site_id: ID del sito archeologico
        skip: Numero di record da saltare (paginazione)
        limit: Numero massimo di record da restituire
        search: Testo di ricerca per nome, cognome o codice fiscale
        ruolo: Filtra per ruolo dell'operatore
        specializzazione: Filtra per specializzazione
        stato: Filtra per stato (attivo/inattivo)
    
    Returns:
        Lista degli operatori assegnati a questo sito con metadati
    """
    from app.models.giornale_cantiere import (
        GiornaleCantiere,
        OperatoreCantiere,
        giornale_operatori_association
    )
    from sqlalchemy import select, func, or_, and_
    from sqlalchemy.orm import selectinload
    
    try:
        # 🐛 DEBUG LOG: Inizio funzione
        from loguru import logger
        logger.info(f"🐛 [DEBUG] v1_get_site_operatori - site_id={site_id}, type={type(site_id)}")
        logger.info(f"🐛 [DEBUG] site_id str representation: {str(site_id)}")
        
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        logger.info(f"🐛 [DEBUG] site_info: {site_info}")
        
        # 🔥 NUOVA LOGICA: Query solo per operatori assegnati a questo sito
        site_id_str = str(site_id)
        logger.info(f"🐛 [DEBUG] site_id_str per query: {site_id_str}")
        query = select(OperatoreCantiere).where(OperatoreCantiere.site_id == site_id_str)
        
        # Applica filtri aggiuntivi
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    OperatoreCantiere.nome.ilike(search_pattern),
                    OperatoreCantiere.cognome.ilike(search_pattern),
                    OperatoreCantiere.codice_fiscale.ilike(search_pattern),
                )
            )
        if ruolo:
            query = query.where(OperatoreCantiere.ruolo == ruolo)
        if specializzazione:
            query = query.where(OperatoreCantiere.specializzazione == specializzazione)
        if stato:
            query = query.where(OperatoreCantiere.is_active == (stato == "attivo"))
        
        query = query.order_by(OperatoreCantiere.cognome, OperatoreCantiere.nome)
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        operatori = result.scalars().all()
        logger.info(f"🐛 [DEBUG] Trovati {len(operatori)} operatori per il sito")
        
        # Conteggio giornali per ogni operatore in questo sito
        operatori_data = []
        for i, op in enumerate(operatori):
            logger.info(f"🐛 [DEBUG] Operatore {i+1}: id={op.id}, type={type(op.id)}, str={str(op.id)}")
            logger.info(f"🐛 [DEBUG] Operatore {i+1}: nome={op.nome} {op.cognome}")
            logger.info(f"🐛 [DEBUG] Operatore {i+1}: site_id={op.site_id}, type={type(op.site_id)}")
            
            # Query per contare i giornali di questo sito dove questo operatore ha lavorato
            # Convert both values to strings for consistent comparison
            op_id_str = str(op.id)
            logger.info(f"🐛 [DEBUG] op_id_str: {op_id_str}")
            
            logger.info(f"🐛 [DEBUG] Eseguendo query per contare giornali dell'operatore...")
            giornali_count_result = await db.execute(
                select(func.count(GiornaleCantiere.id))
                .join(giornale_operatori_association, GiornaleCantiere.id == giornale_operatori_association.c.giornale_id)
                .where(
                    and_(
                        GiornaleCantiere.site_id == site_id_str,
                        giornale_operatori_association.c.operatore_id == op_id_str  # Convert UUID to string for comparison
                    )
                )
            )
            giornali_count = giornali_count_result.scalar() or 0
            logger.info(f"🐛 [DEBUG] Operatore {i+1}: trovati {giornali_count} giornali")
           
            operatori_data.append({
                "id": str(op.id),
                "nome": op.nome,
                "cognome": op.cognome,
                "codice_fiscale": op.codice_fiscale,
                "email": op.email,
                "telefono": op.telefono,
                "ruolo": op.ruolo,
                "specializzazione": op.specializzazione,
                "qualifiche": op.qualifica.split(",") if op.qualifica else [],
                "stato": "attivo" if op.is_active else "inattivo",
                "ore_totali": op.ore_totali or 0,
                "giornali_count": giornali_count,
                "site_id": str(op.site_id),  # 🔥 NUOVO: Include il site_id dell'operatore
                "note": op.note,
                "assigned_to_site": True,  # 🔥 NUOVO: Indica che l'operatore è assegnato a questo sito
                "can_work_on_site": op.site_id == str(site_id),  # 🔥 NUOVO: Verifica se può lavorare su questo sito
            })
        
        logger.info(f"🐛 [DEBUG] Preparando risposta finale con {len(operatori_data)} operatori")
        response_data = {
            "site_id": str(site_id),
            "operatori": operatori_data,
            "count": len(operatori_data),
            "site_info": site_info,
            "filters_applied": {
                "search": search,
                "ruolo": ruolo,
                "specializzazione": specializzazione,
                "stato": stato
            }
        }
        logger.info(f"🐛 [DEBUG] Risposta preparata con successo")
        return response_data
        
    except Exception as e:
        from loguru import logger
        logger.error(f"🐛 [DEBUG] Errore recupero operatori sito {site_id}: {str(e)}")
        logger.error(f"🐛 [DEBUG] Tipo di errore: {type(e)}")
        import traceback
        logger.error(f"🐛 [DEBUG] Stack trace completo: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero degli operatori del sito",
        )

@router.post("/sites/{site_id}/operatori", summary="Crea nuovo operatore", tags=["Giornale di Cantiere"])
async def v1_create_operatore(
    site_id: UUID,
    operatore_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea un nuovo operatore di cantiere assegnato a un sito specifico.
    
    L'operatore potrà lavorare solo su cantieri appartenenti a questo sito.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Crea nuovo operatore con site_id obbligatorio
        nuovo_operatore = OperatoreCantiere(
            site_id=str(site_id),  # 🔥 NUOVO: Associa l'operatore al sito (convert UUID to string)
            nome=operatore_data.get("nome"),
            cognome=operatore_data.get("cognome"),
            codice_fiscale=operatore_data.get("codice_fiscale"),
            qualifica=operatore_data.get("qualifica"),
            ruolo=operatore_data.get("ruolo"),
            specializzazione=operatore_data.get("specializzazione"),
            email=operatore_data.get("email"),
            telefono=operatore_data.get("telefono"),
            is_active=operatore_data.get("is_active", True),
            note=operatore_data.get("note"),
            ore_totali=0
        )
        
        db.add(nuovo_operatore)
        await db.commit()
        await db.refresh(nuovo_operatore)
        
        return {
            "id": str(nuovo_operatore.id),
            "site_id": str(site_id),  # 🔥 NUOVO: Include site_id nella risposta
            "message": "Operatore creato con successo e assegnato al sito",
            "site_info": site_info
        }
        
    except Exception as e:
        logger.error(f"Errore creazione operatore: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nella creazione dell'operatore"
        )

@router.put("/operatori/{operatore_id}", summary="Aggiorna operatore", tags=["Giornale di Cantiere"])
async def v1_update_operatore(
    operatore_id: UUID,
    operatore_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna un operatore di cantiere esistente.
    """
    try:
        # Carica operatore esistente
        result = await db.execute(
            select(OperatoreCantiere).where(OperatoreCantiere.id == str(operatore_id))
        )
        operatore = result.scalar_one_or_none()
        
        if not operatore:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operatore non trovato"
            )
        
        # Aggiorna campi
        if "nome" in operatore_data:
            operatore.nome = operatore_data["nome"]
        if "cognome" in operatore_data:
            operatore.cognome = operatore_data["cognome"]
        if "codice_fiscale" in operatore_data:
            operatore.codice_fiscale = operatore_data["codice_fiscale"]
        if "qualifica" in operatore_data:
            operatore.qualifica = operatore_data["qualifica"]
        if "ruolo" in operatore_data:
            operatore.ruolo = operatore_data["ruolo"]
        if "specializzazione" in operatore_data:
            operatore.specializzazione = operatore_data["specializzazione"]
        if "email" in operatore_data:
            operatore.email = operatore_data["email"]
        if "telefono" in operatore_data:
            operatore.telefono = operatore_data["telefono"]
        if "is_active" in operatore_data:
            operatore.is_active = operatore_data["is_active"]
        if "note" in operatore_data:
            operatore.note = operatore_data["note"]
        
        await db.commit()
        
        return {
            "id": str(operatore.id),
            "message": "Operatore aggiornato con successo"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento operatore: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nell'aggiornamento dell'operatore"
        )


@router.get("/stats/general", summary="Statistiche generali giornali", tags=["Giornale di Cantiere - Stats"])
async def v1_get_general_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera statistiche generali per tutti i siti accessibili.
    
    🔧 ENHANCED: Improved error handling and UUID format validation
    """
    try:
        # 🔍 DEBUG LOG: Enhanced logging for troubleshooting
        logger.info(f"🐛 [DEBUG] v1_get_general_stats - START")
        logger.info(f"🐛 [DEBUG] Current user: {current_user_id}")
        logger.info(f"🐛 [DEBUG] User sites count: {len(user_sites) if user_sites else 0}")
        
        # 🔍 DEBUG: Validate user_sites before processing
        if not user_sites:
            logger.warning(f"🐛 [DEBUG] User has NO accessible sites for general stats")
            return {
                "siti_totali": 0,
                "giornali_totali": 0,
                "giornali_validati": 0,
                "giornali_pendenti": 0,
                "debug_info": "User has no accessible sites"
            }
        
        # 🔍 DEBUG: Enhanced site_id processing with validation
        site_ids = []
        for site in user_sites:
            try:
                site_id_str = str(site["id"])
                site_ids.append(site_id_str)
                logger.info(f"🐛 [DEBUG] Processing site: {site.get('name', 'Unknown')} (ID: {site_id_str})")
            except (KeyError, ValueError) as e:
                logger.error(f"🐛 [DEBUG] Invalid site data: {site}, error: {e}")
                continue
        
        logger.info(f"🐛 [DEBUG] Final site_ids for query: {site_ids}")
        
        if not site_ids:
            logger.warning(f"🐛 [DEBUG] No valid site_ids after processing, returning zeros")
            return {
                "siti_totali": 0,
                "giornali_totali": 0,
                "giornali_validati": 0,
                "giornali_pendenti": 0,
                "debug_info": "No valid site IDs found after processing"
            }

        # 🔍 DEBUG: Execute database queries with enhanced logging
        logger.info(f"🐛 [DEBUG] Querying unique sites with journals...")
        siti_result = await db.execute(
            select(distinct(GiornaleCantiere.site_id)).where(
                GiornaleCantiere.site_id.in_(site_ids)
            )
        )
        siti_totali = len(siti_result.fetchall())
        logger.info(f"🐛 [DEBUG] Found {siti_totali} unique sites with journals")

        logger.info(f"🐛 [DEBUG] Querying total journals count...")
        totali_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                GiornaleCantiere.site_id.in_(site_ids)
            )
        )
        giornali_totali = totali_result.scalar() or 0
        logger.info(f"🐛 [DEBUG] Found {giornali_totali} total journals")

        logger.info(f"🐛 [DEBUG] Querying validated journals count...")
        validati_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                and_(
                    GiornaleCantiere.site_id.in_(site_ids),
                    GiornaleCantiere.validato.is_(True),
                )
            )
        )
        giornali_validati = validati_result.scalar() or 0
        logger.info(f"🐛 [DEBUG] Found {giornali_validati} validated journals")

        response_data = {
            "siti_totali": siti_totali,
            "giornali_totali": giornali_totali,
            "giornali_validati": giornali_validati,
            "giornali_pendenti": giornali_totali - giornali_validati,
            "debug_info": f"Processed {len(site_ids)} sites"
        }
        
        logger.info(f"🐛 [DEBUG] v1_get_general_stats - SUCCESS: {response_data}")
        return response_data
        
    except Exception as e:
        # 🔍 DEBUG: Enhanced error logging
        logger.error(f"🐛 [DEBUG] v1_get_general_stats - ERROR: {str(e)}")
        logger.error(f"🐛 [DEBUG] Error type: {type(e).__name__}")
        import traceback
        logger.error(f"🐛 [DEBUG] Full traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel calcolo delle statistiche generali: {str(e)}",
        )

@router.get("/stats/site/{site_id}", summary="Statistiche sito specifico", tags=["Giornale di Cantiere - Stats"])
async def v1_get_site_stats(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera statistiche per un sito specifico.
    """
    try:
        # Verify site access
        site_info = verify_site_access(site_id, user_sites)

        # Count total journals for site
        totali_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                GiornaleCantiere.site_id == str(site_id)
            )
        )
        total_giornali = totali_result.scalar() or 0

        # Count validated journals
        validati_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                and_(
                    GiornaleCantiere.site_id == str(site_id),
                    GiornaleCantiere.validato.is_(True),
                )
            )
        )
        validated_giornali = validati_result.scalar() or 0

        # Count unique operators for site
        operatori_result = await db.execute(
            select(func.count(distinct(OperatoreCantiere.id)))
            .join(GiornaleCantiere.operatori)
            .where(GiornaleCantiere.site_id == str(site_id))
        )
        operatori_attivi = operatori_result.scalar() or 0

        validation_percentage = (
            round((validated_giornali / total_giornali) * 100) if total_giornali else 0
        )

        return {
            "total_giornali": total_giornali,
            "validated_giornali": validated_giornali,
            "pending_giornali": total_giornali - validated_giornali,
            "operatori_attivi": operatori_attivi,
            "validation_percentage": validation_percentage,
            "site_info": site_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore statistiche sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche del sito",
        )

@router.get("/stats/operatori", summary="Statistiche operatori", tags=["Giornale di Cantiere - Stats"])
async def v1_get_operatori_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera statistiche generali per gli operatori.
    """
    try:
        # Count total operators
        totali_result = await db.execute(select(func.count(OperatoreCantiere.id)))
        totali = totali_result.scalar() or 0

        # Count active operators (those who have worked on journals)
        attivi_result = await db.execute(
            select(func.count(distinct(OperatoreCantiere.id))).join(
                GiornaleCantiere.operatori
            )
        )
        attivi = attivi_result.scalar() or 0

        # Count specialized operators
        specialisti_result = await db.execute(
            select(func.count(OperatoreCantiere.id)).where(
                OperatoreCantiere.specializzazione.isnot(None)
            )
        )
        specialisti = specialisti_result.scalar() or 0

        # Count total hours
        ore_result = await db.execute(
            select(func.sum(OperatoreCantiere.ore_totali)).where(
                OperatoreCantiere.ore_totali.isnot(None)
            )
        )
        ore_totali = int(ore_result.scalar() or 0)

        return {
            "totali": totali,
            "attivi": attivi,
            "specialisti": specialisti,
            "ore_totali": ore_totali,
        }
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore statistiche operatori: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche operatori",
        )

@router.get("/operatori", summary="Lista tutti operatori", tags=["Giornale di Cantiere"])
async def v1_get_all_operatori(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    ruolo: Optional[str] = Query(None),
    specializzazione: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    site_id: Optional[UUID] = Query(None, description="Filtra operatori per sito specifico"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti gli operatori disponibili nel sistema.
    
    🔥 NUOVA LOGICA: Se specificato site_id, filtra solo operatori assegnati a quel sito.
    
    Args:
        skip: Numero di record da saltare (paginazione)
        limit: Numero massimo di record da restituire
        search: Testo di ricerca per nome, cognome o codice fiscale
        ruolo: Filtra per ruolo dell'operatore
        specializzazione: Filtra per specializzazione
        stato: Filtra per stato (attivo/inattivo)
        site_id: 🔥 NUOVO: Filtra operatori per sito specifico
    
    Returns:
        Lista di tutti gli operatori disponibili con metadati
    """
    try:
        # 🔥 NUOVA LOGICA: Verifica accesso al sito se specificato
        site_info = None
        if site_id:
            site_info = verify_site_access(site_id, user_sites)
        
        # Query base per operatori
        query = select(OperatoreCantiere)
        
        # 🔥 NUOVA LOGICA: Filtra per sito se specificato
        if site_id:
            query = query.where(OperatoreCantiere.site_id == str(site_id))
        
        # Applica filtri aggiuntivi
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    OperatoreCantiere.nome.ilike(search_pattern),
                    OperatoreCantiere.cognome.ilike(search_pattern),
                    OperatoreCantiere.codice_fiscale.ilike(search_pattern),
                )
            )
        if ruolo:
            query = query.where(OperatoreCantiere.ruolo == ruolo)
        if specializzazione:
            query = query.where(OperatoreCantiere.specializzazione == specializzazione)
        if stato:
            query = query.where(OperatoreCantiere.is_active == (stato == "attivo"))
        
        query = query.order_by(OperatoreCantiere.cognome, OperatoreCantiere.nome)
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        operatori = result.scalars().all()
        
        # Prepara dati di risposta
        operatori_data = []
        for op in operatori:
            operatore_dict = {
                "id": str(op.id),
                "nome": op.nome,
                "cognome": op.cognome,
                "codice_fiscale": op.codice_fiscale,
                "email": op.email,
                "telefono": op.telefono,
                "ruolo": op.ruolo,
                "specializzazione": op.specializzazione,
                "qualifiche": op.qualifica.split(",") if op.qualifica else [],
                "stato": "attivo" if op.is_active else "inattivo",
                "ore_totali": op.ore_totali or 0,
                "note": op.note,
            }
            
            # 🔥 NUOVO: Include site_id se disponibile
            if hasattr(op, 'site_id') and op.site_id:
                operatore_dict["site_id"] = str(op.site_id)
                operatore_dict["assigned_to_site"] = True
            else:
                operatore_dict["assigned_to_site"] = False
            
            operatori_data.append(operatore_dict)
        
        # 🔥 NUOVO: Include informazioni sul sito se filtrato
        response_data = operatori_data
        if site_id:
            response_data = {
                "site_id": str(site_id),
                "operatori": operatori_data,
                "count": len(operatori_data),
                "site_info": site_info,
                "filters_applied": {
                    "search": search,
                    "ruolo": ruolo,
                    "specializzazione": specializzazione,
                    "stato": stato
                }
            }
        
        return response_data
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore recupero operatori: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero degli operatori",
        )

# ===== PDF EXPORT ENDPOINTS =====

@router.get("/sites/{site_id}/cantieri/{cantiere_id}/export-pdf", summary="Esporta Giornali in PDF", tags=["Giornale di Cantiere - Export"])
async def export_giornali_pdf(
    site_id: UUID,
    cantiere_id: UUID,
    data_da: Optional[date] = Query(None, description="Data inizio filtro giornali"),
    data_a: Optional[date] = Query(None, description="Data fine filtro giornali"),
    include_allegati: bool = Query(False, description="Includi riferimenti allegati"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Esporta tutti i giornali di un cantiere in formato PDF conforme allo standard italiano.
    
    Il PDF generato segue il formato del giornale dei lavori standard con:
    - Intestazione con OGGETTO, COMMITTENTE, IMPRESA
    - Pagine multiple con paginazione
    - Voci giornaliere con data, meteo, temperatura
    - Descrizione lavori e eventi speciali
    - Elenco operatori con ore lavorate
    - Mezzi e attrezzature utilizzate
    - Sezioni firme
    
    Args:
        site_id: ID del sito archeologico
        cantiere_id: ID del cantiere specifico
        data_da: Filtra giornali da questa data (opzionale)
        data_a: Filtra giornali fino a questa data (opzionale)
        include_allegati: Include riferimenti agli allegati (default: False)
        
    Returns:
        Response: PDF file download
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Carica tutti i giornali del cantiere con filtri opzionali
        query = select(GiornaleCantiere).where(
            and_(
                GiornaleCantiere.site_id == str(site_id),
                GiornaleCantiere.cantiere_id == str(cantiere_id)
            )
        )
        
        # Applica filtri data se specificati
        if data_da:
            query = query.where(GiornaleCantiere.data >= data_da)
        if data_a:
            query = query.where(GiornaleCantiere.data <= data_a)
        
        # Load relationships
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori),
        )
        
        # Ordina per data
        query = query.order_by(GiornaleCantiere.data, GiornaleCantiere.created_at)
        
        result = await db.execute(query)
        giornali = result.scalars().all()
        
        if not giornali:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nessun giornale trovato per il periodo specificato"
            )
        
        # Carica informazioni del cantiere
        from app.models.cantiere import Cantiere
        cantiere_result = await db.execute(
            select(Cantiere).where(
                and_(
                    Cantiere.id == str(cantiere_id),
                    Cantiere.site_id == str(site_id)
                )
            )
        )
        cantiere = cantiere_result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Prepara dati per PDF
        giornali_data = []
        for g in giornali:
            # Ottieni dati operatori enhanced
            operatori_enhanced = await _get_enhanced_operator_data(db, g.id, g.operatori or [])
            
            giornale_dict = {
                "data": g.data.isoformat() if g.data else None,
                "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
                "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
                "responsabile_scavo": g.responsabile_nome or (g.responsabile.email if g.responsabile else None),
                "compilatore": g.compilatore or g.responsabile_nome,
                "condizioni_meteo": g.condizioni_meteo,
                "temperatura": g.temperatura,
                "temperatura_min": g.temperatura_min,
                "temperatura_max": g.temperatura_max,
                "note_meteo": g.note_meteo,
                "descrizione_lavori": g.descrizione_lavori,
                "modalita_lavorazioni": g.modalita_lavorazioni,
                "attrezzatura_utilizzata": g.attrezzatura_utilizzata,
                "mezzi_utilizzati": g.mezzi_utilizzati,
                "materiali_rinvenuti": g.materiali_rinvenuti,
                "documentazione_prodotta": g.documentazione_prodotta,
                "sopralluoghi": g.sopralluoghi,
                "disposizioni_rup": g.disposizioni_rup,
                "disposizioni_direttore": g.disposizioni_direttore,
                "contestazioni": g.contestazioni,
                "sospensioni": g.sospensioni,
                "incidenti": g.incidenti,
                "forniture": g.forniture,
                "note_generali": g.note_generali,
                "problematiche": g.problematiche,
                "operatori_presenti": operatori_enhanced,
                "us_elaborate": g.get_us_list() if hasattr(g, "get_us_list") else [],
                "usm_elaborate": g.get_usm_list() if hasattr(g, "get_usm_list") else [],
                "usr_elaborate": g.usr_elaborate.split(",") if g.usr_elaborate else [],
                "validato": g.validato,
                "data_validazione": g.data_validazione.isoformat() if g.data_validazione else None,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            }
            
            # Includi allegati se richiesto
            if include_allegati and g.allegati_paths:
                try:
                    import json
                    allegati = json.loads(g.allegati_paths)
                    giornale_dict["allegati_paths"] = allegati
                except:
                    giornale_dict["allegati_paths"] = []
            
            giornali_data.append(giornale_dict)
        
        # Prepara informazioni cantiere
        cantiere_info = {
            "nome": cantiere.nome,
            "codice": cantiere.codice,
            "descrizione": cantiere.descrizione or "",
            "oggetto_appalto": cantiere.oggetto_appalto or "",
            "committente": cantiere.committente or "",
            "impresa_esecutrice": cantiere.impresa_esecutrice or "",
            "direttore_lavori": cantiere.direttore_lavori or "",
            "responsabile_procedimento": cantiere.responsabile_procedimento or "",
        }
        
        # Importa servizio PDF
        from app.services.giornale_pdf_service import generate_giornale_pdf_quick
        
        # Genera PDF
        logger.info(f"Generating PDF for cantiere {cantiere.nome} with {len(giornali_data)} giornali")
        pdf_content = generate_giornale_pdf_quick(giornali_data, cantiere_info, site_info)
        
        # Prepara nome file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{cantiere.nome.replace(' ', '_')}_{timestamp}.pdf"
        
        logger.info(f"PDF generated successfully: {len(pdf_content)} bytes")
        
        # Return PDF response
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(pdf_content))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating giornale PDF: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella generazione del PDF: {str(e)}"
        )

@router.get("/sites/{site_id}/giornali/{giornale_id}/export-pdf", summary="Esporta Singolo Giornale in PDF", tags=["Giornale di Cantiere - Export"])
async def export_single_giornale_pdf(
    site_id: UUID,
    giornale_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Esporta un singolo giornale in formato PDF.
    
    Args:
        site_id: ID del sito archeologico
        giornale_id: ID del giornale specifico
        
    Returns:
        Response: PDF file download
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Carica giornale specifico
        result = await db.execute(
            select(GiornaleCantiere).where(
                and_(
                    GiornaleCantiere.id == str(giornale_id),
                    GiornaleCantiere.site_id == str(site_id)
                )
            ).options(
                selectinload(GiornaleCantiere.site),
                selectinload(GiornaleCantiere.responsabile),
                selectinload(GiornaleCantiere.operatori),
                selectinload(GiornaleCantiere.cantiere)
            )
        )
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Carica informazioni cantiere
        cantiere = giornale.cantiere
        
        # Prepara dati per PDF
        operatori_enhanced = await _get_enhanced_operator_data(db, giornale.id, giornale.operatori or [])
        
        giornale_dict = {
            "data": giornale.data.isoformat() if giornale.data else None,
            "ora_inizio": giornale.ora_inizio.strftime("%H:%M") if giornale.ora_inizio else None,
            "ora_fine": giornale.ora_fine.strftime("%H:%M") if giornale.ora_fine else None,
            "responsabile_scavo": giornale.responsabile_nome or (giornale.responsabile.email if giornale.responsabile else None),
            "compilatore": giornale.compilatore or giornale.responsabile_nome,
            "condizioni_meteo": giornale.condizioni_meteo,
            "temperatura": giornale.temperatura,
            "temperatura_min": giornale.temperatura_min,
            "temperatura_max": giornale.temperatura_max,
            "note_meteo": giornale.note_meteo,
            "descrizione_lavori": giornale.descrizione_lavori,
            "modalita_lavorazioni": giornale.modalita_lavorazioni,
            "attrezzatura_utilizzata": giornale.attrezzatura_utilizzata,
            "mezzi_utilizzati": giornale.mezzi_utilizzati,
            "materiali_rinvenuti": giornale.materiali_rinvenuti,
            "documentazione_prodotta": giornale.documentazione_prodotta,
            "sopralluoghi": giornale.sopralluoghi,
            "disposizioni_rup": giornale.disposizioni_rup,
            "disposizioni_direttore": giornale.disposizioni_direttore,
            "contestazioni": giornale.contestazioni,
            "sospensioni": giornale.sospensioni,
            "incidenti": giornale.incidenti,
            "forniture": giornale.forniture,
            "note_generali": giornale.note_generali,
            "problematiche": giornale.problematiche,
            "operatori_presenti": operatori_enhanced,
            "us_elaborate": giornale.get_us_list() if hasattr(giornale, "get_us_list") else [],
            "usm_elaborate": giornale.get_usm_list() if hasattr(giornale, "get_usm_list") else [],
            "usr_elaborate": giornale.usr_elaborate.split(",") if giornale.usr_elaborate else [],
            "validato": giornale.validato,
            "data_validazione": giornale.data_validazione.isoformat() if giornale.data_validazione else None,
            "created_at": giornale.created_at.isoformat() if giornale.created_at else None,
            "updated_at": giornale.updated_at.isoformat() if giornale.updated_at else None,
        }
        
        # Prepara informazioni cantiere
        cantiere_info = {
            "nome": cantiere.nome if cantiere else "Cantiere Sconosciuto",
            "codice": cantiere.codice if cantiere else "",
            "descrizione": cantiere.descrizione or "" if cantiere else "",
            "oggetto_appalto": cantiere.oggetto_appalto or "" if cantiere else "",
            "committente": cantiere.committente or "" if cantiere else "",
            "impresa_esecutrice": cantiere.impresa_esecutrice or "" if cantiere else "",
            "direttore_lavori": cantiere.direttore_lavori or "" if cantiere else "",
            "responsabile_procedimento": cantiere.responsabile_procedimento or "" if cantiere else "",
        }
        
        # Importa servizio PDF
        from app.services.giornale_pdf_service import generate_giornale_pdf_quick
        
        # Genera PDF
        logger.info(f"Generating PDF for single giornale {giornale_id}")
        pdf_content = generate_giornale_pdf_quick([giornale_dict], cantiere_info, site_info)
        
        # Prepara nome file
        data_giornale = giornale.data.strftime("%d_%m_%Y") if giornale.data else "sdata"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{cantiere_info['nome'].replace(' ', '_')}_{data_giornale}_{timestamp}.pdf"
        
        logger.info(f"Single giornale PDF generated successfully: {len(pdf_content)} bytes")
        
        # Return PDF response
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(pdf_content))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating single giornale PDF: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella generazione del PDF: {str(e)}"
        )

# ===== WORD EXPORT ENDPOINTS =====

@router.get("/sites/{site_id}/cantieri/{cantiere_id}/export-word", summary="Esporta Giornali in Word", tags=["Giornale di Cantiere - Export"])
async def export_giornali_word(
    site_id: UUID,
    cantiere_id: UUID,
    data_da: Optional[date] = Query(None, description="Data inizio filtro giornali"),
    data_a: Optional[date] = Query(None, description="Data fine filtro giornali"),
    include_allegati: bool = Query(False, description="Includi riferimenti allegati"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Esporta tutti i giornali di un cantiere in formato Word (.docx).
    
    Il documento Word generato segue lo stesso formato del giornale dei lavori standard
    con la possibilità di essere modificato e personalizzato dall'utente.
    
    Args:
        site_id: ID del sito archeologico
        cantiere_id: ID del cantiere specifico
        data_da: Filtra giornali da questa data (opzionale)
        data_a: Filtra giornali fino a questa data (opzionale)
        include_allegati: Include riferimenti agli allegati (default: False)
        
    Returns:
        Response: Word (.docx) file download
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Carica tutti i giornali del cantiere con filtri opzionali
        query = select(GiornaleCantiere).where(
            and_(
                GiornaleCantiere.site_id == str(site_id),
                GiornaleCantiere.cantiere_id == str(cantiere_id)
            )
        )
        
        # Applica filtri data se specificati
        if data_da:
            query = query.where(GiornaleCantiere.data >= data_da)
        if data_a:
            query = query.where(GiornaleCantiere.data <= data_a)
        
        # Load relationships
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori),
        )
        
        # Ordina per data
        query = query.order_by(GiornaleCantiere.data, GiornaleCantiere.created_at)
        
        result = await db.execute(query)
        giornali = result.scalars().all()
        
        if not giornali:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nessun giornale trovato per il periodo specificato"
            )
        
        # Carica informazioni del cantiere
        from app.models.cantiere import Cantiere
        cantiere_result = await db.execute(
            select(Cantiere).where(
                and_(
                    Cantiere.id == str(cantiere_id),
                    Cantiere.site_id == str(site_id)
                )
            )
        )
        cantiere = cantiere_result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Prepara dati per Word (stessi dati del PDF)
        giornali_data = []
        for g in giornali:
            # Ottieni dati operatori enhanced
            operatori_enhanced = await _get_enhanced_operator_data(db, g.id, g.operatori or [])
            
            giornale_dict = {
                "data": g.data.isoformat() if g.data else None,
                "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
                "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
                "responsabile_scavo": g.responsabile_nome or (g.responsabile.email if g.responsabile else None),
                "compilatore": g.compilatore or g.responsabile_nome,
                "condizioni_meteo": g.condizioni_meteo,
                "temperatura": g.temperatura,
                "temperatura_min": g.temperatura_min,
                "temperatura_max": g.temperatura_max,
                "note_meteo": g.note_meteo,
                "descrizione_lavori": g.descrizione_lavori,
                "modalita_lavorazioni": g.modalita_lavorazioni,
                "attrezzatura_utilizzata": g.attrezzatura_utilizzata,
                "mezzi_utilizzati": g.mezzi_utilizzati,
                "materiali_rinvenuti": g.materiali_rinvenuti,
                "documentazione_prodotta": g.documentazione_prodotta,
                "sopralluoghi": g.sopralluoghi,
                "disposizioni_rup": g.disposizioni_rup,
                "disposizioni_direttore": g.disposizioni_direttore,
                "contestazioni": g.contestazioni,
                "sospensioni": g.sospensioni,
                "incidenti": g.incidenti,
                "forniture": g.forniture,
                "note_generali": g.note_generali,
                "problematiche": g.problematiche,
                "operatori_presenti": operatori_enhanced,
                "us_elaborate": g.get_us_list() if hasattr(g, "get_us_list") else [],
                "usm_elaborate": g.get_usm_list() if hasattr(g, "get_usm_list") else [],
                "usr_elaborate": g.usr_elaborate.split(",") if g.usr_elaborate else [],
                "validato": g.validato,
                "data_validazione": g.data_validazione.isoformat() if g.data_validazione else None,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            }
            
            # Includi allegati se richiesto
            if include_allegati and g.allegati_paths:
                try:
                    import json
                    allegati = json.loads(g.allegati_paths)
                    giornale_dict["allegati_paths"] = allegati
                except:
                    giornale_dict["allegati_paths"] = []
            
            giornali_data.append(giornale_dict)
        
        # Prepara informazioni cantiere
        cantiere_info = {
            "nome": cantiere.nome,
            "codice": cantiere.codice,
            "descrizione": cantiere.descrizione or "",
            "oggetto_appalto": cantiere.oggetto_appalto or "",
            "committente": cantiere.committente or "",
            "impresa_esecutrice": cantiere.impresa_esecutrice or "",
            "direttore_lavori": cantiere.direttore_lavori or "",
            "responsabile_procedimento": cantiere.responsabile_procedimento or "",
        }
        
        # Importa servizio Word
        from app.services.giornale_word_service import generate_giornale_word_quick
        
        # Genera Word
        logger.info(f"Generating Word document for cantiere {cantiere.nome} with {len(giornali_data)} giornali")
        word_content = generate_giornale_word_quick(giornali_data, cantiere_info, site_info)
        
        # Prepara nome file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{cantiere.nome.replace(' ', '_')}_{timestamp}.docx"
        
        logger.info(f"Word document generated successfully: {len(word_content)} bytes")
        
        # Return Word response
        return Response(
            content=word_content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(word_content))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating giornale Word document: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella generazione del documento Word: {str(e)}"
        )

@router.get("/sites/{site_id}/giornali/{giornale_id}/export-word", summary="Esporta Singolo Giornale in Word", tags=["Giornale di Cantiere - Export"])
async def export_single_giornale_word(
    site_id: UUID,
    giornale_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Esporta un singolo giornale in formato Word (.docx).
    
    Args:
        site_id: ID del sito archeologico
        giornale_id: ID del giornale specifico
        
    Returns:
        Response: Word (.docx) file download
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Carica giornale specifico
        result = await db.execute(
            select(GiornaleCantiere).where(
                and_(
                    GiornaleCantiere.id == str(giornale_id),
                    GiornaleCantiere.site_id == str(site_id)
                )
            ).options(
                selectinload(GiornaleCantiere.site),
                selectinload(GiornaleCantiere.responsabile),
                selectinload(GiornaleCantiere.operatori),
                selectinload(GiornaleCantiere.cantiere)
            )
        )
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Carica informazioni cantiere
        cantiere = giornale.cantiere
        
        # Prepara dati per Word (stessi dati del PDF)
        operatori_enhanced = await _get_enhanced_operator_data(db, giornale.id, giornale.operatori or [])
        
        giornale_dict = {
            "data": giornale.data.isoformat() if giornale.data else None,
            "ora_inizio": giornale.ora_inizio.strftime("%H:%M") if giornale.ora_inizio else None,
            "ora_fine": giornale.ora_fine.strftime("%H:%M") if giornale.ora_fine else None,
            "responsabile_scavo": giornale.responsabile_nome or (giornale.responsabile.email if giornale.responsabile else None),
            "compilatore": giornale.compilatore or giornale.responsabile_nome,
            "condizioni_meteo": giornale.condizioni_meteo,
            "temperatura": giornale.temperatura,
            "temperatura_min": giornale.temperatura_min,
            "temperatura_max": giornale.temperatura_max,
            "note_meteo": giornale.note_meteo,
            "descrizione_lavori": giornale.descrizione_lavori,
            "modalita_lavorazioni": giornale.modalita_lavorazioni,
            "attrezzatura_utilizzata": giornale.attrezzatura_utilizzata,
            "mezzi_utilizzati": giornale.mezzi_utilizzati,
            "materiali_rinvenuti": giornale.materiali_rinvenuti,
            "documentazione_prodotta": giornale.documentazione_prodotta,
            "sopralluoghi": giornale.sopralluoghi,
            "disposizioni_rup": giornale.disposizioni_rup,
            "disposizioni_direttore": giornale.disposizioni_direttore,
            "contestazioni": giornale.contestazioni,
            "sospensioni": giornale.sospensioni,
            "incidenti": giornale.incidenti,
            "forniture": giornale.forniture,
            "note_generali": giornale.note_generali,
            "problematiche": giornale.problematiche,
            "operatori_presenti": operatori_enhanced,
            "us_elaborate": giornale.get_us_list() if hasattr(giornale, "get_us_list") else [],
            "usm_elaborate": giornale.get_usm_list() if hasattr(giornale, "get_usm_list") else [],
            "usr_elaborate": giornale.usr_elaborate.split(",") if giornale.usr_elaborate else [],
            "validato": giornale.validato,
            "data_validazione": giornale.data_validazione.isoformat() if giornale.data_validazione else None,
            "created_at": giornale.created_at.isoformat() if giornale.created_at else None,
            "updated_at": giornale.updated_at.isoformat() if giornale.updated_at else None,
        }
        
        # Prepara informazioni cantiere
        cantiere_info = {
            "nome": cantiere.nome if cantiere else "Cantiere Sconosciuto",
            "codice": cantiere.codice if cantiere else "",
            "descrizione": cantiere.descrizione or "" if cantiere else "",
            "oggetto_appalto": cantiere.oggetto_appalto or "" if cantiere else "",
            "committente": cantiere.committente or "" if cantiere else "",
            "impresa_esecutrice": cantiere.impresa_esecutrice or "" if cantiere else "",
            "direttore_lavori": cantiere.direttore_lavori or "" if cantiere else "",
            "responsabile_procedimento": cantiere.responsabile_procedimento or "" if cantiere else "",
        }
        
        # Importa servizio Word
        from app.services.giornale_word_service import generate_giornale_word_quick
        
        # Genera Word
        logger.info(f"Generating Word document for single giornale {giornale_id}")
        word_content = generate_giornale_word_quick([giornale_dict], cantiere_info, site_info)
        
        # Prepara nome file
        data_giornale = giornale.data.strftime("%d_%m_%Y") if giornale.data else "sdata"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{cantiere_info['nome'].replace(' ', '_')}_{data_giornale}_{timestamp}.docx"
        
        logger.info(f"Single giornale Word document generated successfully: {len(word_content)} bytes")
        
        # Return Word response
        return Response(
            content=word_content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(word_content))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating single giornale Word document: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella generazione del documento Word: {str(e)}"
        )