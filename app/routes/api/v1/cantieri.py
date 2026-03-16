"""
API v1 - Cantieri (Work Sites) Management
Endpoints per gestione cantieri all'interno di siti archeologici.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from datetime import date
from decimal import Decimal, InvalidOperation
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)

router = APIRouter()

# Import association table for operatori
from app.models.giornale_cantiere import giornale_operatori_association

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

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(str(site_id))
    if not normalized_site_id:
        raise SiteNotFoundError(str(site_id))
    
    site_info = None
    for site in user_sites:
        if not site.get("site_id"):
            continue
        
        site_user_id = str(site["site_id"])
        
        # Try multiple matching strategies
        if (site_user_id == normalized_site_id or
            site_user_id == str(site_id) or
            site_user_id.replace("-", "") == normalized_site_id.replace("-", "")):
        
            site_info = site
            break
    
    if not site_info:
        raise SiteNotFoundError(str(site_id))
    
    return site_info


def read_payload_field(payload: Any, *field_names: str, default: Any = None) -> Any:
    """Legge un campo da payload in modo robusto (dict/object, snake_case/camelCase)."""
    sentinel = object()

    for field_name in field_names:
        # Mapping/dict-like access
        try:
            if isinstance(payload, dict):
                value = payload.get(field_name, sentinel)
                if value is not sentinel:
                    return value
            elif hasattr(payload, "get"):
                value = payload.get(field_name, sentinel)
                if value is not sentinel:
                    return value
        except Exception:
            pass

        # Attribute access fallback
        try:
            value = getattr(payload, field_name, sentinel)
            if value is not sentinel:
                return value
        except Exception:
            pass

    return default


def parse_optional_iso_date(value: Any, field_name: str) -> Optional[date]:
    """Converte una data ISO opzionale in `date` con errore HTTP esplicito."""
    if value in (None, ""):
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Formato data non valido per '{field_name}'. Usa YYYY-MM-DD"
        )


def parse_optional_decimal(value: Any, field_name: str) -> Optional[Decimal]:
    """Converte un valore numerico opzionale in Decimal; stringhe vuote diventano None."""
    if value in (None, ""):
        return None

    if isinstance(value, Decimal):
        return value

    try:
        normalized = str(value).strip().replace(",", ".")
        if normalized == "":
            return None
        return Decimal(normalized)
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Formato numerico non valido per '{field_name}'"
        )


def parse_optional_int(value: Any, field_name: str, default: Optional[int] = None) -> Optional[int]:
    """Converte un intero opzionale; stringhe vuote usano default."""
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Formato intero non valido per '{field_name}'"
        )

# Import required models
from app.models.cantiere import Cantiere
from app.models.sites import ArchaeologicalSite
from app.models.giornale_cantiere import GiornaleCantiere
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
    db: AsyncSession = Depends(get_database_session)
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
            and_(Cantiere.site_id == str(site_id), Cantiere.is_active == True)
        )
        
        # Applica filtri
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Cantiere.nome.ilike(search_pattern),
                    Cantiere.codice.ilike(search_pattern),
                    Cantiere.descrizione.ilike(search_pattern),
                    # Campi aggiuntivi per ricerca
                    Cantiere.committente.ilike(search_pattern),
                    Cantiere.impresa_esecutrice.ilike(search_pattern),
                    Cantiere.direttore_lavori.ilike(search_pattern),
                    Cantiere.responsabile_procedimento.ilike(search_pattern),
                    Cantiere.oggetto_appalto.ilike(search_pattern),
                    Cantiere.codice_cup.ilike(search_pattern),
                    Cantiere.codice_cig.ilike(search_pattern)
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
                    GiornaleCantiere.cantiere_id == str(cantiere.id)
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
    db: AsyncSession = Depends(get_database_session)
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
            and_(Cantiere.site_id == str(site_id), Cantiere.is_active == True)
        )
        
        # Applica filtri
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Cantiere.nome.ilike(search_pattern),
                    Cantiere.codice.ilike(search_pattern),
                    Cantiere.descrizione.ilike(search_pattern),
                    # Campi aggiuntivi per ricerca
                    Cantiere.committente.ilike(search_pattern),
                    Cantiere.impresa_esecutrice.ilike(search_pattern),
                    Cantiere.direttore_lavori.ilike(search_pattern),
                    Cantiere.responsabile_procedimento.ilike(search_pattern),
                    Cantiere.oggetto_appalto.ilike(search_pattern),
                    Cantiere.codice_cup.ilike(search_pattern),
                    Cantiere.codice_cig.ilike(search_pattern)
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
                    GiornaleCantiere.cantiere_id == str(cantiere.id)
                )
            )
            giornali_count = giornali_count_result.scalar() or 0
            
            # Conteggio operatori che hanno lavorato su questo cantiere (SQLite compatible)
            operatori_subquery = (
                select(giornale_operatori_association.c.operatore_id)
                .join(GiornaleCantiere, GiornaleCantiere.id == giornale_operatori_association.c.giornale_id)
                .where(GiornaleCantiere.cantiere_id == str(cantiere.id))
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
                # Campi per il giornale dei lavori
                "committente": cantiere.committente,
                "impresa_esecutrice": cantiere.impresa_esecutrice,
                "direttore_lavori": cantiere.direttore_lavori,
                "responsabile_procedimento": cantiere.responsabile_procedimento,
                "oggetto_appalto": cantiere.oggetto_appalto,
                # Campi opzionali
                "codice_cup": cantiere.codice_cup,
                "codice_cig": cantiere.codice_cig,
                "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None,
                # Campi temporali
                "stato": cantiere.stato,
                "stato_formattato": cantiere.stato_formattato,
                "data_inizio_prevista": cantiere.data_inizio_prevista.isoformat() if cantiere.data_inizio_prevista else None,
                "data_fine_prevista": cantiere.data_fine_prevista.isoformat() if cantiere.data_fine_prevista else None,
                "data_inizio_effettiva": cantiere.data_inizio_effettiva.isoformat() if cantiere.data_inizio_effettiva else None,
                "data_fine_effettiva": cantiere.data_fine_effettiva.isoformat() if cantiere.data_fine_effettiva else None,
                # Campi geografici
                "area_descrizione": cantiere.area_descrizione,
                "coordinate_lat": cantiere.coordinate_lat,
                "coordinate_lon": cantiere.coordinate_lon,
                "quota": cantiere.quota,
                # Metadati
                "responsabile_cantiere": cantiere.responsabile_cantiere,
                "tipologia_intervento": cantiere.tipologia_intervento,
                "priorita": cantiere.priorita,
                "e_in_corso": cantiere.e_in_corso,
                "durata_giorni": cantiere.durata_giorni,
                # Statistiche
                "giornali_count": giornali_count,
                "operatori_count": operatori_count,
                # Timestamp
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
    db: AsyncSession = Depends(get_database_session)
):
    """
    Crea un nuovo cantiere per un sito archeologico.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)

        # Normalizza payload in forma dict-like robusta
        if not isinstance(cantiere_data, dict):
            try:
                cantiere_data = dict(cantiere_data)
            except Exception:
                cantiere_data = {}

        nome = read_payload_field(cantiere_data, "nome", default=None)
        if not nome:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Il campo 'nome' è obbligatorio"
            )

        codice = read_payload_field(cantiere_data, "codice", default=None)
        descrizione = read_payload_field(cantiere_data, "descrizione", default=None)

        committente = read_payload_field(cantiere_data, "committente", default=None)
        impresa_esecutrice = read_payload_field(cantiere_data, "impresa_esecutrice", "impresaEsecutrice", default=None)
        direttore_lavori = read_payload_field(cantiere_data, "direttore_lavori", "direttoreLavori", default=None)
        responsabile_procedimento = read_payload_field(cantiere_data, "responsabile_procedimento", "responsabileProcedimento", default=None)
        oggetto_appalto = read_payload_field(cantiere_data, "oggetto_appalto", "oggettoAppalto", default=None)

        codice_cup = read_payload_field(cantiere_data, "codice_cup", "codiceCup", default=None)
        codice_cig = read_payload_field(cantiere_data, "codice_cig", "codiceCig", default=None)
        importo_lavori = parse_optional_decimal(
            read_payload_field(cantiere_data, "importo_lavori", "importoLavori", default=None),
            "importo_lavori"
        )

        data_inizio_prevista = parse_optional_iso_date(
            read_payload_field(cantiere_data, "data_inizio_prevista", "dataInizioPrevista", default=None),
            "data_inizio_prevista"
        )
        data_fine_prevista = parse_optional_iso_date(
            read_payload_field(cantiere_data, "data_fine_prevista", "dataFinePrevista", default=None),
            "data_fine_prevista"
        )

        stato = read_payload_field(cantiere_data, "stato", default="pianificato")
        area_descrizione = read_payload_field(cantiere_data, "area_descrizione", "areaDescrizione", default=None)
        coordinate_lat = read_payload_field(cantiere_data, "coordinate_lat", "coordinateLat", default=None)
        coordinate_lon = read_payload_field(cantiere_data, "coordinate_lon", "coordinateLon", default=None)
        quota = read_payload_field(cantiere_data, "quota", default=None)

        iccd_re_tipo = read_payload_field(cantiere_data, "iccd_re_tipo", "iccdReTipo", default=None)
        iccd_re_metodo = read_payload_field(cantiere_data, "iccd_re_metodo", "iccdReMetodo", default=None)
        iccd_geometria = read_payload_field(cantiere_data, "iccd_geometria", "iccdGeometria", default=None)

        responsabile_cantiere = read_payload_field(cantiere_data, "responsabile_cantiere", "responsabileCantiere", default=None)
        tipologia_intervento = read_payload_field(cantiere_data, "tipologia_intervento", "tipologiaIntervento", default=None)
        priorita = parse_optional_int(
            read_payload_field(cantiere_data, "priorita", default=3),
            "priorita",
            default=3
        )
        
        # Crea nuovo cantiere
        nuovo_cantiere = Cantiere(
            site_id=str(site_id),  # Convert UUID to string for SQLite compatibility
            nome=nome,
            codice=codice,
            descrizione=descrizione,
            # Campi per il giornale dei lavori
            committente=committente,
            impresa_esecutrice=impresa_esecutrice,
            direttore_lavori=direttore_lavori,
            responsabile_procedimento=responsabile_procedimento,
            oggetto_appalto=oggetto_appalto,
            # Campi opzionali
            codice_cup=codice_cup,
            codice_cig=codice_cig,
            importo_lavori=importo_lavori,
            # Campi temporali
            data_inizio_prevista=data_inizio_prevista,
            data_fine_prevista=data_fine_prevista,
            stato=stato,
            # Campi geografici
            area_descrizione=area_descrizione,
            coordinate_lat=coordinate_lat,
            coordinate_lon=coordinate_lon,
            quota=quota,
            # Campi Scientifici ICCD
            iccd_re_tipo=iccd_re_tipo,
            iccd_re_metodo=iccd_re_metodo,
            iccd_geometria=iccd_geometria,
            # Metadati
            responsabile_cantiere=responsabile_cantiere,
            tipologia_intervento=tipologia_intervento,
            priorita=priorita
        )
        
        db.add(nuovo_cantiere)
        await db.commit()
        await db.refresh(nuovo_cantiere)
        
        return {
            "id": str(nuovo_cantiere.id),
            "message": "Cantiere creato con successo",
            "site_info": site_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        payload_keys = list(cantiere_data.keys()) if isinstance(cantiere_data, dict) else []
        logger.exception(
            "Errore creazione cantiere site_id={} payload_keys={} error={}",
            str(site_id),
            payload_keys,
            str(e)
        )
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/cantieri/{cantiere_id}", summary="Dettaglio cantiere", tags=["Cantieri"])
async def v1_get_cantiere_detail(
    cantiere_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
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
                selectinload(Cantiere.giornali_cantiere)
            )
            .where(
                and_(Cantiere.id == str(cantiere_id), Cantiere.is_active == True)
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
                GiornaleCantiere.cantiere_id == str(cantiere_id)
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
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/cantieri/{cantiere_id}", summary="Aggiorna cantiere", tags=["Cantieri"])
async def v1_update_cantiere(
    cantiere_id: UUID,
    cantiere_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Aggiorna un cantiere esistente.
    """
    try:
        # Carica cantiere esistente
        result = await db.execute(
            select(Cantiere).where(Cantiere.id == str(cantiere_id))
        )
        cantiere = result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Verifica accesso al sito
        verify_site_access(cantiere.site_id, user_sites)
        
        # Aggiorna campi base
        if "nome" in cantiere_data:
            cantiere.nome = cantiere_data["nome"]
        if "codice" in cantiere_data:
            cantiere.codice = cantiere_data["codice"]
        if "descrizione" in cantiere_data:
            cantiere.descrizione = cantiere_data["descrizione"]
        
        # Aggiorna campi per il giornale dei lavori
        if "committente" in cantiere_data:
            cantiere.committente = cantiere_data["committente"]
        if "impresa_esecutrice" in cantiere_data:
            cantiere.impresa_esecutrice = cantiere_data["impresa_esecutrice"]
        if "direttore_lavori" in cantiere_data:
            cantiere.direttore_lavori = cantiere_data["direttore_lavori"]
        if "responsabile_procedimento" in cantiere_data:
            cantiere.responsabile_procedimento = cantiere_data["responsabile_procedimento"]
        if "oggetto_appalto" in cantiere_data:
            cantiere.oggetto_appalto = cantiere_data["oggetto_appalto"]
        
        # Aggiorna campi opzionali
        if "codice_cup" in cantiere_data:
            cantiere.codice_cup = cantiere_data["codice_cup"]
        if "codice_cig" in cantiere_data:
            cantiere.codice_cig = cantiere_data["codice_cig"]
        if "importo_lavori" in cantiere_data:
            cantiere.importo_lavori = parse_optional_decimal(cantiere_data["importo_lavori"], "importo_lavori")
        
        # Aggiorna campi temporali
        if "data_inizio_prevista" in cantiere_data:
            cantiere.data_inizio_prevista = date.fromisoformat(cantiere_data["data_inizio_prevista"]) if cantiere_data["data_inizio_prevista"] else None
        if "data_fine_prevista" in cantiere_data:
            cantiere.data_fine_prevista = date.fromisoformat(cantiere_data["data_fine_prevista"]) if cantiere_data["data_fine_prevista"] else None
        if "stato" in cantiere_data:
            cantiere.stato = cantiere_data["stato"]
        
        # Aggiorna campi geografici
        if "area_descrizione" in cantiere_data:
            cantiere.area_descrizione = cantiere_data["area_descrizione"]
        if "coordinate_lat" in cantiere_data:
            cantiere.coordinate_lat = cantiere_data["coordinate_lat"]
        if "coordinate_lon" in cantiere_data:
            cantiere.coordinate_lon = cantiere_data["coordinate_lon"]
        if "quota" in cantiere_data:
            cantiere.quota = cantiere_data["quota"]
            
        # Aggiorna Campi Scientifici ICCD
        if "iccd_re_tipo" in cantiere_data:
            cantiere.iccd_re_tipo = cantiere_data["iccd_re_tipo"]
        if "iccd_re_metodo" in cantiere_data:
            cantiere.iccd_re_metodo = cantiere_data["iccd_re_metodo"]
        if "iccd_geometria" in cantiere_data:
            cantiere.iccd_geometria = cantiere_data["iccd_geometria"]
        
        # Aggiorna metadati
        if "responsabile_cantiere" in cantiere_data:
            cantiere.responsabile_cantiere = cantiere_data["responsabile_cantiere"]
        if "tipologia_intervento" in cantiere_data:
            cantiere.tipologia_intervento = cantiere_data["tipologia_intervento"]
        if "priorita" in cantiere_data:
            cantiere.priorita = parse_optional_int(cantiere_data["priorita"], "priorita", default=cantiere.priorita)
        
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
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/cantieri/{cantiere_id}", summary="Elimina cantiere", tags=["Cantieri"])
async def v1_delete_cantiere(
    cantiere_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Elimina un cantiere (soft delete).
    """
    try:
        # Carica cantiere esistente
        result = await db.execute(
            select(Cantiere).where(Cantiere.id == str(cantiere_id))
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
                GiornaleCantiere.cantiere_id == str(cantiere_id)
            )
        )
        giornali_count = giornali_count_result.scalar() or 0
        
        if giornali_count > 0:
            raise DomainValidationError(f"Impossibile eliminare il cantiere: ci sono {giornali_count} giornali associati")
        
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
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/stats/cantieri", summary="Statistiche cantieri", tags=["Cantieri - Stats"])
async def v1_get_cantieri_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera statistiche generali per i cantieri dell'utente.
    """
    try:
        site_ids = [UUID(site["site_id"]) for site in user_sites]
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
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/sites/{site_id}/stats/cantieri", summary="Statistiche cantieri sito", tags=["Cantieri - Stats"])
async def v1_get_site_cantieri_stats(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
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
                    Cantiere.site_id == str(site_id),
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
                    Cantiere.site_id == str(site_id),
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
                    GiornaleCantiere.site_id == str(site_id),
                    GiornaleCantiere.cantiere_id.in_(
                        select(Cantiere.id).where(
                            and_(
                                Cantiere.site_id == str(site_id),
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
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
