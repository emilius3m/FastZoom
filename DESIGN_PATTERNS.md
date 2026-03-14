# Design Patterns - FastZoom

## Obiettivo

Questo documento riassume i pattern realmente usati nel codice corrente per mantenere coerenza architetturale.

## Pattern Principali

### 1. Router + Service Separation

- I router (`app/routes/`) gestiscono request/response e dipendenze FastAPI.
- I servizi (`app/services/`) centralizzano la logica applicativa.
- I repository (`app/repositories/`) incapsulano l'accesso dati dove presente.

Flusso tipico:

`Route -> Service -> Repository/DB -> Response`

### 2. Dependency Injection (FastAPI)

L'app usa `Depends(...)` per:

- sessioni database async
- autenticazione e context utente
- controllo accesso multi-sito

Questo riduce l'accoppiamento e facilita i test.

### 3. Multi-Tenant per Sito

Le operazioni sono in gran parte site-scoped:

- il contesto sito e validato lato API
- i permessi derivano da associazioni utente-sito
- la UI e le API filtrano per siti accessibili

### 4. Whitelist Pattern (Voice)

Nel voice layer, il modello non puo invocare endpoint arbitrari:

- registry centralizzato in `app/services/voice_tools_registry.py`
- validazione argomenti prima dell'esecuzione
- esecuzione via ASGI in-process (`voice_execute.py`)

### 5. Adapter/Facade per Integrazioni Esterne

I servizi fungono da adapter verso sistemi esterni:

- MinIO storage
- Deep Zoom processing
- provider AI voice/LLM

La logica dominio resta separata dalla libreria esterna.

### 6. Centralized Settings

Configurazioni in classi Pydantic settings:

- `app/core/config.py`
- `app/core/pipecat_settings.py`

Benefici: validazione, default sicuri, mapping consistente `.env` -> runtime.

## Decisioni Pratiche

- Preferire funzioni/method service riusabili invece di logica duplicata nei router.
- Evitare accesso diretto al DB nei template/view.
- Tenere i router sottili (coordinamento, non business logic).
- Aggiungere nuove integrazioni passando da service layer.

## Quando Introdurre Nuovi Pattern

Introdurre un pattern nuovo solo se:

1. riduce complessita ciclica o duplicazione
2. e testabile con il setup corrente
3. non aumenta eccessivamente il costo di manutenzione
