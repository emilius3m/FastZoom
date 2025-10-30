"""
API v1 - Cantieri (Work Sites) Management
Endpoints per gestione cantieri all'interno di siti archeologici.
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

# Import association table for operatori
from app.models.giornale_cantiere import giornale_operatori_association

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

# Import required models
from app.models.cantiere import Cantiere
from app.models.sites import ArchaeologicalSite
from app.models.giornale_cantiere import GiornaleCantiere
from datetime import date
from sqlalchemy import select, func, and_, or_, desc, distinct
from sqlalchemy.orm import selectinload

@router.get("/sites/{site_id}", summary="Lista cantieri sito", tags=["Cantieri"])
async def v1_get_cantieri_sito_direct(
    site_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti i cantieri di un sito archeologico.
    Endpoint principale per compatibilità con frontend.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Query base
        query = select(Cantiere).where(
            and_(Cantiere.site_id == site_id, Cantiere.is_active == True)
        )
        
        # Applica filtri
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Cantiere.nome.ilike(search_pattern),
                    Cantiere.codice.ilike(search_pattern),
                    Cantiere.descrizione.ilike(search_pattern)
                )
            )
        if stato:
            query = query.where(Cantiere.stato == stato)
        
        # Ordinamento e paginazione
        query = query.order_by(
            Cantiere.priorita.asc(), Cantiere.created_at.desc()
        )
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        cantieri = result.scalars().all()
        
        # Prepara dati di risposta
        cantieri_data = []
        for cantiere in cantieri:
            # Conteggio giornali per ogni cantiere
            giornali_count_result = await db.execute(
                select(func.count(GiornaleCantiere.id)).where(
                    GiornaleCantiere.cantiere_id == cantiere.id
                )
            )
            giornali_count = giornali_count_result.scalar() or 0
            
            cantieri_data.append({
                "id": str(cantiere.id),
                "nome": cantiere.nome,
                "codice": cantiere.codice,
                "stato": cantiere.stato,
                "giornali_count": giornali_count,
                "site_info": site_info
            })
        
        return {
            "site_id": str(site_id),
            "cantieri": cantieri_data,
            "count": len(cantieri_data),
            "site_info": site_info
        }
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore recupero cantieri sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei cantieri"
        )

@router.get("/sites/{site_id}/cantieri", summary="Lista cantieri sito", tags=["Cantieri"])
async def v1_get_cantieri_sito(
    site_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera tutti i cantieri di un sito archeologico.
    
    Args:
        site_id: ID del sito archeologico
        skip: Numero di record da saltare (paginazione)
        limit: Numero massimo di record da restituire
        search: Testo di ricerca per nome o codice
        stato: Filtra per stato del cantiere
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Query base
        query = select(Cantiere).where(
            and_(Cantiere.site_id == site_id, Cantiere.is_active == True)
        )
        
        # Applica filtri
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Cantiere.nome.ilike(search_pattern),
                    Cantiere.codice.ilike(search_pattern),
                    Cantiere.descrizione.ilike(search_pattern)
                )
            )
        if stato:
            query = query.where(Cantiere.stato == stato)
        
        # Ordinamento e paginazione
        query = query.order_by(
            Cantiere.priorita.asc(), Cantiere.created_at.desc()
        )
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        cantieri = result.scalars().all()
        
        # Prepara dati di risposta
        cantieri_data = []
        for cantiere in cantieri:
            # Conteggio giornali per ogni cantiere
            giornali_count_result = await db.execute(
                select(func.count(GiornaleCantiere.id)).where(
                    GiornaleCantiere.cantiere_id == cantiere.id
                )
            )
            giornali_count = giornali_count_result.scalar() or 0
            
            # Conteggio operatori che hanno lavorato su questo cantiere (SQLite compatible)
            operatori_subquery = (
                select(giornale_operatori_association.c.operatore_id)
                .join(GiornaleCantiere, GiornaleCantiere.id == giornale_operatori_association.c.giornale_id)
                .where(GiornaleCantiere.cantiere_id == cantiere.id)
                .distinct()
            )
            
            operatori_count_result = await db.execute(
                select(func.count()).select_from(operatori_subquery.subquery())
            )
            operatori_count = operatori_count_result.scalar() or 0
            
            cantieri_data.append({
                "id": str(cantiere.id),
                "nome": cantiere.nome,
                "codice": cantiere.codice,
                "descrizione": cantiere.descrizione,
                "stato": cantiere.stato,
                "stato_formattato": cantiere.stato_formattato,
                "priorita": cantiere.priorita,
                "data_inizio_prevista": cantiere.data_inizio_prevista.isoformat() if cantiere.data_inizio_prevista else None,
                "data_fine_prevista": cantiere.data_fine_prevista.isoformat() if cantiere.data_fine_prevista else None,
                "data_inizio_effettiva": cantiere.data_inizio_effettiva.isoformat() if cantiere.data_inizio_effettiva else None,
                "data_fine_effettiva": cantiere.data_fine_effettiva.isoformat() if cantiere.data_fine_effettiva else None,
                "area_descrizione": cantiere.area_descrizione,
                "responsabile_cantiere": cantiere.responsabile_cantiere,
                "tipologia_intervento": cantiere.tipologia_intervento,
                "e_in_corso": cantiere.e_in_corso,
                "durata_giorni": cantiere.durata_giorni,
                "giornali_count": giornali_count,
                "operatori_count": operatori_count,
                "created_at": cantiere.created_at.isoformat() if cantiere.created_at else None,
                "updated_at": cantiere.updated_at.isoformat() if cantiere.updated_at else None
            })
        
        return {
            "site_id": str(site_id),
            "cantieri": cantieri_data,
            "count": len(cantieri_data),
            "site_info": site_info
        }
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore recupero cantieri sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei cantieri"
        )

@router.post("/sites/{site_id}/cantieri", summary="Crea nuovo cantiere", tags=["Cantieri"])
async def v1_create_cantiere(
    site_id: UUID,
    cantiere_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea un nuovo cantiere per un sito archeologico.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Crea nuovo cantiere
        nuovo_cantiere = Cantiere(
            site_id=site_id,
            nome=cantiere_data.get("nome"),
            codice=cantiere_data.get("codice"),
            descrizione=cantiere_data.get("descrizione"),
            data_inizio_prevista=date.fromisoformat(cantiere_data.get("data_inizio_prevista")) if cantiere_data.get("data_inizio_prevista") else None,
            data_fine_prevista=date.fromisoformat(cantiere_data.get("data_fine_prevista")) if cantiere_data.get("data_fine_prevista") else None,
            stato=cantiere_data.get("stato", "pianificato"),
            area_descrizione=cantiere_data.get("area_descrizione"),
            coordinate_lat=cantiere_data.get("coordinate_lat"),
            coordinate_lon=cantiere_data.get("coordinate_lon"),
            quota=cantiere_data.get("quota"),
            responsabile_cantiere=cantiere_data.get("responsabile_cantiere"),
            tipologia_intervento=cantiere_data.get("tipologia_intervento"),
            priorita=cantiere_data.get("priorita", 3)
        )
        
        db.add(nuovo_cantiere)
        await db.commit()
        await db.refresh(nuovo_cantiere)
        
        return {
            "id": str(nuovo_cantiere.id),
            "message": "Cantiere creato con successo",
            "site_info": site_info
        }
        
    except Exception as e:
        logger.error(f"Errore creazione cantiere: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nella creazione del cantiere"
        )

@router.get("/cantieri/{cantiere_id}", summary="Dettaglio cantiere", tags=["Cantieri"])
async def v1_get_cantiere_detail(
    cantiere_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera i dettagli di un cantiere specifico.
    """
    try:
        # Carica cantiere con relazioni
        result = await db.execute(
            select(Cantiere)
            .options(
                selectinload(Cantiere.site),
                selectinload(Cantiere.giornali)
            )
            .where(
                and_(Cantiere.id == cantiere_id, Cantiere.is_active == True)
            )
        )
        cantiere = result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Verifica accesso al sito
        verify_site_access(cantiere.site_id, user_sites)
        
        # Prepara statistiche aggiuntive
        giornali_count_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                GiornaleCantiere.cantiere_id == cantiere_id
            )
        )
        giornali_count = giornali_count_result.scalar() or 0
        
        return {
            **cantiere.to_dict(),
            "giornali_count": giornali_count,
            "site_info": {
                "id": str(cantiere.site.id),
                "name": cantiere.site.name if cantiere.site else "N/A",
                "code": cantiere.site.code if cantiere.site else "N/A"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore dettaglio cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento del cantiere"
        )

@router.put("/cantieri/{cantiere_id}", summary="Aggiorna cantiere", tags=["Cantieri"])
async def v1_update_cantiere(
    cantiere_id: UUID,
    cantiere_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna un cantiere esistente.
    """
    try:
        # Carica cantiere esistente
        result = await db.execute(
            select(Cantiere).where(Cantiere.id == cantiere_id)
        )
        cantiere = result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Verifica accesso al sito
        verify_site_access(cantiere.site_id, user_sites)
        
        # Aggiorna campi
        if "nome" in cantiere_data:
            cantiere.nome = cantiere_data["nome"]
        if "codice" in cantiere_data:
            cantiere.codice = cantiere_data["codice"]
        if "descrizione" in cantiere_data:
            cantiere.descrizione = cantiere_data["descrizione"]
        if "data_inizio_prevista" in cantiere_data:
            cantiere.data_inizio_prevista = date.fromisoformat(cantiere_data["data_inizio_prevista"]) if cantiere_data["data_inizio_prevista"] else None
        if "data_fine_prevista" in cantiere_data:
            cantiere.data_fine_prevista = date.fromisoformat(cantiere_data["data_fine_prevista"]) if cantiere_data["data_fine_prevista"] else None
        if "stato" in cantiere_data:
            cantiere.stato = cantiere_data["stato"]
        if "area_descrizione" in cantiere_data:
            cantiere.area_descrizione = cantiere_data["area_descrizione"]
        if "coordinate_lat" in cantiere_data:
            cantiere.coordinate_lat = cantiere_data["coordinate_lat"]
        if "coordinate_lon" in cantiere_data:
            cantiere.coordinate_lon = cantiere_data["coordinate_lon"]
        if "quota" in cantiere_data:
            cantiere.quota = cantiere_data["quota"]
        if "responsabile_cantiere" in cantiere_data:
            cantiere.responsabile_cantiere = cantiere_data["responsabile_cantiere"]
        if "tipologia_intervento" in cantiere_data:
            cantiere.tipologia_intervento = cantiere_data["tipologia_intervento"]
        if "priorita" in cantiere_data:
            cantiere.priorita = cantiere_data["priorita"]
        
        # Se lo stato cambia a "in_corso", imposta data inizio effettiva
        if cantiere_data.get("stato") == "in_corso" and not cantiere.data_inizio_effettiva:
            cantiere.data_inizio_effettiva = date.today()
        
        # Se lo stato cambia a "completato", imposta data fine effettiva
        if cantiere_data.get("stato") == "completato" and not cantiere.data_fine_effettiva and cantiere.data_inizio_effettiva:
            cantiere.data_fine_effettiva = date.today()
        
        await db.commit()
        
        return {
            "id": str(cantiere.id),
            "message": "Cantiere aggiornato con successo"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore aggiornamento cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nell'aggiornamento del cantiere"
        )

@router.delete("/cantieri/{cantiere_id}", summary="Elimina cantiere", tags=["Cantieri"])
async def v1_delete_cantiere(
    cantiere_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Elimina un cantiere (soft delete).
    """
    try:
        # Carica cantiere esistente
        result = await db.execute(
            select(Cantiere).where(Cantiere.id == cantiere_id)
        )
        cantiere = result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Verifica accesso al sito
        verify_site_access(cantiere.site_id, user_sites)
        
        # Verifica che non ci siano giornali associati
        giornali_count_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                GiornaleCantiere.cantiere_id == cantiere_id
            )
        )
        giornali_count = giornali_count_result.scalar() or 0
        
        if giornali_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Impossibile eliminare il cantiere: ci sono {giornali_count} giornali associati"
            )
        
        # Soft delete
        cantiere.is_active = False
        cantiere.deleted_at = func.now()
        await db.commit()
        
        return {
            "message": "Cantiere eliminato con successo"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore eliminazione cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nell'eliminazione del cantiere"
        )

