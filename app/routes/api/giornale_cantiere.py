# app/routes/api/giornale_cantiere.py
"""
API Routes per il Giornale di Cantiere Archeologico
Gestione CRUD completa con autenticazione e controllo accessi per siti
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import selectinload
from loguru import logger

# Import del sistema esistente
from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models.users import User

# Import dei nuovi modelli
from app.models.giornale_cantiere import GiornaleCantiere, OperatoreCantiere, CondizioniMeteoEnum

# Import degli schemi Pydantic (da creare nel prossimo file)
from app.schemas.giornale_cantiere import (
    GiornaleCantiereCreate,
    GiornaleCantiereUpdate, 
    GiornaleCantiereOut,
    OperatoreCantiereCreate,
    OperatoreCantiereOut,
    GiornaleCantiereFilter
)

# Router con prefisso API
router = APIRouter(prefix="/api/giornale-cantiere", tags=["giornale-cantiere"])


# ===== GESTIONE OPERATORI DI CANTIERE =====

@router.post("/operatori", response_model=OperatoreCantiereOut, status_code=status.HTTP_201_CREATED)
async def create_operatore(
    operatore: OperatoreCantiereCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Crea un nuovo operatore di cantiere
    Disponibile solo per utenti autenticati
    """
    try:
        # Crea nuovo operatore
        db_operatore = OperatoreCantiere(**operatore.model_dump())
        
        db.add(db_operatore)
        await db.commit()
        await db.refresh(db_operatore)
        
        logger.info(f"Operatore creato: {db_operatore.nome_completo} da user {current_user_id}")
        
        return db_operatore
        
    except Exception as e:
        logger.error(f"Errore creazione operatore: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione dell'operatore: {str(e)}"
        )


@router.get("/operatori", response_model=List[OperatoreCantiereOut])
async def list_operatori(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    qualifica_filter: Optional[str] = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Lista tutti gli operatori di cantiere con filtri opzionali
    """
    try:
        query = select(OperatoreCantiere)
        
        # Filtro attivi/inattivi
        if active_only:
            query = query.where(OperatoreCantiere.is_active == True)
        
        # Filtro per ricerca testuale (nome, cognome, qualifica)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    OperatoreCantiere.nome.ilike(search_pattern),
                    OperatoreCantiere.cognome.ilike(search_pattern),
                    OperatoreCantiere.qualifica.ilike(search_pattern)
                )
            )
        
        # Filtro per qualifica specifica
        if qualifica_filter:
            query = query.where(OperatoreCantiere.qualifica.ilike(f"%{qualifica_filter}%"))
        
        # Ordinamento e paginazione
        query = query.order_by(OperatoreCantiere.cognome, OperatoreCantiere.nome)
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        operatori = result.scalars().all()
        
        logger.info(f"Lista operatori: {len(operatori)} trovati (user: {current_user_id})")
        
        return operatori
        
    except Exception as e:
        logger.error(f"Errore lista operatori: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero degli operatori"
        )


@router.get("/operatori/{operatore_id}", response_model=OperatoreCantiereOut)
async def get_operatore(
    operatore_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Ottieni dettagli di un operatore specifico
    """
    try:
        result = await db.execute(
            select(OperatoreCantiere).where(OperatoreCantiere.id == operatore_id)
        )
        operatore = result.scalar_one_or_none()
        
        if not operatore:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Operatore {operatore_id} non trovato"
            )
        
        return operatore
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore get operatore {operatore_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dell'operatore"
        )


# ===== GESTIONE GIORNALE DI CANTIERE =====

