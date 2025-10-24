# Linee Guida per l'Uso degli Enum nel Progetto FastZoom

## 1. Introduzione e Panoramica

### 1.1 Spiegazione del Problema Risolto

Il progetto FastZoom gestisce dati archeologici multilingua, ma il sistema di database utilizza valori enum standardizzati in inglese per garantire coerenza e integrità dei dati. Tuttavia, gli utenti italiani inseriscono spesso dati in italiano, creando incoerenze tra i valori memorizzati nel database e quelli definiti negli enum.

Questo problema si manifesta in diversi modi:
- **Incoerenza dei dati**: Valori italiani mescolati con valori inglesi nello stesso campo
- **Errori di validazione**: Il sistema rifiuta valori italiani non riconosciuti dagli enum
- **Problemi di query**: Difficoltà nel filtrare dati con valori misti
- **Esperienza utente degradata**: Frustrazione quando i dati inseriti vengono persi o rifiutati

### 1.2 Obiettivi della Standardizzazione degli Enum

La standardizzazione degli enum nel progetto FastZoom mira a:

1. **Garantire coerenza dei dati**: Assicurare che solo valori enum validi in inglese siano memorizzati nel database
2. **Supportare input multilingua**: Permettere agli utenti di inserire dati in italiano, convertendoli automaticamente
3. **Mantenere retrocompatibilità**: Gestire correttamente dati esistenti che potrebbero contenere valori italiani
4. **Fornire un sistema estensibile**: Facilitare l'aggiunta di nuovi mapping per lingue aggiuntive
5. **Migliorare l'esperienza utente**: Eliminare errori di validazione e perdita di dati

### 1.3 Architettura del Sistema di Conversione

Il sistema di conversione enum si basa su un'architettura centralizzata con i seguenti componenti:

```
┌─────────────────────────────────────────────────────────────┐
│                    Input Utente                          │
│                 (Italiano/Inglese)                      │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Sistema di Conversione Enum                   │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           EnumConverter                             │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │        Mapping Dizionario                    │  │  │
│  │  │  Italiano → Inglese                        │  │  │
│  │  │  PhotoType, MaterialType, etc.              │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │        Matching Parziale                      │  │  │
│  │  │  Per valori non esatti                      │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │        Logging e Debug                        │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  Database                                 │
│            (Solo valori inglesi)                        │
└─────────────────────────────────────────────────────────────┘
```

Il sistema è implementato nel file [`app/utils/enum_mappings.py`](app/utils/enum_mappings.py:1) e utilizzato in vari punti dell'applicazione, in particolare nei servizi e nelle API.

## 2. Linee Guida per Sviluppatori

### 2.1 Come Definire Nuovi Enum

Quando si definisce un nuovo enum nel progetto FastZoom, seguire queste linee guida:

#### 2.1.1 Definizione dell'Enum

```python
# In app/models/enums.py (o file appropriato)
from enum import Enum
import sqlalchemy as sa
from sqlalchemy import Enum as SQLEnum

class ArchaeologicalContextType(str, Enum):
    """Enum per i tipi di contesto archeologico"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DISTURBED = "disturbed"
    MIXED = "mixed"
    REDEPOSITED = "redeposited"
    UNKNOWN = "unknown"

# Definizione SQLAlchemy per il database
archaeological_context_type_enum = SQLEnum(
    ArchaeologicalContextType,
    name="archaeological_context_type"
)
```

#### 2.1.2 Aggiunta del Mapping

Aggiungere il mapping italiano → inglese in [`app/utils/enum_mappings.py`](app/utils/enum_mappings.py:1):

```python
# In app/utils/enum_mappings.py
class EnumConverter:
    # Aggiungere il dizionario di mapping
    ARCHAEOLOGICAL_CONTEXT_TYPE_MAPPINGS: Dict[str, str] = {
        # Italiano → Inglese
        'primario': 'primary',
        'secondario': 'secondary',
        'sconvolto': 'disturbed',
        'misto': 'mixed',
        'ridepositato': 'redeposited',
        'sconosciuto': 'unknown',
    }
    
    # Aggiornare il dizionario dei mapping delle classi
    ENUM_CLASS_MAPPINGS: Dict[Type, Dict[str, str]] = {
        # ... mapping esistenti ...
        ArchaeologicalContextType: ARCHAEOLOGICAL_CONTEXT_TYPE_MAPPINGS,
    }
```