@router.get("/stats/cantieri", summary="Statistiche cantieri", tags=["Cantieri - Stats"])
async def v1_get_cantieri_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera statistiche generali per i cantieri dell'utente.
    """
    try:
        site_ids = [UUID(site["id"]) for site in user_sites]
        if not site_ids:
            return {
                "totali": 0,
                "pianificati": 0,
                "in_corso": 0,
                "completati": 0,
                "annullati": 0
            }
        
        # Statistiche per stato
        stati_result = await db.execute(
            select(
                Cantiere.stato,
                func.count(Cantiere.id).label("count")
            )
            .where(
                and_(
                    Cantiere.site_id.in_(site_ids),
                    Cantiere.is_active == True
                )
            )
            .group_by(Cantiere.stato)
            .order_by(Cantiere.stato)
        )
        stati = stati_result.all()
        
        stats = {
            "totali": sum(count for _, count in stati),
            "pianificati": 0,
            "in_corso": 0,
            "completati": 0,
            "annullati": 0
        }
        
        for stato, count in stati:
            if stato == "pianificato":
                stats["pianificati"] = count
            elif stato == "in_corso":
                stats["in_corso"] = count
            elif stato == "completato":
                stats["completati"] = count
            elif stato == "annullato":
                stats["annullati"] = count
        
        return stats
        
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore statistiche cantieri: {str(e)}")
        raise HTTPException(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche cantieri"
        )

@router.get("/sites/{site_id}/stats/cantieri", summary="Statistiche cantieri sito", tags=["Cantieri - Stats"])
async def v1_get_site_cantieri_stats(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera statistiche per i cantieri di un sito specifico.
    """
    try:
        # Verify site access
        site_info = verify_site_access(site_id, user_sites)
        
        # Count total cantieri for site
        total_cantieri_result = await db.execute(
            select(func.count(Cantiere.id)).where(
                and_(
                    Cantiere.site_id == site_id,
                    Cantiere.is_active == True
                )
            )
        )
        total_cantieri = total_cantieri_result.scalar() or 0
        
        # Statistics by state
        stati_result = await db.execute(
            select(
                Cantiere.stato,
                func.count(Cantiere.id).label("count")
            )
            .where(
                and_(
                    Cantiere.site_id == site_id,
                    Cantiere.is_active == True
                )
            )
            .group_by(Cantiere.stato)
            .order_by(Cantiere.stato)
        )
        stati = stati_result.all()
        
        stats = {
            "total_cantieri": total_cantieri
        }
        
        for stato, count in stati:
            stats[stato] = count
        
        # Get cantieri with giornali (SQLite compatible)
        cantieri_con_giornali_subquery = (
            select(GiornaleCantiere.cantiere_id)
            .where(
                and_(
                    GiornaleCantiere.site_id == site_id,
                    GiornaleCantiere.cantiere_id.in_(
                        select(Cantiere.id).where(
                            and_(
                                Cantiere.site_id == site_id,
                                Cantiere.is_active == True
                            )
                        )
                    )
                )
            )
            .distinct()
        )
        
        cantieri_con_giornali_result = await db.execute(
            select(func.count()).select_from(cantieri_con_giornali_subquery.subquery())
        )
        cantieri_con_giornali = cantieri_con_giornali_result.scalar() or 0
        
        stats["cantieri_con_giornali"] = cantieri_con_giornali
        stats["cantieri_senza_giornali"] = total_cantieri - cantieri_con_giornali
        
        return {
            **stats,
            "site_info": site_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"Errore statistiche cantieri sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche cantieri del sito"
        )