@router.post("/", response_model=GiornaleCantiereOut, status_code=status.HTTP_201_CREATED)
async def create_giornale(
    giornale: GiornaleCantiereCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Crea una nuova voce nel giornale di cantiere
    L'utente deve avere accesso al sito specifico
    """
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(giornale.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {giornale.site_id}"
            )
        
        # Verifica esistenza sito
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == giornale.site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sito archeologico {giornale.site_id} non trovato"
            )
        
        # Verifica che non esista già un giornale per la stessa data e sito
        existing_result = await db.execute(
            select(GiornaleCantiere).where(
                and_(
                    GiornaleCantiere.site_id == giornale.site_id,
                    GiornaleCantiere.data == giornale.data
                )
            )
        )
        existing_giornale = existing_result.scalar_one_or_none()
        
        if existing_giornale:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Giornale per il sito {site.name} in data {giornale.data} già esistente"
            )
        
        # Verifica operatori esistenti
        if giornale.operatori_ids:
            operatori_result = await db.execute(
                select(OperatoreCantiere).where(
                    OperatoreCantiere.id.in_(giornale.operatori_ids)
                )
            )
            operatori = operatori_result.scalars().all()
            
            if len(operatori) != len(giornale.operatori_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uno o più operatori specificati non esistono"
                )
        
        # Ottieni nome responsabile
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        responsabile_nome = user.email if user else "Utente sconosciuto"
        
        # Crea il giornale
        giornale_data = giornale.model_dump(exclude={'operatori_ids'})
        db_giornale = GiornaleCantiere(
            **giornale_data,
            responsabile_id=current_user_id,
            responsabile_nome=responsabile_nome
        )
        
        # Associa operatori se specificati
        if giornale.operatori_ids:
            db_giornale.operatori = operatori
        
        db.add(db_giornale)
        await db.commit()
        await db.refresh(db_giornale, ['site', 'responsabile', 'operatori'])
        
        logger.info(f"Giornale cantiere creato: sito {site.name}, data {giornale.data} da user {current_user_id}")
        
        return db_giornale
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore creazione giornale: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione del giornale: {str(e)}"
        )


@router.get("/site/{site_id}", response_model=List[GiornaleCantiereOut])
async def list_giornali_by_site(
    site_id: UUID,
    filters: GiornaleCantiereFilter = Depends(),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Lista tutte le voci del giornale di cantiere per un sito specifico con filtri
    """
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Costruisci query base
        query = select(GiornaleCantiere).where(GiornaleCantiere.site_id == site_id)
        
        # Applica filtri
        if filters.data_inizio:
            query = query.where(GiornaleCantiere.data >= filters.data_inizio)
        
        if filters.data_fine:
            query = query.where(GiornaleCantiere.data <= filters.data_fine)
        
        if filters.condizioni_meteo:
            query = query.where(GiornaleCantiere.condizioni_meteo == filters.condizioni_meteo)
        
        if filters.responsabile_id:
            query = query.where(GiornaleCantiere.responsabile_id == filters.responsabile_id)
        
        if filters.validato is not None:
            query = query.where(GiornaleCantiere.validato == filters.validato)
        
        # Include relazioni
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori)
        )
        
        # Ordinamento e paginazione
        query = query.order_by(GiornaleCantiere.data.desc(), GiornaleCantiere.created_at.desc())
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        giornali = result.scalars().all()
        
        logger.info(f"Lista giornali sito {site_id}: {len(giornali)} trovati (user: {current_user_id})")
        
        return giornali
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista giornali sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei giornali di cantiere"
        )


@router.get("/{giornale_id}", response_model=GiornaleCantiereOut)
async def get_giornale(
    giornale_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Ottieni dettagli di una voce specifica del giornale di cantiere
    """
    try:
        # Query con relazioni
        query = select(GiornaleCantiere).where(GiornaleCantiere.id == giornale_id).options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori)
        )
        
        result = await db.execute(query)
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Giornale {giornale_id} non trovato"
            )
        
        # Verifica accesso al sito
        site_access = any(site['id'] == str(giornale.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito del giornale"
            )
        
        return giornale
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore get giornale {giornale_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero del giornale"
        )


@router.put("/{giornale_id}", response_model=GiornaleCantiereOut)
async def update_giornale(
    giornale_id: UUID,
    giornale_update: GiornaleCantiereUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Aggiorna una voce del giornale di cantiere
    Solo il responsabile o un superuser può modificare
    Non è possibile modificare un giornale già validato
    """
    try:
        # Ottieni giornale esistente
        result = await db.execute(
            select(GiornaleCantiere).where(GiornaleCantiere.id == giornale_id).options(
                selectinload(GiornaleCantiere.operatori)
            )
        )
        db_giornale = result.scalar_one_or_none()
        
        if not db_giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Giornale {giornale_id} non trovato"
            )
        
        # Verifica accesso al sito
        site_access = any(site['id'] == str(db_giornale.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito del giornale"
            )
        
        # Verifica permessi di modifica
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        current_user = user_result.scalar_one_or_none()
        
        is_owner = db_giornale.responsabile_id == current_user_id
        is_superuser = current_user and current_user.is_superuser
        
        if not (is_owner or is_superuser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo il responsabile del giornale o un superuser può modificarlo"
            )
        
        # Non permettere modifiche se già validato (solo superuser può)
        if db_giornale.validato and not is_superuser:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossibile modificare un giornale già validato"
            )
        
        # Aggiorna campi
        update_data = giornale_update.model_dump(exclude_unset=True)
        
        # Gestione operatori
        if 'operatori_ids' in update_data:
            operatori_ids = update_data.pop('operatori_ids')
            if operatori_ids is not None:
                operatori_result = await db.execute(
                    select(OperatoreCantiere).where(
                        OperatoreCantiere.id.in_(operatori_ids)
                    )
                )
                operatori = operatori_result.scalars().all()
                
                if len(operatori) != len(operatori_ids):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Uno o più operatori specificati non esistono"
                    )
                
                db_giornale.operatori = operatori
        
        # Aggiorna altri campi
        for field, value in update_data.items():
            setattr(db_giornale, field, value)
        
        # Incrementa versione se modificato
        if update_data:
            db_giornale.version += 1
        
        await db.commit()
        await db.refresh(db_giornale, ['site', 'responsabile', 'operatori'])
        
        logger.info(f"Giornale {giornale_id} aggiornato da user {current_user_id}")
        
        return db_giornale
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore update giornale {giornale_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'aggiornamento del giornale: {str(e)}"
        )