#### 2.1.3 Implementazione del Matching Parziale

Per enum complessi, implementare il matching parziale:

```python
@classmethod
def _partial_match_archaeological_context_type(cls, value: str) -> Optional[ArchaeologicalContextType]:
    """Try partial matching for ArchaeologicalContextType"""
    if any(keyword in value for keyword in ['primario', 'principale']):
        return ArchaeologicalContextType.PRIMARY
    elif any(keyword in value for keyword in ['secondario', 'secondario']):
        return ArchaeologicalContextType.SECONDARY
    # ... altri casi ...
    return None
```

### 2.2 Come Utilizzare gli Enum Esistenti

#### 2.2.1 Nei Modelli SQLAlchemy

```python
from app.models.enums import ArchaeologicalContextType, archaeological_context_type_enum

class ArchaeologicalSite(Base):
    __tablename__ = 'archaeological_sites'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    context_type = Column(archaeological_context_type_enum, nullable=True)
```

#### 2.2.2 Nei Servizi

Utilizzare sempre il sistema di conversione centralizzato:

```python
from app.utils.enum_mappings import enum_converter

class ArchaeologicalService:
    def create_site(self, site_data: dict) -> ArchaeologicalSite:
        # Converti i valori enum
        context_type = enum_converter.convert_to_enum(
            ArchaeologicalContextType, 
            site_data.get('context_type')
        )
        
        # Crea il sito con il valore convertito
        site = ArchaeologicalSite(
            name=site_data['name'],
            context_type=context_type
        )
        
        return site
```

#### 2.2.3 Nelle API

```python
from app.utils.enum_mappings import enum_converter

@router.post("/sites")
async def create_site(site_data: dict, db: AsyncSession = Depends(get_async_session)):
    # Converti i valori enum
    context_type = enum_converter.convert_to_enum(
        ArchaeologicalContextType, 
        site_data.get('context_type')
    )
    
    if context_type is None:
        raise HTTPException(
            status_code=400, 
            detail=f"Context type non valido: {site_data.get('context_type')}"
        )
    
    # Procedi con la creazione
    site = ArchaeologicalSite(
        name=site_data['name'],
        context_type=context_type
    )
    
    db.add(site)
    await db.commit()
    
    return {"message": "Sito creato con successo", "site_id": site.id}
```

### 2.3 Come Aggiungere Nuovi Mapping di Conversione

#### 2.3.1 Mapping Diretti

Per mapping diretti 1:1, aggiungere semplicemente al dizionario appropriato:

```python
PHOTO_TYPE_MAPPINGS: Dict[str, str] = {
    # ... mapping esistenti ...
    'nuovo_valore_italiano': 'new_english_value',
}
```

#### 2.3.2 Mapping Complessi

Per mapping che richiedono logica complessa:

```python
@classmethod
def convert_to_enum(cls, enum_class: Type, value: Any) -> Optional[Any]:
    # ... codice esistente ...
    
    # Aggiungere logica specifica per il nuovo enum
    if enum_class == NewEnumType:
        return cls._convert_new_enum_type(value)
    
    # ... resto del codice ...

@classmethod
def _convert_new_enum_type(cls, value: str) -> Optional[NewEnumType]:
    """Conversione personalizzata per NewEnumType"""
    # Logica di conversione personalizzata
    if value.lower() in ['valore1', 'sinonimo1']:
        return NewEnumType.VALUE1
    elif value.lower() in ['valore2', 'sinonimo2']:
        return NewEnumType.VALUE2
    
    return None
```

### 2.4 Best Practices per la Gestione degli Enum

#### 2.4.1 Validazione Sempre Attiva

```python
# ✅ CORRETTO: Usa sempre il sistema di conversione
photo_type = enum_converter.convert_to_enum(PhotoType, user_input)

# ❌ ERRATO: Non usare direttamente l'input utente
photo_type = PhotoType(user_input)  # Può sollevare ValueError
```

#### 2.4.2 Gestione dei Valori Null

```python
# ✅ CORRETTO: Gestisci esplicitamente i valori None
if user_input:
    photo_type = enum_converter.convert_to_enum(PhotoType, user_input)
else:
    photo_type = None

# ❌ ERRATO: Non passare None al convertitore
photo_type = enum_converter.convert_to_enum(PhotoType, None)  # Evita se possibile
```

#### 2.4.3 Logging delle Conversioni

