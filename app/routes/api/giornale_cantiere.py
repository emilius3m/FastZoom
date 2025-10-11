# app/routes/api/giornale_cantiere.py
"""
API Routes complete per Giornale di Cantiere
Sostituisce tutti i mock data con endpoint reali per i template
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, distinct
from sqlalchemy.orm import selectinload
from loguru import logger

# Import sistema esistente
from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models.users import User

# Import modelli giornale cantiere (dai file esistenti)
from app.models.giornale_cantiere import (
    GiornaleCantiere, OperatoreCantiere, 
    CondizioniMeteoEnum
)

# Import schemas from existing schema file
from app.schemas.giornale_cantiere import (
    OperatoreCantiereCreate,
    OperatoreCantiereOut,
    OperatoreCantiereUpdate
)

# Pydantic schemas
from pydantic import BaseModel, Field
from datetime import time

# ===== SCHEMAS PYDANTIC =====

class GiornaleStatsResponse(BaseModel):
    """Statistiche per dashboard"""
    siti_totali: int = 0
    giornali_totali: int = 0
    giornali_validati: int = 0
    giornali_pendenti: int = 0

class SiteStatsResponse(BaseModel):
    """Statistiche per sito specifico"""
    total_giornali: int = 0
    validated_giornali: int = 0
    pending_giornali: int = 0
    operatori_attivi: int = 0
    validation_percentage: int = 0

class OperatoreStatsResponse(BaseModel):
    """Statistiche operatori"""
    totali: int = 0
    attivi: int = 0
    specialisti: int = 0
    ore_totali: int = 0

class TopOperatore(BaseModel):
    """Top operatore per report"""
    id: UUID
    nome: str
    cognome: str
    ruolo: str
    ore_lavorate: int
    giornali_count: int

class SiteStat(BaseModel):
    """Statistiche per sito nei report"""
    id: UUID
    name: str
    location: str
    giornali_count: int

class MeteoStat(BaseModel):
    """Statistiche meteo"""
    condizione: str
    count: int

class ReportStatsResponse(BaseModel):
    """Response per report completi"""
    totali: int = 0
    validati: int = 0
    in_attesa: int = 0
    ore_totali: int = 0
    operatori_unici: int = 0

class ReportDataResponse(BaseModel):
    """Dati completi per report"""
    stats: ReportStatsResponse
    site_stats: List[SiteStat]
    top_operatori: List[TopOperatore]
    meteo_stats: List[MeteoStat]

# ===== ROUTER =====
router = APIRouter(prefix="/api/giornale-cantiere", tags=["giornale-cantiere-api"])


# ===== TEST ENDPOINTS =====

@router.post("/operatori/test")
async def test_operatore_creation(
        db: AsyncSession = Depends(get_async_session),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Test endpoint for creating an operator with fixed data"""
    try:
        # Create test data
        test_data = {
            "nome": "Test",
            "cognome": "Operator",
            "qualifica": "Test Qualification",
            "ruolo": "test_role",
            "specializzazione": "test_specialization",
            "email": "test@example.com",
            "telefono": "1234567890",
            "is_active": True,
            "note": "Test operator created via test endpoint"
        }
        
        logger.info(f"Creating test operator with data: {test_data}")
        
        # Create new operatore
        db_operatore = OperatoreCantiere(**test_data)

        db.add(db_operatore)
        await db.commit()
        await db.refresh(db_operatore)

        logger.info(f"Test operator created: {db_operatore.nome_completo} from user {current_user_id}")

        return {
            "message": "Test operator created successfully",
            "operator_id": str(db_operatore.id),
            "operator_name": db_operatore.nome_completo
        }

    except Exception as e:
        # Log the full exception with traceback for debugging
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error creating test operator: {str(e)}\nTraceback: {error_traceback}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error creating test operator: {str(e)}"
        )