@router.post("/{giornale_id}/valida")
async def valida_giornale(
    giornale_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Valida un giornale di cantiere (firma digitale)
    Solo il responsabile può validare il proprio giornale
    """
    try:
        # Ottieni giornale
        result = await db.execute(
            select(GiornaleCantiere).where(GiornaleCantiere.id == giornale_id)
        )
        db_giornale = result.scalar_one_or_none()
        
        if not db_giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Giornale {giornale_id} non trovato"
            )
        
        # Verifica accesso al sito
        site_access = any(site['id'] == str(db_giornale.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito del giornale"
            )
        
        # Verifica che sia il responsabile
        if db_giornale.responsabile_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo il responsabile può validare il giornale"
            )
        
        # Verifica che non sia già validato
        if db_giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Il giornale è già stato validato"
            )
        
        # Valida il giornale
        db_giornale.validato = True
        db_giornale.data_validazione = datetime.now()
        # TODO: Implementare firma digitale hash se necessario
        # db_giornale.firma_digitale_hash = generate_digital_signature_hash(...)
        
        await db.commit()
        
        logger.info(f"Giornale {giornale_id} validato da user {current_user_id}")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Giornale validato con successo", "validated_at": db_giornale.data_validazione.isoformat()}
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore validazione giornale {giornale_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella validazione del giornale: {str(e)}"
        )


@router.delete("/{giornale_id}")
async def delete_giornale(
    giornale_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Elimina un giornale di cantiere
    Solo superuser può eliminare
    Non è possibile eliminare giornali validati
    """
    try:
        # Verifica che l'utente sia superuser
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        current_user = user_result.scalar_one_or_none()
        
        if not current_user or not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo i superuser possono eliminare i giornali"
            )
        
        # Ottieni giornale
        result = await db.execute(
            select(GiornaleCantiere).where(GiornaleCantiere.id == giornale_id)
        )
        db_giornale = result.scalar_one_or_none()
        
        if not db_giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Giornale {giornale_id} non trovato"
            )
        
        # Verifica accesso al sito
        site_access = any(site['id'] == str(db_giornale.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito del giornale"
            )
        
        # Non permettere eliminazione di giornali validati
        if db_giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossibile eliminare un giornale validato"
            )
        
        await db.delete(db_giornale)
        await db.commit()
        
        logger.info(f"Giornale {giornale_id} eliminato da superuser {current_user_id}")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Giornale eliminato con successo"}
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione giornale {giornale_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'eliminazione del giornale: {str(e)}"
        )


# ===== ENDPOINT UTILITY E STATISTICHE =====

@router.get("/site/{site_id}/stats")
async def get_giornale_stats(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Ottieni statistiche sui giornali di cantiere per un sito
    """
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Statistiche base
        total_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == site_id)
        )
        total_giornali = total_result.scalar()
        
        validated_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                and_(GiornaleCantiere.site_id == site_id, GiornaleCantiere.validato == True)
            )
        )
        validated_giornali = validated_result.scalar()
        
        # Ultimo giornale
        last_result = await db.execute(
            select(GiornaleCantiere.data).where(GiornaleCantiere.site_id == site_id).order_by(GiornaleCantiere.data.desc()).limit(1)
        )
        last_date = last_result.scalar_one_or_none()
        
        return {
            "site_id": str(site_id),
            "total_giornali": total_giornali,
            "validated_giornali": validated_giornali,
            "pending_validation": total_giornali - validated_giornali,
            "last_entry_date": last_date.isoformat() if last_date else None,
            "validation_percentage": round((validated_giornali / total_giornali * 100) if total_giornali > 0 else 0, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore stats giornale sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero delle statistiche"
        )


@router.get("/condizioni-meteo")
async def get_condizioni_meteo():
    """
    Restituisce l'elenco delle condizioni meteorologiche disponibili
    """
    return {
        "condizioni_meteo": [
            {"value": condition.value, "label": condition.value.replace("_", " ").title()}
            for condition in CondizioniMeteoEnum
        ]
    }