```python
# ✅ CORRETTO: Logga le conversioni per debug
from app.utils.enum_mappings import log_conversion_attempt

converted_value = enum_converter.convert_to_enum(PhotoType, user_input)
success = converted_value is not None
log_conversion_attempt(PhotoType, user_input, converted_value, success)
```

#### 2.4.4 Test delle Conversioni

```python
# ✅ CORRETTO: Scrivi test per tutte le conversioni
def test_photo_type_conversion():
    test_cases = [
        ("vista generale", PhotoType.GENERAL_VIEW),
        ("dettaglio", PhotoType.DETAIL),
        # ... altri casi ...
    ]
    
    for italian_input, expected_enum in test_cases:
        result = enum_converter.convert_to_enum(PhotoType, italian_input)
        assert result == expected_enum
```

## 3. Guida al Sistema di Conversione

### 3.1 Come Funziona il Sistema di Conversione Automatica

Il sistema di conversione automatica segue un processo a più livelli:

```
Input Utente → Normalizzazione → Matching Diretto → Matching Parziale → Fallback → Output
```

#### 3.1.1 Processo di Conversione

1. **Normalizzazione**: L'input viene normalizzato (lowercase, trim)
2. **Matching Diretto**: Tentativo di conversione tramite dizionario di mapping
3. **Matching Parziale**: Tentativo di conversione tramite keyword matching
4. **Fallback**: Tentativo di conversione diretta dell'enum
5. **Logging**: Registrazione del risultato della conversione

#### 3.1.2 Esempio di Conversione

```python
# Input: "Vista Generale del Sito"
# 1. Normalizzazione: "vista generale del sito"
# 2. Matching Diretto: "vista generale del sito" → "general_view" ✅
# 3. Output: PhotoType.GENERAL_VIEW

# Input: "Macrofotografia dettaglio"
# 1. Normalizzazione: "macrofotografia dettaglio"
# 2. Matching Diretto: Non trovato
# 3. Matching Parziale: "macro" → PhotoType.DETAIL ✅
# 4. Output: PhotoType.DETAIL
```

### 3.2 Quando e Come Utilizzare il Metodo `_convert_to_enum`

#### 3.2.1 Quando Utilizzare

Utilizzare il metodo `_convert_to_enum` nei seguenti casi:

1. **Input utente**: Sempre quando si processa input proveniente da utenti
2. **Importazione dati**: Quando si importano dati da fonti esterne
3. **API endpoints**: Quando si ricevono dati tramite API
4. **Form HTML**: Quando si processano dati da form web

#### 3.2.2 Come Utilizzare

```python
from app.utils.enum_mappings import enum_converter

# Nei servizi
class PhotoService:
    def create_photo(self, photo_data: dict):
        # Converti i valori enum
        photo_type = enum_converter.convert_to_enum(
            PhotoType, 
            photo_data.get('photo_type')
        )
        
        material = enum_converter.convert_to_enum(
            MaterialType, 
            photo_data.get('material')
        )
        
        # Crea il record con i valori convertiti
        photo = Photo(
            filename=photo_data['filename'],
            photo_type=photo_type,
            material=material
        )
        
        return photo

# Nelle API
@router.post("/photos")
async def create_photo(photo_data: dict):
    # Converti e valida
    photo_type = enum_converter.convert_to_enum(
        PhotoType, 
        photo_data.get('photo_type')
    )
    
    if photo_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Photo type non valido: {photo_data.get('photo_type')}"
        )
    
    # Procedi con la creazione
    photo = photo_service.create_photo(photo_data)
    return {"photo_id": photo.id}
```

### 3.3 Come Estendere i Mapping per Nuovi Enum

#### 3.3.1 Aggiunta di Nuovo Enum

1. **Definire l'enum** nel file appropriato in `app/models/`
2. **Aggiungere il mapping** in `app/utils/enum_mappings.py`
3. **Implementare il matching parziale** se necessario
4. **Aggiungere i test** per verificare le conversioni
5. **Aggiornare la documentazione**

#### 3.3.2 Esempio Completo