# ===== HELPER FUNCTIONS =====

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica accesso utente al sito"""
    return any(site['id'] == str(site_id) for site in user_sites)

async def get_site_with_verification(
    site_id: UUID, 
    db: AsyncSession, 
    user_sites: List[Dict[str, Any]]
) -> ArchaeologicalSite:
    """Ottieni sito con verifica accesso"""
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accesso negato al sito {site_id}"
        )
    
    result = await db.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    )
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato"
        )
    
    return site

# ===== ENDPOINTS STATISTICHE =====

@router.get("/stats/general", response_model=GiornaleStatsResponse)
async def get_general_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Statistiche generali per dashboard home"""
    try:
        # Ottieni ID siti accessibili
        site_ids = [UUID(site['id']) for site in user_sites]
        
        if not site_ids:
            return GiornaleStatsResponse()
        
        # Siti con giornali
        siti_result = await db.execute(
            select(distinct(GiornaleCantiere.site_id))
            .where(GiornaleCantiere.site_id.in_(site_ids))
        )
        siti_totali = len(siti_result.fetchall())
        
        # Giornali totali
        totali_result = await db.execute(
            select(func.count(GiornaleCantiere.id))
            .where(GiornaleCantiere.site_id.in_(site_ids))
        )
        giornali_totali = totali_result.scalar() or 0
        
        # Giornali validati
        validati_result = await db.execute(
            select(func.count(GiornaleCantiere.id))
            .where(and_(
                GiornaleCantiere.site_id.in_(site_ids),
                GiornaleCantiere.validato == True
            ))
        )
        giornali_validati = validati_result.scalar() or 0
        
        return GiornaleStatsResponse(
            siti_totali=siti_totali,
            giornali_totali=giornali_totali,
            giornali_validati=giornali_validati,
            giornali_pendenti=giornali_totali - giornali_validati
        )
        
    except Exception as e:
        logger.error(f"Errore statistiche generali: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche generali"
        )

