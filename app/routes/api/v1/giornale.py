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

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )
    
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

@router.get("/sites/{site_id}", summary="Lista giornali sito", tags=["Giornale di Cantiere"])
async def v1_get_site_giornali(
    site_id: UUID,
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
    Recupera tutti i giornali di cantiere di un sito con filtri avanzati.
    
    Args:
        site_id: ID del sito archeologico
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

        # Query base
        query = select(GiornaleCantiere).where(GiornaleCantiere.site_id == site_id)

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
                "operatori_presenti": [
                    {
                        "id": str(op.id),
                        "nome": op.nome,
                        "cognome": op.cognome,
                        "ruolo": op.ruolo,
                    }
                    for op in (g.operatori or [])
                ],
                "note_generali": g.note_generali,
                "problematiche": g.problematiche,
                "compilatore": g.compilatore or g.responsabile_nome,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
                "version": g.version or 1,
            }
            giornali_data.append(giornale_dict)

        return {
            "site_id": str(site_id),
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
        logger.error(f"Errore recupero giornali sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei giornali",
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
                "/api/giornale-cantiere/operatori/site/{site_id}": "/api/v1/giornale/sites/{site_id}/operatori"
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
    Recupera gli operatori specifici per un sito archeologico.
    Filtra gli operatori che hanno lavorato su giornali di questo sito.
    
    Args:
        site_id: ID del sito archeologico
        skip: Numero di record da saltare (paginazione)
        limit: Numero massimo di record da restituire
        search: Testo di ricerca per nome, cognome o codice fiscale
        ruolo: Filtra per ruolo dell'operatore
        specializzazione: Filtra per specializzazione
        stato: Filtra per stato (attivo/inattivo)
    
    Returns:
        Lista di operatori specifici per il sito con metadati
    """
    from app.models.giornale_cantiere import (
        GiornaleCantiere,
        OperatoreCantiere,
        giornale_operatori_association
    )
    from sqlalchemy import select, func, or_, and_
    from sqlalchemy.orm import selectinload
    
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Query per trovare operatori che hanno lavorato su giornali di questo sito
        site_operatori_subquery = (
            select(giornale_operatori_association.c.operatore_id)
            .join(GiornaleCantiere, giornale_operatori_association.c.giornale_id == GiornaleCantiere.id)
            .where(GiornaleCantiere.site_id == site_id)
            .distinct()
            .subquery()
        )
        
        query = select(OperatoreCantiere).where(
            OperatoreCantiere.id.in_(site_operatori_subquery)
        )
        
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
        
        # Conteggio giornali per ogni operatore in questo sito
        operatori_data = []
        for op in operatori:
            # Query per contare i giornali di questo sito dove questo operatore ha lavorato
            giornali_count_result = await db.execute(
                select(func.count(GiornaleCantiere.id))
                .join(giornale_operatori_association, GiornaleCantiere.id == giornale_operatori_association.c.giornale_id)
                .where(
                    and_(
                        GiornaleCantiere.site_id == site_id,
                        giornale_operatori_association.c.operatore_id == op.id
                    )
                )
            )
            giornali_count = giornali_count_result.scalar() or 0
            
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
                "giornali_count": giornali_count,  # Solo per questo sito
                "site_id": str(site_id),
                "note": op.note,
            })
        
        return {
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
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore recupero operatori sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero degli operatori del sito",
        )