```python
# 1. Definizione dell'enum (app/models/enums.py)
class ExcavationMethodType(str, Enum):
    MANUAL = "manual"
    MECHANICAL = "mechanical"
    MIXED = "mixed"
    UNKNOWN = "unknown"

# 2. Aggiunta del mapping (app/utils/enum_mappings.py)
class EnumConverter:
    EXCAVATION_METHOD_TYPE_MAPPINGS: Dict[str, str] = {
        'manuale': 'manual',
        'meccanico': 'mechanical',
        'misto': 'mixed',
        'sconosciuto': 'unknown',
    }
    
    ENUM_CLASS_MAPPINGS: Dict[Type, Dict[str, str]] = {
        # ... mapping esistenti ...
        ExcavationMethodType: EXCAVATION_METHOD_TYPE_MAPPINGS,
    }

# 3. Implementazione del matching parziale
@classmethod
def _partial_match_excavation_method_type(cls, value: str) -> Optional[ExcavationMethodType]:
    if any(keyword in value for keyword in ['manuale', 'a mano']):
        return ExcavationMethodType.MANUAL
    elif any(keyword in value for keyword in ['meccanico', 'macchina']):
        return ExcavationMethodType.MECHANICAL
    elif any(keyword in value for keyword in ['misto', 'combinato']):
        return ExcavationMethodType.MIXED
    return None

# 4. Aggiornamento del metodo principale
@classmethod
def convert_to_enum(cls, enum_class: Type, value: Any) -> Optional[Any]:
    # ... codice esistente ...
    
    if enum_class == ExcavationMethodType:
        return cls._partial_match_excavation_method_type(normalized_value)
    
    # ... resto del codice ...

# 5. Aggiunta dei test
def test_excavation_method_type_conversion():
    test_cases = [
        ("manuale", ExcavationMethodType.MANUAL),
        ("meccanico", ExcavationMethodType.MECHANICAL),
        ("scavo misto", ExcavationMethodType.MIXED),
    ]
    
    for italian_input, expected_enum in test_cases:
        result = enum_converter.convert_to_enum(ExcavationMethodType, italian_input)
        assert result == expected_enum
```

## 4. Riferimenti Tecnici

### 4.1 Elenco Completo degli Enum Disponibili

Il progetto FastZoom utilizza i seguenti enum principali:

#### 4.1.1 PhotoType
```python
class PhotoType(str, Enum):
    GENERAL_VIEW = "general_view"
    DETAIL = "detail"
    SECTION = "section"
    DRAWING_OVERLAY = "drawing_overlay"
    BEFORE_RESTORATION = "before_restoration"
    AFTER_RESTORATION = "after_restoration"
    EXCAVATION_PROGRESS = "excavation_progress"
    STRATIGRAPHY = "stratigraphy"
    FIND_CONTEXT = "find_context"
    LABORATORY = "laboratory"
    ARCHIVE = "archive"
    WORKING = "working"
    PUBLICATION = "publication"
```

#### 4.1.2 MaterialType
```python
class MaterialType(str, Enum):
    CERAMIC = "ceramic"
    TERRACOTTA = "terracotta"
    BRONZE = "bronze"
    IRON = "iron"
    STONE = "stone"
    MARBLE = "marble"
    GLASS = "glass"
    BONE = "bone"
    WOOD = "wood"
    GOLD = "gold"
    SILVER = "silver"
    LEAD = "lead"
    COPPER = "copper"
    STUCCO = "stucco"
    PLASTER = "plaster"
    MORTAR = "mortar"
    CONCRETE = "concrete"
    TILE = "tile"
    MOSAIC = "mosaic"
    FABRIC = "fabric"
    LEATHER = "leather"
    AMBER = "amber"
    IVORY = "ivory"
    CORAL = "coral"
    METAL_COMPOSITE = "metal_composite"
    COMPOSITE = "composite"
    ORGANIC = "organic"
    OTHER = "other"
```

#### 4.1.3 ConservationStatus
```python
class ConservationStatus(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    VERY_POOR = "very_poor"
    FRAGMENTARY = "fragmentary"
    INCOMPLETE = "incomplete"
    RESTORED = "restored"
    RECONSTRUCTED = "reconstructed"
    LOST = "lost"
    MISSING = "missing"
    DAMAGED = "damaged"
```

#### 4.1.4 DocumentType
```python
class DocumentType(str, Enum):
    RELAZIONE = "relazione"
    RAPPORTO = "rapporto"
    PLANIMETRIA = "planimetria"
    SEZIONE = "sezione"
    PROSPETTO = "prospetto"
    DISEGNO = "disegno"
    FOTOGRAFIA = "fotografia"
    AUTORIZZAZIONE = "autorizzazione"
    BIBLIOGRAFIA = "bibliografia"
    CATALOGO = "catalogo"
    INVENTARIO = "inventario"
    ALTRO = "altro"
```