@router.get("/stats/site/{site_id}", response_model=SiteStatsResponse)
async def get_site_stats(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Statistiche per sito specifico"""
    try:
        # Verifica accesso
        await get_site_with_verification(site_id, db, user_sites)
        
        # Giornali totali
        totali_result = await db.execute(
            select(func.count(GiornaleCantiere.id))
            .where(GiornaleCantiere.site_id == site_id)
        )
        total_giornali = totali_result.scalar() or 0
        
        # Giornali validati
        validati_result = await db.execute(
            select(func.count(GiornaleCantiere.id))
            .where(and_(
                GiornaleCantiere.site_id == site_id,
                GiornaleCantiere.validato == True
            ))
        )
        validated_giornali = validati_result.scalar() or 0
        
        # Operatori unici coinvolti nel sito
        # Assumendo relazione many-to-many tra giornali e operatori
        operatori_result = await db.execute(
            select(func.count(distinct(OperatoreCantiere.id)))
            .join(GiornaleCantiere.operatori)
            .where(GiornaleCantiere.site_id == site_id)
        )
        operatori_attivi = operatori_result.scalar() or 0
        
        # Calcola percentuale validazione
        validation_percentage = 0
        if total_giornali > 0:
            validation_percentage = round((validated_giornali / total_giornali) * 100)
        
        return SiteStatsResponse(
            total_giornali=total_giornali,
            validated_giornali=validated_giornali,
            pending_giornali=total_giornali - validated_giornali,
            operatori_attivi=operatori_attivi,
            validation_percentage=validation_percentage
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore statistiche sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche del sito"
        )

@router.get("/stats/operatori", response_model=OperatoreStatsResponse)
async def get_operatori_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Statistiche operatori"""
    try:
        # Operatori totali
        totali_result = await db.execute(
            select(func.count(OperatoreCantiere.id))
        )
        totali = totali_result.scalar() or 0
        
        # Operatori attivi (con almeno un giornale)
        attivi_result = await db.execute(
            select(func.count(distinct(OperatoreCantiere.id)))
            .join(GiornaleCantiere.operatori)
        )
        attivi = attivi_result.scalar() or 0
        
        # Specialisti (assumendo campo specializzazione not null)
        specialisti_result = await db.execute(
            select(func.count(OperatoreCantiere.id))
            .where(OperatoreCantiere.specializzazione.isnot(None))
        )
        specialisti = specialisti_result.scalar() or 0
        
        # Ore totali (assumendo campo ore_lavorate in OperatoreCantiere o calcolo dai giornali)
        ore_result = await db.execute(
            select(func.sum(OperatoreCantiere.ore_totali))
            .where(OperatoreCantiere.ore_totali.isnot(None))
        )
        ore_totali = int(ore_result.scalar() or 0)
        
        return OperatoreStatsResponse(
            totali=totali,
            attivi=attivi,
            specialisti=specialisti,
            ore_totali=ore_totali
        )
        
    except Exception as e:
        logger.error(f"Errore statistiche operatori: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel calcolo delle statistiche operatori"
        )

# ===== ENDPOINTS GIORNALI =====

@router.get("/site/{site_id}")
async def get_giornali_by_site(
    site_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    data_da: Optional[date] = Query(None),
    data_a: Optional[date] = Query(None),
    responsabile: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista giornali per sito con filtri"""
    try:
        # Verifica accesso
        await get_site_with_verification(site_id, db, user_sites)
        
        # Query base
        query = select(GiornaleCantiere).where(GiornaleCantiere.site_id == site_id)
        
        # Applica filtri
        if data_da:
            query = query.where(GiornaleCantiere.data >= data_da)
        if data_a:
            query = query.where(GiornaleCantiere.data <= data_a)
        if responsabile:
            query = query.where(GiornaleCantiere.responsabile_nome.ilike(f"%{responsabile}%"))
        if stato:
            if stato == "validato":
                query = query.where(GiornaleCantiere.validato == True)
            elif stato == "in_attesa":
                query = query.where(GiornaleCantiere.validato == False)
        
        # Include relazioni
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori)
        )
        
        # Ordinamento e paginazione
        query = query.order_by(desc(GiornaleCantiere.data), desc(GiornaleCantiere.created_at))
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        giornali = result.scalars().all()
        
        # Converti in dizionari per il frontend
        giornali_data = []
        for g in giornali:
            giornale_dict = {
                "id": str(g.id),
                "data": g.data.isoformat() if g.data else None,
                "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
                "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
                "responsabile_scavo": g.responsabile_nome or (g.responsabile.email if g.responsabile else None),
                "descrizione_lavori": g.descrizione_lavori,
                "condizioni_meteo": g.condizioni_meteo,
                "stato": "validato" if g.validato else "in_attesa",
                "us_elaborate": g.get_us_list(),
                "operatori_presenti": [
                    {"nome": op.nome, "cognome": op.cognome, "ruolo": op.ruolo}
                    for op in g.operatori
                ] if g.operatori else [],
                "note_generali": g.note_generali,
                "problematiche": g.problematiche,
                "compilatore": g.responsabile_nome,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
                "version": g.version or 1
            }
            giornali_data.append(giornale_dict)
        
        return giornali_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista giornali sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei giornali"
        )

# Schema per creazione giornale
class GiornaleCantiereCreate(BaseModel):
    """Schema per creazione nuovo giornale"""
    site_id: UUID
    data: date
    ora_inizio: Optional[time] = None
    ora_fine: Optional[time] = None
    responsabile_nome: str
    compilatore: Optional[str] = None
    condizioni_meteo: Optional[str] = None
    temperatura_min: Optional[int] = None
    temperatura_max: Optional[int] = None
    descrizione_lavori: str
    operatori_ids: Optional[List[UUID]] = []
    us_elaborate_input: Optional[str] = None
    note_generali: Optional[str] = None
    problematiche: Optional[str] = None
    apparecchiature_input: Optional[str] = None

@router.post("/giornali", status_code=status.HTTP_201_CREATED)
async def create_giornale(
    giornale_data: GiornaleCantiereCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Crea un nuovo giornale di cantiere"""
    try:
        # Verifica accesso al sito
        await get_site_with_verification(giornale_data.site_id, db, user_sites)
        
        # Crea nuovo giornale
        db_giornale = GiornaleCantiere(
            site_id=giornale_data.site_id,
            data=giornale_data.data,
            ora_inizio=giornale_data.ora_inizio,
            ora_fine=giornale_data.ora_fine,
            responsabile_id=current_user_id,  # FIX: Set responsabile_id from current user
            responsabile_nome=giornale_data.responsabile_nome,
            compilatore=giornale_data.compilatore,
            condizioni_meteo=giornale_data.condizioni_meteo,
            temperatura=giornale_data.temperatura_max,  # Salviamo temperatura_max nel campo temperatura per compatibilità
            temperatura_min=giornale_data.temperatura_min,
            temperatura_max=giornale_data.temperatura_max,
            descrizione_lavori=giornale_data.descrizione_lavori,
            note_generali=giornale_data.note_generali,
            problematiche=giornale_data.problematiche,
            validato=False
            # created_at and updated_at will be set automatically by server_default
        )
        
        # Processa US elaborate
        if giornale_data.us_elaborate_input:
            us_list = [us.strip() for us in giornale_data.us_elaborate_input.split(",") if us.strip()]
            db_giornale.set_us_list(us_list)
        
        # Processa apparecchiature
        if giornale_data.apparecchiature_input:
            apparecchiature_list = [app.strip() for app in giornale_data.apparecchiature_input.replace("\n", ",").split(",") if app.strip()]
            db_giornale.set_apparecchiature_list(apparecchiature_list)
        
        db.add(db_giornale)
        await db.flush()  # Ottieni l'ID senza commit finale
        
        # Associa operatori se specificati
        if giornale_data.operatori_ids:
            # Carica operatori
            operatori_result = await db.execute(
                select(OperatoreCantiere).where(OperatoreCantiere.id.in_(giornale_data.operatori_ids))
            )
            operatori = operatori_result.scalars().all()
            
            # Associa operatori al giornale
            db_giornale.operatori = operatori
        
        await db.commit()
        await db.refresh(db_giornale)
        
        logger.info(f"Giornale creato: {db_giornale.id} per sito {giornale_data.site_id} da user {current_user_id}")
        
        return {
            "id": str(db_giornale.id),
            "message": "Giornale creato con successo",
            "site_id": str(db_giornale.site_id),
            "data": db_giornale.data.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore creazione giornale: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione del giornale: {str(e)}"
        )

@router.get("/giornali/{giornale_id}")
async def get_giornale(
    giornale_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottiene dettagli di un singolo giornale"""
    try:
        # Carica giornale con relazioni
        result = await db.execute(
            select(GiornaleCantiere)
            .where(GiornaleCantiere.id == giornale_id)
            .options(
                selectinload(GiornaleCantiere.site),
                selectinload(GiornaleCantiere.operatori)
            )
        )
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Verifica accesso al sito
        await get_site_with_verification(giornale.site_id, db, user_sites)
        
        # Converti in dizionario per il frontend
        giornale_dict = {
            "id": str(giornale.id),
            "site_id": str(giornale.site_id),
            "data": giornale.data.isoformat() if giornale.data else None,
            "ora_inizio": giornale.ora_inizio.strftime("%H:%M") if giornale.ora_inizio else None,
            "ora_fine": giornale.ora_fine.strftime("%H:%M") if giornale.ora_fine else None,
            "responsabile_scavo": giornale.responsabile_nome,
            "compilatore": giornale.compilatore,
            "condizioni_meteo": giornale.condizioni_meteo,
            "temperatura_min": giornale.temperatura_min,
            "temperatura_max": giornale.temperatura_max,
            "descrizione_lavori": giornale.descrizione_lavori,
            "us_elaborate": giornale.get_us_list(),
            "apparecchiature_utilizzate": giornale.get_apparecchiature_list(),
            "note_generali": giornale.note_generali,
            "problematiche": giornale.problematiche,
            "operatori_presenti": [
                {"id": str(op.id), "nome": op.nome, "cognome": op.cognome, "ruolo": op.ruolo}
                for op in giornale.operatori
            ] if giornale.operatori else [],
            "stato": "validato" if giornale.validato else "in_attesa",
            "created_at": giornale.created_at.isoformat() if giornale.created_at else None,
            "updated_at": giornale.updated_at.isoformat() if giornale.updated_at else None,
            "version": giornale.version or 1
        }
        
        return giornale_dict
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore recupero giornale {giornale_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero del giornale"
        )

@router.put("/giornali/{giornale_id}")
async def update_giornale(
    giornale_id: UUID,
    giornale_data: GiornaleCantiereCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Aggiorna un giornale esistente"""
    try:
        # Carica giornale esistente
        result = await db.execute(
            select(GiornaleCantiere).where(GiornaleCantiere.id == giornale_id)
        )
        db_giornale = result.scalar_one_or_none()
        
        if not db_giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Verifica accesso al sito
        await get_site_with_verification(db_giornale.site_id, db, user_sites)
        
        # Verifica che il giornale non sia già validato
        if db_giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossibile modificare un giornale già validato"
            )
        
        # Aggiorna campi
        db_giornale.data = giornale_data.data
        db_giornale.ora_inizio = giornale_data.ora_inizio
        db_giornale.ora_fine = giornale_data.ora_fine
        db_giornale.responsabile_nome = giornale_data.responsabile_nome
        db_giornale.compilatore = giornale_data.compilatore
        db_giornale.condizioni_meteo = giornale_data.condizioni_meteo
        db_giornale.temperatura = giornale_data.temperatura_max  # Salviamo temperatura_max nel campo temperatura per compatibilità
        db_giornale.temperatura_min = giornale_data.temperatura_min
        db_giornale.temperatura_max = giornale_data.temperatura_max
        db_giornale.descrizione_lavori = giornale_data.descrizione_lavori
        db_giornale.note_generali = giornale_data.note_generali
        db_giornale.problematiche = giornale_data.problematiche
        # updated_at will be set automatically by onupdate
        db_giornale.version = (db_giornale.version or 1) + 1
        
        # Processa US elaborate
        if giornale_data.us_elaborate_input:
            us_list = [us.strip() for us in giornale_data.us_elaborate_input.split(",") if us.strip()]
            db_giornale.set_us_list(us_list)
        
        # Processa apparecchiature
        if giornale_data.apparecchiature_input:
            apparecchiature_list = [app.strip() for app in giornale_data.apparecchiature_input.replace("\n", ",").split(",") if app.strip()]
            db_giornale.set_apparecchiature_list(apparecchiature_list)
        
        # Aggiorna operatori se specificati
        if giornale_data.operatori_ids:
            # Carica operatori
            operatori_result = await db.execute(
                select(OperatoreCantiere).where(OperatoreCantiere.id.in_(giornale_data.operatori_ids))
            )
            operatori = operatori_result.scalars().all()
            
            # Associa operatori al giornale
            db_giornale.operatori = operatori
        
        await db.commit()
        
        logger.info(f"Giornale {giornale_id} aggiornato da user {current_user_id}")
        
        return {
            "id": str(db_giornale.id),
            "message": "Giornale aggiornato con successo",
            "site_id": str(db_giornale.site_id),
            "data": db_giornale.data.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento giornale {giornale_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'aggiornamento del giornale: {str(e)}"
        )

@router.delete("/giornali/{giornale_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_giornale(
    giornale_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Elimina un giornale di cantiere"""
    try:
        # Carica giornale esistente
        result = await db.execute(
            select(GiornaleCantiere).where(GiornaleCantiere.id == giornale_id)
        )
        db_giornale = result.scalar_one_or_none()
        
        if not db_giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Verifica accesso al sito
        await get_site_with_verification(db_giornale.site_id, db, user_sites)
        
        # Verifica che il giornale non sia già validato
        if db_giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossibile eliminare un giornale già validato"
            )
        
        # Elimina giornale
        await db.delete(db_giornale)
        await db.commit()
        
        logger.info(f"Giornale {giornale_id} eliminato da user {current_user_id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione giornale {giornale_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'eliminazione del giornale: {str(e)}"
        )

@router.get("/operatori")
async def get_operatori(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    ruolo: Optional[str] = Query(None),
    specializzazione: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Lista operatori con filtri"""
    try:
        # Query base
        query = select(OperatoreCantiere)
        
        # Applica filtri
        if search:
            search_pattern = f"%{search}%"
            query = query.where(or_(
                OperatoreCantiere.nome.ilike(search_pattern),
                OperatoreCantiere.cognome.ilike(search_pattern),
                OperatoreCantiere.codice_fiscale.ilike(search_pattern)
            ))
        
        if ruolo:
            query = query.where(OperatoreCantiere.ruolo == ruolo)
        if specializzazione:
            query = query.where(OperatoreCantiere.specializzazione == specializzazione)
        if stato:
            query = query.where(OperatoreCantiere.is_active == (stato == "attivo"))
        
        # Ordinamento e paginazione
        query = query.order_by(OperatoreCantiere.cognome, OperatoreCantiere.nome)
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        operatori = result.scalars().all()
        
        # Converti per frontend
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
                "giornali_count": 0,  # TODO: Calcolare dai giornali collegati
                "note": op.note
            }
            operatori_data.append(operatore_dict)
        
        return operatori_data
        
    except Exception as e:
        logger.error(f"Errore lista operatori: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero degli operatori"
        )


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
        # Debug: Log the received data
        logger.info(f"Dati operatore ricevuti: {operatore.model_dump()}")
        
        # Prepara dati operatore
        operatore_data = operatore.model_dump()
        
        # Ensure is_active is set if not provided
        if 'is_active' not in operatore_data:
            operatore_data['is_active'] = True
        
        # Convert empty strings to None for optional fields
        optional_string_fields = ['codice_fiscale', 'ruolo', 'specializzazione', 'email', 'telefono', 'abilitazioni', 'note']
        for field in optional_string_fields:
            if field in operatore_data and operatore_data[field] == '':
                operatore_data[field] = None
        
        # Debug: Log the data that will be saved
        logger.info(f"Dati che verranno salvati: {operatore_data}")
        
        # Validate required fields
        required_fields = ['nome', 'cognome', 'qualifica']
        missing_fields = [field for field in required_fields if not operatore_data.get(field)]
        if missing_fields:
            error_msg = f"Campi obbligatori mancanti: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_msg
            )
        
        # Crea nuovo operatore
        db_operatore = OperatoreCantiere(**operatore_data)

        db.add(db_operatore)
        await db.commit()
        await db.refresh(db_operatore)

        logger.info(f"Operatore creato: {db_operatore.nome_completo} da user {current_user_id}")

        return db_operatore

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        # Log the full exception with traceback for debugging
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Errore creazione operatore: {str(e)}\nTraceback: {error_traceback}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Errore nella creazione dell'operatore: {str(e)}"
        )


@router.put("/operatori/{operatore_id}", response_model=OperatoreCantiereOut)
async def update_operatore(
        operatore_id: UUID,
        operatore: OperatoreCantiereUpdate,
        db: AsyncSession = Depends(get_async_session),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Aggiorna un operatore di cantiere esistente
    """
    try:
        # Trova operatore
        result = await db.execute(
            select(OperatoreCantiere).where(OperatoreCantiere.id == operatore_id)
        )
        db_operatore = result.scalar_one_or_none()
        
        if not db_operatore:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Operatore {operatore_id} non trovato"
            )
        
        # Aggiorna campi
        update_data = operatore.model_dump(exclude_unset=True)
        
        
        for field, value in update_data.items():
            setattr(db_operatore, field, value)
        
        await db.commit()
        await db.refresh(db_operatore)
        
        logger.info(f"Operatore {operatore_id} aggiornato da user {current_user_id}")
        
        return db_operatore
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento operatore {operatore_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'aggiornamento dell'operatore: {str(e)}"
        )


@router.delete("/operatori/{operatore_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operatore(
        operatore_id: UUID,
        db: AsyncSession = Depends(get_async_session),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Elimina un operatore di cantiere
    """
    try:
        # Trova operatore
        result = await db.execute(
            select(OperatoreCantiere).where(OperatoreCantiere.id == operatore_id)
        )
        db_operatore = result.scalar_one_or_none()
        
        if not db_operatore:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Operatore {operatore_id} non trovato"
            )
        
        # Elimina operatore
        await db.delete(db_operatore)
        await db.commit()
        
        logger.info(f"Operatore {operatore_id} eliminato da user {current_user_id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione operatore {operatore_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'eliminazione dell'operatore: {str(e)}"
        )


@router.get("/operatori/{operatore_id}", response_model=OperatoreCantiereOut)
async def get_operatore(
        operatore_id: UUID,
        db: AsyncSession = Depends(get_async_session),
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Ottiene dettagli di un singolo operatore
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
        logger.error(f"Errore recupero operatore {operatore_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero dell'operatore: {str(e)}"
        )


# ===== ENDPOINTS REPORT =====

@router.post("/reports", response_model=ReportDataResponse)
async def get_reports_data(
    filters: Dict[str, Any],
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Genera dati per report con filtri"""
    try:
        # Ottieni ID siti accessibili
        site_ids = [UUID(site['id']) for site in user_sites]
        
        if not site_ids:
            return ReportDataResponse(
                stats=ReportStatsResponse(),
                site_stats=[],
                top_operatori=[],
                meteo_stats=[]
            )
        
        # Query base con filtri
        base_query = select(GiornaleCantiere).where(GiornaleCantiere.site_id.in_(site_ids))
        
        # Applica filtri temporali
        if filters.get("data_da"):
            base_query = base_query.where(GiornaleCantiere.data >= datetime.fromisoformat(filters["data_da"]).date())
        if filters.get("data_a"):
            base_query = base_query.where(GiornaleCantiere.data <= datetime.fromisoformat(filters["data_a"]).date())
        if filters.get("sito_id"):
            base_query = base_query.where(GiornaleCantiere.site_id == UUID(filters["sito_id"]))
        
        # Statistiche principali
        totali_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).select_from(base_query.subquery())
        )
        totali = totali_result.scalar() or 0
        
        validati_result = await db.execute(
            base_query.where(GiornaleCantiere.validato == True)
        )
        validati = len(validati_result.fetchall())
        
        # Ore totali (calcolo approssimativo)
        ore_result = await db.execute(
            select(func.sum(
                func.extract('epoch', GiornaleCantiere.ora_fine - GiornaleCantiere.ora_inizio) / 3600
            )).select_from(
                base_query.where(and_(
                    GiornaleCantiere.ora_inizio.isnot(None),
                    GiornaleCantiere.ora_fine.isnot(None)
                )).subquery()
            )
        )
        ore_totali = int(ore_result.scalar() or 0)
        
        # Operatori unici
        operatori_result = await db.execute(
            select(func.count(distinct(OperatoreCantiere.id)))
            .join(GiornaleCantiere.operatori)
            .select_from(base_query.subquery())
        )
        operatori_unici = operatori_result.scalar() or 0
        
        stats = ReportStatsResponse(
            totali=totali,
            validati=validati,
            in_attesa=totali - validati,
            ore_totali=ore_totali,
            operatori_unici=operatori_unici
        )
        
        # Statistiche per sito
        site_stats_query = await db.execute(
            select(
                ArchaeologicalSite.id,
                ArchaeologicalSite.name,
                ArchaeologicalSite.location,
                func.count(GiornaleCantiere.id).label('giornali_count')
            )
            .join(GiornaleCantiere, ArchaeologicalSite.id == GiornaleCantiere.site_id)
            .where(ArchaeologicalSite.id.in_(site_ids))
            .group_by(ArchaeologicalSite.id, ArchaeologicalSite.name, ArchaeologicalSite.location)
            .order_by(desc('giornali_count'))
        )
        
        site_stats = [
            SiteStat(
                id=row.id,
                name=row.name,
                location=row.location or "",
                giornali_count=row.giornali_count
            )
            for row in site_stats_query.fetchall()
        ]
        
        # Top operatori
        top_operatori_query = await db.execute(
            select(
                OperatoreCantiere.id,
                OperatoreCantiere.nome,
                OperatoreCantiere.cognome,
                OperatoreCantiere.ruolo,
                OperatoreCantiere.ore_totali,
                func.count(distinct(GiornaleCantiere.id)).label('giornali_count')
            )
            .join(GiornaleCantiere.operatori)
            .where(GiornaleCantiere.site_id.in_(site_ids))
            .group_by(
                OperatoreCantiere.id,
                OperatoreCantiere.nome,
                OperatoreCantiere.cognome,
                OperatoreCantiere.ruolo,
                OperatoreCantiere.ore_totali
            )
            .order_by(desc(OperatoreCantiere.ore_totali))
            .limit(10)
        )
        
        top_operatori = [
            TopOperatore(
                id=row.id,
                nome=row.nome,
                cognome=row.cognome,
                ruolo=row.ruolo or "Operatore",
                ore_lavorate=row.ore_totali or 0,
                giornali_count=row.giornali_count
            )
            for row in top_operatori_query.fetchall()
        ]
        
        # Statistiche meteo
        meteo_query = await db.execute(
            select(
                GiornaleCantiere.condizioni_meteo,
                func.count(GiornaleCantiere.id).label('count')
            )
            .select_from(base_query.subquery())
            .where(GiornaleCantiere.condizioni_meteo.isnot(None))
            .group_by(GiornaleCantiere.condizioni_meteo)
            .order_by(desc('count'))
        )
        
        meteo_stats = [
            MeteoStat(condizione=row.condizioni_meteo, count=row.count)
            for row in meteo_query.fetchall()
        ]
        
        return ReportDataResponse(
            stats=stats,
            site_stats=site_stats,
            top_operatori=top_operatori,
            meteo_stats=meteo_stats
        )
        
    except Exception as e:
        logger.error(f"Errore generazione report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nella generazione dei report"
        )

# ===== ENDPOINT VALIDAZIONE =====

@router.post("/validate/{giornale_id}")
async def validate_giornale(
    giornale_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Valida un giornale di cantiere"""
    try:
        # Carica giornale
        result = await db.execute(
            select(GiornaleCantiere)
            .where(GiornaleCantiere.id == giornale_id)
            .options(selectinload(GiornaleCantiere.site))
        )
        giornale = result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        
        # Verifica accesso al sito
        if not await verify_site_access(giornale.site_id, user_sites):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito del giornale"
            )
        
        # Validazione
        giornale.validato = True
        # Use func.now() for timezone-aware current timestamp
        giornale.data_validazione = func.now()
        # updated_at will be set automatically by onupdate
        
        # TODO: Aggiungere campo validato_da se esiste nel modello
        # giornale.validato_da_id = current_user_id
        
        await db.commit()
        
        logger.info(f"Giornale {giornale_id} validato da user {current_user_id}")
        
        return {"message": "Giornale validato con successo", "id": str(giornale_id)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore validazione giornale {giornale_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nella validazione del giornale"
        )

# ===== ENDPOINT REFERENCE DATA =====

@router.get("/reference-data")
async def get_reference_data():
    """Dati di riferimento per dropdown e enum"""
    try:
        # Condizioni meteo (da enum)
        condizioni_meteo = [
            {"value": "sereno", "label": "Sereno"},
            {"value": "nuvoloso", "label": "Nuvoloso"}, 
            {"value": "piovoso", "label": "Piovoso"},
            {"value": "nevoso", "label": "Nevoso"},
            {"value": "ventoso", "label": "Ventoso"}
        ]
        
        # Ruoli operatori
        ruoli_operatori = [
            {"value": "responsabile_scavo", "label": "Responsabile Scavo"},
            {"value": "assistente", "label": "Assistente"},
            {"value": "operatore", "label": "Operatore"},
            {"value": "specialista", "label": "Specialista"},
            {"value": "tecnico", "label": "Tecnico"}
        ]
        
        # Specializzazioni
        specializzazioni = [
            {"value": "ceramica", "label": "Ceramica"},
            {"value": "numismatica", "label": "Numismatica"},
            {"value": "antropologia", "label": "Antropologia"},
            {"value": "archeozoologia", "label": "Archeozoologia"},
            {"value": "topografia", "label": "Topografia"},
            {"value": "disegno", "label": "Disegno"},
            {"value": "fotografia", "label": "Fotografia"}
        ]
        
        return {
            "condizioni_meteo": condizioni_meteo,
            "ruoli_operatori": ruoli_operatori,
            "specializzazioni": specializzazioni
        }
        
    except Exception as e:
        logger.error(f"Errore reference data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei dati di riferimento"
        )