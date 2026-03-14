# Integrazione FastZoom

## Scopo

Questa guida descrive i punti di integrazione **attuali** del progetto FastZoom.
Non e una checklist storica di migrazione: i moduli principali (Giornale, US/USM, Harris Matrix, foto, voice) sono gia integrati.

## Architettura di Integrazione

- Entrypoint app: `app/app.py`
- Router API v1 aggregati: `app/routes/api/v1/__init__.py`
- Config runtime: `app/core/config.py`
- Config voice assistant: `app/core/pipecat_settings.py`
- Storage immagini: servizi in `app/services/` (MinIO + Deep Zoom)

## Integrazione API v1

Tutti i domini API sono montati sotto `/api/v1`.
Le aree principali attive includono:

- Auth
- Sites
- Photos
- Deep Zoom
- Documents
- US/USM
- Harris Matrix (+ mapping/validation)
- Giornale/Cantieri
- Teams
- TUS uploads
- Voice (`/api/v1/voice`, `/api/v1/pipecat`)

Per estendere l'API:

1. creare il router in `app/routes/api/v1/<dominio>.py`
2. includerlo in `app/routes/api/v1/__init__.py`
3. verificare dipendenze auth/permessi
4. aggiungere test in `tests/`

## Integrazione Frontend

- Template: `app/templates/`
- Static assets: `app/static/`
- Componenti riusabili: `app/templates/sites/components/` e `app/templates/sites/photos/`
- Le view routes HTML sono in `app/routes/view/`

## Storage e File

FastZoom usa MinIO con profilo configurabile (`local` o `remote`):

- variabili in `.env` (vedi `.env.example`)
- selezione profilo tramite `MINIO_CONFIG_PROFILE`
- Deep Zoom processato dai servizi dedicati in `app/services/deep_zoom*`

## Database e Migrazioni

- ORM: SQLAlchemy async
- Migrazioni: Alembic (`alembic/`, `alembic.ini`)

Comandi standard:

```bash
alembic upgrade head
pytest
```

## Integrazione Voice

- HTTP planning/execution: `app/routes/api/v1/voice.py`
- WebSocket streaming: `app/routes/api/v1/pipecat.py`
- Whitelist tools: `app/services/voice_tools_registry.py`
- Executor in-process ASGI: `app/services/voice_execute.py`

## Checklist per Nuove Integrazioni

1. Definire il confine del dominio (modelli, schema, service, route).
2. Applicare sicurezza (auth + permessi sito).
3. Aggiornare API router aggregato.
4. Aggiungere test unit/integration.
5. Aggiornare la documentazione correlata (`README.md` + file di dominio).