#### 4.1.5 ContextType
```python
class ContextType(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DISTURBED = "disturbed"
    MIXED = "mixed"
    REDEPOSITED = "redeposited"
    UNKNOWN = "unknown"
```

#### 4.1.6 DepositionType
```python
class DepositionType(str, Enum):
    INTENTIONAL = "intentional"
    ACCIDENTAL = "accidental"
    NATURAL = "natural"
    RITUAL = "ritual"
    FUNERARY = "funerary"
    VOTIVE = "votive"
    UNKNOWN = "unknown"
```

### 4.2 Mapping Completo Italiano → Inglese

#### 4.2.1 PhotoType Mapping

| Italiano | Inglese | Note |
|----------|---------|------|
| vista generale, vista complessiva, panoramica | general_view | Viste generali del sito |
| dettaglio, particolare, macro | detail | Dettagli e macrofotografie |
| sezione, profilo, sezione stratigrafica | section | Sezioni stratigrafiche |
| disegno sovrapposto, rilievo sovrapposto | drawing_overlay | Disegni sovrapposti |
| pre-restauro, prima del restauro | before_restoration | Stato prima del restauro |
| post-restauro, dopo il restauro | after_restoration | Stato dopo il restauro |
| avanzamento scavo, lavori in corso | excavation_progress | Progressione scavo |
| stratigrafia, matrix harris | stratigraphy | Documentazione stratigrafica |
| contesto rinvenimento, in situ | find_context | Contesto di rinvenimento |
| laboratorio, analisi laboratorio | laboratory | Analisi di laboratorio |
| archivio, documentazione archivio | archive | Documentazione d'archivio |
| di lavoro, lavorazione, tecnica | working | Documentazione tecnica |
| pubblicazione, divulgazione | publication | Materiali per pubblicazione |

#### 4.2.2 MaterialType Mapping

| Italiano | Inglese | Note |
|----------|---------|------|
| ceramica, ceramico, vasellame | ceramic | Materiali ceramici |
| terracotta, cotto, laterizio | terracotta | Materiali terracotta |
| bronzo, bronzo antico, lega bronzo | bronze | Leghe di bronzo |
| ferro, ferro battuto, ferroso | iron | Materiali ferrosi |
| pietra, litico, materiale lapideo | stone | Materiali lapidei |
| marmo, marmoreo | marble | Materiali marmorei |
| vetro, vetroso | glass | Materiali vetrosi |
| osso, ossa, materiale osseo | bone | Materiali ossei |
| legno, ligneo, materiale legnoso | wood | Materiali lignei |
| oro, aureo, laminato oro | gold | Materiali aurei |
| argento, argentato, laminato argento | silver | Materiali argentei |
| piombo, piombato, plumbeo | lead | Materiali plumbei |
| rame, ramato, lega di rame | copper | Materiali cuprici |
| stucco | stucco | Stucchi |
| intonaco, rivestimento | plaster | Intonaci |
| malta | mortar | Malte |
| calcestruzzo, cemento | concrete | Materiali cementizi |
| tegola, mattone, laterizio | tile | Materiali laterizi |
| mosaico, tessera musiva | mosaic | Mosaici |
| tessuto, tessile, fibra tessile | fabric | Materiali tessili |
| cuoio, pelle | leather | Materiali cuoio |
| ambra, resina fossile | amber | Ambra |
| avorio, materiale avorio | ivory | Avorio |
| corallo, materiale corallo | coral | Coralli |
| lega metallica, lega | metal_composite | Leghe metalliche |
| composito, materiale composito | composite | Materiali compositi |
| organico, resti organici | organic | Materiali organici |
| altro, sconosciuto | other | Altri materiali |

#### 4.2.3 ConservationStatus Mapping

| Italiano | Inglese | Note |
|----------|---------|------|
| eccellente, ottimo, perfetto, integro | excellent | Stato eccellente |
| buono | good | Stato buono |
| discreto, soddisfacente, accettabile | fair | Stato discreto |
| cattivo, scadente, deteriorato | poor | Stato cattivo |
| pessimo, molto cattivo, gravemente danneggiato | very_poor | Stato pessimo |
| frammentario, frammentato | fragmentary | Stato frammentario |
| incompleto, parziale | incomplete | Stato incompleto |
| restaurato, con restauro | restored | Restaurato |
| ricostruito, ricostruzione, integrato | reconstructed | Ricostruito |
| perduto, scomparso | lost | Perduto |
| mancante, assente | missing | Mancante |
| danneggiato, lesionato | damaged | Danneggiato |

