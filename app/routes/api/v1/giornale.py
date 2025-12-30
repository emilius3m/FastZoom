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
from app.services.giornale_service import GiornaleService

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
    
    Handles various UUID formats for comparison
    """
    from loguru import logger
    
    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(str(site_id))
    if not normalized_site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID sito non valido: {site_id}"
        )
    
    # Enhanced matching with multiple format variations
    site_info = None
    for site in user_sites:
        if not site.get("site_id"):
            continue
        
        site_user_id = str(site["site_id"])
        
        # Try multiple matching strategies with normalized ID
        if (site_user_id == normalized_site_id or
            site_user_id == str(site_id) or
            site_user_id.replace("-", "") == normalized_site_id.replace("-", "")):
        
            site_info = site
            break
    
    if not site_info:
        logger.warning(f"Site access denied: site_id={site_id}, user has {len(user_sites)} accessible sites")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied. User has access to {len(user_sites)} sites."
        )
    
    logger.debug(f"Site access verified: {site_info.get('site_name', 'Unknown')}")
    return site_info

# Import required models and schemas
from app.models.giornale_cantiere import (
    GiornaleCantiere,
    OperatoreCantiere,
    giornale_operatori_association,
    giornale_foto_association,
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


# Helper removed - moved to Repository

@router.get("/sites/{site_id}/giornali", summary="Lista giornali sito", tags=["Giornale di Cantiere"])
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
    """
    try:
        # Validate user_sites before proceeding
        if not user_sites:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no accessible sites. Please contact administrator."
            )
        
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)

        filters = {
            "data_da": data_da,
            "data_a": data_a,
            "responsabile": responsabile,
            "stato": stato,
            "cantiere_id": cantiere_id
        }
        
        service = GiornaleService(db)
        result = await service.list_giornali(site_id, skip, limit, filters)

        return {
            "site_id": str(site_id),
            "giornali": result["data"],
            "count": result["count"],
            "site_info": site_info,
            "filters_applied": {
                "data_da": data_da.isoformat() if data_da else None,
                "data_a": data_a.isoformat() if data_a else None,
                "responsabile": responsabile,
                "stato": stato,
                "cantiere_id": str(cantiere_id) if cantiere_id else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore recupero giornali sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero dei giornali: {str(e)}",
        )

@router.get("/sites/{site_id}/cantieri/{cantiere_id}/giornali", summary="Giornali cantiere", tags=["Giornale di Cantiere"])
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
    """Recupera giornali di un cantiere specifico"""
    try:
        site_info = verify_site_access(site_id, user_sites)
        
        filters = {
            "data_da": data_da,
            "data_a": data_a,
            "responsabile": responsabile,
            "stato": stato,
            "cantiere_id": cantiere_id
        }
        
        service = GiornaleService(db)
        result = await service.list_giornali(site_id, skip, limit, filters)
        
        return {
            "site_id": str(site_id),
            "cantiere_id": str(cantiere_id),
            "giornali": result["data"],
            "count": result["count"],
            "site_info": site_info,
            "filters_applied": {
                "data_da": data_da.isoformat() if data_da else None,
                "data_a": data_a.isoformat() if data_a else None,
                "responsabile": responsabile,
                "stato": stato
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore recupero giornali cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        nuovo_giornale = await service.create_giornale(site_id, giornale_data, current_user_id)
        
        return {
            "id": str(nuovo_giornale.id),
            "message": "Giornale creato con successo",
            "site_info": site_info,
            "operatori_validati": len(giornale_data.get("operatori", []))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore creazione giornale: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nella creazione del giornale")

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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        giornale = await service.update_giornale(site_id, giornale_id, giornale_data)

        return {
            "id": str(giornale.id),
            "message": "Giornale aggiornato con successo",
            "site_info": site_info,
            "operatori_validati": len(giornale_data.get("operatori", [])) if "operatori" in giornale_data else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento giornale: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nell'aggiornamento del giornale")

@router.post("/sites/{site_id}/giornali/{giornale_id}/validate", summary="Valida giornale", tags=["Giornale di Cantiere"])
async def v1_validate_giornale(
    site_id: UUID,
    giornale_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Valida un giornale di cantiere, rendendolo non modificabile.
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        giornale = await service.validate_giornale(site_id, giornale_id)
        
        return {
            "id": str(giornale.id),
            "message": "Giornale validato con successo",
            "data_validazione": giornale.data_validazione.isoformat(),
            "validato": True
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore validazione giornale: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nella validazione del giornale")

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
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        await service.delete_giornale(site_id, giornale_id)
        
        return {
            "message": "Giornale eliminato con successo",
            "site_info": site_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione giornale: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nell'eliminazione del giornale")

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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        
        filters = {
            "search": search,
            "ruolo": ruolo,
            "specializzazione": specializzazione,
            "stato": stato
        }
        
        service = GiornaleService(db)
        result = await service.list_site_operators(site_id, skip, limit, filters)
        
        return {
            "site_id": str(site_id),
            "operatori": result["data"],
            "count": result["count"],
            "site_info": site_info,
            "filters_applied": filters
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore recupero operatori sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero degli operatori del sito",
        )

@router.get("/sites/{site_id}/operatori/export-pdf", summary="Esporta Operatori in PDF", tags=["Giornale di Cantiere - Export"])
async def export_site_operatori_pdf(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Esporta la lista degli operatori del sito in formato PDF.
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        
        service = GiornaleService(db)
        # Fetch all operators (unlimited)
        result = await service.list_site_operators(site_id, skip=0, limit=10000)
        operatori_data = result["data"]
        
        from app.services.giornale_pdf_service import generate_operatori_pdf_quick
        pdf_content = generate_operatori_pdf_quick(operatori_data, site_info)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        site_name_safe = site_info.get('name', 'Sito').replace(' ', '_')
        filename = f"Operatori_{site_name_safe}_{timestamp}.pdf"
        
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
        logger.error(f"Errore generazione PDF operatori: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella generazione del PDF: {str(e)}"
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
                site_id_str = str(site["site_id"])
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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        
        service = GiornaleService(db)
        filters = {
            "cantiere_id": str(cantiere_id),
            "data_da": data_da,
            "data_a": data_a
        }
        
        # Fetch data via service (unlimited limit for export)
        result = await service.list_giornali(site_id, skip=0, limit=10000, filters=filters)
        giornali_data = result["data"]
        
        if not giornali_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nessun giornale trovato per il periodo specificato"
            )
            
        # Get cantiere info from first record
        cantiere_info = giornali_data[0].get("cantiere")
        if not cantiere_info:
             # Fallback if somehow missing
             from app.models.cantiere import Cantiere
             c_res = await db.execute(select(Cantiere).where(Cantiere.id == str(cantiere_id)))
             c = c_res.scalar_one_or_none()
             if not c:
                 raise HTTPException(status_code=404, detail="Cantiere non trovato")
             cantiere_info = {"nome": c.nome, "codice": c.codice} # Minimal fallback

        # Process attachments if requested
        if include_allegati:
            import json
            for g in giornali_data:
                if g.get("allegati_paths"):
                    try:
                        g["allegati_paths"] = json.loads(g["allegati_paths"])
                    except:
                        g["allegati_paths"] = []
                        
        # Genera PDF
        from app.services.giornale_pdf_service import generate_giornale_pdf_quick
        logger.info(f"Generating PDF for cantiere {cantiere_info.get('nome')} with {len(giornali_data)} giornali")
        pdf_content = generate_giornale_pdf_quick(giornali_data, cantiere_info, site_info)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{cantiere_info.get('nome', 'Cantiere').replace(' ', '_')}_{timestamp}.pdf"
        
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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        
        # Fetch formatted giornale
        giornale_dict = await service.get_giornale(site_id, giornale_id)
        
        cantiere_info = giornale_dict.get("cantiere")
        if not cantiere_info:
             # Fallback
             cantiere_info = {
                "nome": "Cantiere Sconosciuto",
                "codice": "",
                "descrizione": "",
                "oggetto_appalto": "",
                "committente": "",
                "impresa_esecutrice": "",
                "direttore_lavori": "",
                "responsabile_procedimento": ""
            }

        # Genera PDF
        from app.services.giornale_pdf_service import generate_giornale_pdf_quick
        pdf_content = generate_giornale_pdf_quick([giornale_dict], cantiere_info, site_info)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{timestamp}.pdf"
        
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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        filters = {
            "cantiere_id": str(cantiere_id),
            "data_da": data_da,
            "data_a": data_a
        }
        
        result = await service.list_giornali(site_id, skip=0, limit=10000, filters=filters)
        giornali_data = result["data"]
        
        if not giornali_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nessun giornale trovato per il periodo specificato"
            )
            
        cantiere_info = giornali_data[0].get("cantiere")
        if not cantiere_info:
             # Fallback
             from app.models.cantiere import Cantiere
             c_res = await db.execute(select(Cantiere).where(Cantiere.id == str(cantiere_id)))
             c = c_res.scalar_one_or_none()
             if not c:
                 raise HTTPException(status_code=404, detail="Cantiere non trovato")
             cantiere_info = {"nome": c.nome, "codice": c.codice}

        if include_allegati:
            import json
            for g in giornali_data:
                if g.get("allegati_paths"):
                    try:
                        g["allegati_paths"] = json.loads(g["allegati_paths"])
                    except:
                        g["allegati_paths"] = []

        from app.services.giornale_word_service import generate_giornale_word_quick
        word_content = generate_giornale_word_quick(giornali_data, cantiere_info, site_info)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{cantiere_info.get('nome', 'Cantiere').replace(' ', '_')}_{timestamp}.docx"
        
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
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        
        giornale_dict = await service.get_giornale(site_id, giornale_id)
        
        cantiere_info = giornale_dict.get("cantiere")
        if not cantiere_info:
             cantiere_info = {
                "nome": "Cantiere Sconosciuto",
                "codice": "",
                "descrizione": "",
                "oggetto_appalto": "",
                "committente": "",
                "impresa_esecutrice": "",
                "direttore_lavori": "",
                "responsabile_procedimento": ""
            }

        from app.services.giornale_word_service import generate_giornale_word_quick
        word_content = generate_giornale_word_quick([giornale_dict], cantiere_info, site_info)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Giornale_{timestamp}.docx"
        
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella generazione del documento Word: {str(e)}"
        )


# ===== GESTIONE FOTO GIORNALE =====

@router.post("/sites/{site_id}/giornali/{giornale_id}/foto/{foto_id}", summary="Link foto a giornale", tags=["Giornale di Cantiere"])
async def v1_link_foto_to_giornale(
    site_id: UUID,
    giornale_id: UUID,
    foto_id: UUID,
    didascalia: Optional[str] = None,
    ordine: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Collega una foto esistente al giornale di cantiere con didascalia opzionale.
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        await service.link_photo(site_id, giornale_id, foto_id, didascalia, ordine)
        
        return {
            "message": "Foto collegata con successo",
            "giornale_id": str(giornale_id),
            "foto_id": str(foto_id),
            "didascalia": didascalia
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore collegamento foto a giornale: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel collegamento della foto")


@router.delete("/sites/{site_id}/giornali/{giornale_id}/foto/{foto_id}", summary="Scollega foto da giornale", tags=["Giornale di Cantiere"])
async def v1_unlink_foto_from_giornale(
    site_id: UUID,
    giornale_id: UUID,
    foto_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Scollega una foto dal giornale (non elimina la foto).
    """
    try:
        site_info = verify_site_access(site_id, user_sites)
        service = GiornaleService(db)
        await service.unlink_photo(site_id, giornale_id, foto_id)
        
        return {
            "message": "Foto scollegata con successo",
            "giornale_id": str(giornale_id),
            "foto_id": str(foto_id)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore scollegamento foto da giornale: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nello scollegamento della foto")


@router.put("/sites/{site_id}/giornali/{giornale_id}/foto/{foto_id}", summary="Aggiorna didascalia foto", tags=["Giornale di Cantiere"])
async def v1_update_foto_didascalia(
    site_id: UUID,
    giornale_id: UUID,
    foto_id: UUID,
    update_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna didascalia e ordine di una foto nel giornale.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Prepara i valori da aggiornare
        update_values = {}
        if "didascalia" in update_data:
            update_values["didascalia"] = update_data["didascalia"]
        if "ordine" in update_data:
            update_values["ordine"] = update_data["ordine"]
        
        if not update_values:
            raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
        
        # Aggiorna l'associazione
        result = await db.execute(
            giornale_foto_association.update()
            .where(
                and_(
                    giornale_foto_association.c.giornale_id == str(giornale_id),
                    giornale_foto_association.c.foto_id == str(foto_id)
                )
            )
            .values(**update_values)
        )
        await db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Associazione foto-giornale non trovata")
        
        return {
            "message": "Didascalia aggiornata con successo",
            "giornale_id": str(giornale_id),
            "foto_id": str(foto_id),
            "updated_fields": list(update_values.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento didascalia foto: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nell'aggiornamento della didascalia")