### 4.3 Struttura dei File e Dipendenze

#### 4.3.1 File Principali

```
app/
├── utils/
│   └── enum_mappings.py          # Sistema di conversione enum
├── models/
│   ├── __init__.py              # Definizioni enum
│   └── enums.py                 # Definizioni enum (separato)
├── services/
│   └── photo_service.py         # Utilizzo enum nei servizi
└── routes/
    └── api/
        └── sites_photos.py      # Utilizzo enum nelle API

tests/
└── test_enum_validation.py      # Test del sistema enum

docs/
├── ENUM_GUIDELINES.md          # Questa documentazione
└── ENUM_TESTING_GUIDE.md      # Guida ai test

scripts/
├── check_italian_enum_values.py    # Verifica valori italiani
├── migrate_enum_values.py          # Migrazione dati
└── run_enum_tests.py               # Esecuzione test
```

#### 4.3.2 Dipendenze

Il sistema di enum dipende dai seguenti moduli:

```python
# Dipendenze principali
from typing import Dict, Optional, Any, Type
from loguru import logger

# Import degli enum dal progetto
from app.models import (
    PhotoType, MaterialType, ConservationStatus,
    DocumentType, ContextType, DepositionType
)
```

## 5. Procedure Operative

### 5.1 Come Eseguire la Migrazione dei Dati

#### 5.1.1 Verifica Dati Esistenti

Prima di eseguire la migrazione, verificare la presenza di valori italiani:

```bash
# Esegui lo script di verifica
python check_italian_enum_values.py

# Il report verrà salvato in italian_enum_values_report.json
```

#### 5.1.2 Esecuzione della Migrazione

Utilizzare lo script di migrazione per convertire i dati:

```bash
# Esegui la migrazione in modalità dry-run (senza modifiche)
python migrate_enum_values.py --environment=dev --dry-run

# Esegui la migrazione effettiva
python migrate_enum_values.py --environment=dev

# Per ambiente di produzione
python migrate_enum_values.py --environment=prod
```

#### 5.1.3 Verifica Post-Migrazione

Dopo la migrazione, verificare che tutti i valori siano stati convertiti:

```bash
# Ri-esegui la verifica
python check_italian_enum_values.py

# Dovrebbe restituire 0 record con valori italiani
```

### 5.2 Come Eseguire i Test di Validazione

#### 5.2.1 Esecuzione Completa

```bash
# Esegui tutti i test
python run_enum_tests.py

# Con coverage
python run_enum_tests.py --coverage

# Con report HTML
python run_enum_tests.py --report
```

#### 5.2.2 Esecuzione Test Specifici

```bash
# Solo test unitari
python run_enum_tests.py --unit

# Solo test di integrazione
python run_enum_tests.py --integration

# Solo test di performance
python run_enum_tests.py --performance

# Test specifico
python run_enum_tests.py --test TestEnumConversion::test_photo_type_conversion_complete
```

#### 5.2.3 Verifica Dipendenze

```bash
# Verifica che tutte le dipendenze siano installate
python run_enum_tests.py --check-deps
```

### 5.3 Come Verificare la Coerenza dei Dati

#### 5.3.1 Verifica Manuale

```sql
-- Verifica valori italiani nella tabella photos
SELECT id, filename, photo_type, material, conservation_status
FROM photos 
WHERE photo_type IS NOT NULL 
AND (
    photo_type ILIKE '%vista%' OR 
    photo_type ILIKE '%dettaglio%' OR 
    photo_type ILIKE '%ceramica%' OR
    photo_type ILIKE '%bronzo%' OR
    photo_type ILIKE '%eccellente%' OR
    photo_type ILIKE '%buono%'
);
```

#### 5.3.2 Verifica Automatica

```bash
# Esegui la verifica automatica
python check_italian_enum_values.py

# Il report dettagliato verrà generato automaticamente
```

#### 5.3.3 Monitoraggio Continuo

Impostare un job schedulato per eseguire la verifica periodicamente:

```bash
# Aggiungi a crontab per esecuzione giornaliera
0 2 * * * /path/to/fastzoom/check_italian_enum_values.py
```

## 6. Troubleshooting

### 6.1 Problemi Comuni e Soluzioni

#### 6.1.1 Conversioni Fallite

**Problema**: Le conversioni enum falliscono silenziosamente

**Sintomi**:
- Valori None nel database
- Log di warning conversioni fallite
- Dati mancanti nell'interfaccia

**Diagnosi**:
```python
# Abilita il debug dettagliato
import logging
logging.basicConfig(level=logging.DEBUG)

# Verifica i mapping disponibili
from app.utils.enum_mappings import enum_converter
mappings = enum_converter.get_all_mappings()
print(mappings)
```

**Soluzioni**:
1. Verifica che il valore sia presente nel mapping
2. Aggiungi il mapping mancante
3. Implementa il matching parziale
4. Verifica errori di battitura

#### 6.1.2 Performance Lenta

**Problema**: Le conversioni enum sono lente

**Sintomi**:
- API lente
- Timeout nelle operazioni bulk
- Alto utilizzo CPU

**Diagnosi**:
```python
# Profila le conversioni
import cProfile
import pstats

def profile_conversions():
    for _ in range(10000):
        enum_converter.convert_to_enum(PhotoType, "vista generale")

cProfile.run('profile_conversions()', 'enum_profile.stats')
pstats.Stats('enum_profile.stats').sort_stats('cumulative').print_stats(10)
```

**Soluzioni**:
1. Implementa caching delle conversioni frequenti
2. Ottimizza i matching parziali
3. Utilizza set invece di liste per keyword matching
4. Pre-compila i pattern regex

#### 6.1.3 Valori Non Riconosciuti

**Problema**: Nuovi valori italiani non vengono riconosciuti

**Sintomi**:
- Input utente rifiutato
- Errori di validazione
- Dati persi

**Diagnosi**:
```python
# Testa la conversione specifica
result = enum_converter.convert_to_enum(PhotoType, "nuovo_valore_italiano")
print(f"Conversion result: {result}")

# Verifica i mapping disponibili
print(PhotoType.PHOTO_TYPE_MAPPINGS.get("nuovo_valore_italiano", "NOT FOUND"))
```

**Soluzioni**:
1. Aggiungi il nuovo valore al mapping appropriato
2. Implementa il matching parziale per il nuovo valore
3. Aggiungi test per verificare la conversione
4. Documenta il nuovo valore

### 6.2 Come Diagnosticare Errori di Validazione

#### 6.2.1 Logging Dettagliato

Abilita il logging dettagliato per identificare gli errori:

```python
import logging
from loguru import logger

# Configura il logger per enum
logger.add("enum_conversion.log", level="DEBUG", rotation="10 MB")

# Aggiungi logging personalizzato
def debug_enum_conversion(enum_class, value):
    logger.debug(f"Attempting conversion: {enum_class.__name__} <- '{value}'")
    result = enum_converter.convert_to_enum(enum_class, value)
    logger.debug(f"Conversion result: {result}")
    return result
```

#### 6.2.2 Validazione Step-by-Step

```python
def validate_enum_conversion(enum_class, value):
    """Validazione dettagliata della conversione enum"""
    print(f"Validating: {enum_class.__name__} <- '{value}'")
    
    # 1. Verifica input
    if value is None:
        print("  - Value is None")
        return None
    
    if not isinstance(value, str):
        print(f"  - Value is not string: {type(value)}")
        return None
    
    # 2. Normalizzazione
    normalized = value.lower().strip()
    print(f"  - Normalized: '{normalized}'")
    
    # 3. Matching diretto
    mappings = enum_converter.ENUM_CLASS_MAPPINGS.get(enum_class, {})
    if normalized in mappings:
        result = enum_class(mappings[normalized])
        print(f"  - Direct match: {result}")
        return result
    
    # 4. Matching parziale
    if enum_class == PhotoType:
        result = enum_converter._partial_match_photo_type(normalized)
        if result:
            print(f"  - Partial match: {result}")
            return result
    
    # 5. Tentativo diretto
    try:
        result = enum_class(normalized)
        print(f"  - Direct enum: {result}")
        return result
    except ValueError as e:
        print(f"  - Direct enum failed: {e}")
    
    print("  - No conversion found")
    return None
```

### 6.3 Come Gestire Dati Legacy

#### 6.3.1 Identificazione Dati Legacy

```python
# Script per identificare dati legacy
def identify_legacy_data():
    conn = sqlite3.connect('archaeological.db')
    cursor = conn.cursor()
    
    # Query per trovare valori non standard
    cursor.execute("""
        SELECT table_name, column_name, COUNT(*) as count
        FROM (
            SELECT 'photos' as table_name, 'photo_type' as column_name, photo_type as value
            FROM photos WHERE photo_type IS NOT NULL
            UNION ALL
            SELECT 'photos' as table_name, 'material' as column_name, material as value
            FROM photos WHERE material IS NOT NULL
            UNION ALL
            SELECT 'photos' as table_name, 'conservation_status' as column_name, conservation_status as value
            FROM photos WHERE conservation_status IS NOT NULL
        )
        WHERE value NOT IN (
            'general_view', 'detail', 'section', 'drawing_overlay',
            'before_restoration', 'after_restoration', 'excavation_progress',
            'stratigraphy', 'find_context', 'laboratory', 'archive',
            'working', 'publication',
            'ceramic', 'terracotta', 'bronze', 'iron', 'stone',
            'marble', 'glass', 'bone', 'wood', 'gold', 'silver',
            'lead', 'copper', 'stucco', 'plaster', 'mortar',
            'concrete', 'tile', 'mosaic', 'fabric', 'leather',
            'amber', 'ivory', 'coral', 'metal_composite',
            'composite', 'organic', 'other',
            'excellent', 'good', 'fair', 'poor', 'very_poor',
            'fragmentary', 'incomplete', 'restored', 'reconstructed',
            'lost', 'missing', 'damaged'
        )
        GROUP BY table_name, column_name
        ORDER BY table_name, column_name
    """)
    
    results = cursor.fetchall()
    for table, column, count in results:
        print(f"{table}.{column}: {count} legacy values")
    
    conn.close()
```

#### 6.3.2 Migrazione Dati Legacy

```python
# Script per migrare dati legacy
def migrate_legacy_data():
    conn = sqlite3.connect('archaeological.db')
    cursor = conn.cursor()
    
    # Backup dei dati
    cursor.execute("""
        CREATE TABLE photos_backup AS
        SELECT * FROM photos
    """)
    
    # Migrazione dei valori legacy
    migrations = [
        ('photos', 'photo_type', {
            'vista generale': 'general_view',
            'dettaglio': 'detail',
            # ... altri mapping ...
        }),
        ('photos', 'material', {
            'ceramica': 'ceramic',
            'bronzo': 'bronze',
            # ... altri mapping ...
        }),
        # ... altre tabelle e colonne ...
    ]
    
    for table, column, mapping in migrations:
        for italian, english in mapping.items():
            cursor.execute(f"""
                UPDATE {table}
                SET {column} = ?
                WHERE LOWER({column}) = ?
            """, (english, italian.lower()))
    
    conn.commit()
    print(f"Migrated {cursor.rowcount} records")
    conn.close()
```

#### 6.3.3 Validazione Post-Migrazione

```python
# Script per validare la migrazione
def validate_migration():
    conn = sqlite3.connect('archaeological.db')
    cursor = conn.cursor()
    
    # Verifica che non ci siano più valori legacy
    cursor.execute("""
        SELECT COUNT(*) as remaining_legacy
        FROM photos
        WHERE photo_type NOT IN (
            'general_view', 'detail', 'section', 'drawing_overlay',
            'before_restoration', 'after_restoration', 'excavation_progress',
            'stratigraphy', 'find_context', 'laboratory', 'archive',
            'working', 'publication'
        ) AND photo_type IS NOT NULL
    """)
    
    result = cursor.fetchone()
    if result[0] == 0:
        print("✅ Migration successful: no legacy values found")
    else:
        print(f"❌ Migration incomplete: {result[0]} legacy values remaining")
    
    conn.close()
```

---

## Conclusione

Questo documento fornisce una guida completa per l'uso corretto degli enum nel progetto FastZoom. Seguendo queste linee guida, gli sviluppatori possono:

1. **Garantire la coerenza dei dati** utilizzando sempre il sistema di conversione
2. **Supportare input multilingua** gestendo correttamente i valori italiani
3. **Estendere il sistema** aggiungendo nuovi enum e mapping
4. **Diagnosticare e risolvere problemi** relativi alla conversione enum
5. **Mantenere la qualità del codice** seguendo le best practices documentate

Per qualsiasi domanda o problema non coperto da questa guida, consultare i test esistenti in [`tests/test_enum_validation.py`](tests/test_enum_validation.py:1) o contattare il team di sviluppo.