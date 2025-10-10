# Istruzioni per l'integrazione del Giornale di Cantiere in FastZoom

## 1. AGGIORNAMENTO MODELLI ESISTENTI

### A. Aggiornare app/models/sites.py
Aggiungere questa relazione alla classe `ArchaeologicalSite`:

```python
# Relazione con i giornali di cantiere
giornali_cantiere = relationship("GiornaleCantiere", back_populates="site", cascade="all, delete-orphan")
```

### B. Aggiornare app/database/base.py  
Nella funzione `init_models()`, aggiungere gli import:

```python
# Import giornale di cantiere
from ..models.giornale_cantiere import GiornaleCantiere, OperatoreCantiere  # noqa: F401
```

## 2. CREARE I NUOVI FILE

### A. Copiare i file creati nella struttura corretta:
- `giornale-cantiere-models.py` → `app/models/giornale_cantiere.py`
- `giornale-cantiere-schemas.py` → `app/schemas/giornale_cantiere.py` 
- `giornale-cantiere-routes.py` → `app/routes/api/giornale_cantiere.py`

### B. Creare la route view (prossimo file da generare):
- `app/routes/view/giornale_cantiere.py` - Route HTML per le pagine web

### C. Creare il template HTML:
- `app/templates/pages/giornale_cantiere.html` - Template con Alpine.js

## 3. AGGIORNARE app/app.py

Aggiungere import e registrazione router:

```python
# Import del router giornale cantiere
from app.routes.api.giornale_cantiere import router as giornale_cantiere_api_router
from app.routes.view.giornale_cantiere import router as giornale_cantiere_view_router

# Registrazione API router
app.include_router(
    giornale_cantiere_api_router,
    tags=["giornale-cantiere"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# Registrazione view router
app.include_router(
    giornale_cantiere_view_router,
    tags=["Pages", "Giornale Cantiere"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)
```

## 4. MIGRATION DATABASE

Creare migration Alembic:

```bash
# Dalla root del progetto
alembic revision --autogenerate -m "add giornale cantiere tables"
alembic upgrade head
```

## 5. STRUTTURA FINALE

```
app/
├── models/
│   ├── sites.py (AGGIORNATO)
│   └── giornale_cantiere.py (NUOVO)
├── schemas/
│   └── giornale_cantiere.py (NUOVO)
├── routes/
│   ├── api/
│   │   └── giornale_cantiere.py (NUOVO)
│   └── view/
│       └── giornale_cantiere.py (NUOVO)
├── templates/
│   └── pages/
│       └── giornale_cantiere.html (NUOVO)
├── database/
│   └── base.py (AGGIORNATO)
└── app.py (AGGIORNATO)
```

## 6. FUNZIONALITÀ IMPLEMENTATE

### API Endpoints:
- `POST /api/giornale-cantiere/operatori` - Crea operatore
- `GET /api/giornale-cantiere/operatori` - Lista operatori con filtri
- `POST /api/giornale-cantiere/` - Crea giornale
- `GET /api/giornale-cantiere/site/{site_id}` - Lista giornali per sito
- `GET /api/giornale-cantiere/{id}` - Dettaglio giornale
- `PUT /api/giornale-cantiere/{id}` - Aggiorna giornale
- `POST /api/giornale-cantiere/{id}/valida` - Valida giornale
- `DELETE /api/giornale-cantiere/{id}` - Elimina giornale
- `GET /api/giornale-cantiere/site/{site_id}/stats` - Statistiche

### Sicurezza:
- Autenticazione con blacklist token
- Controllo accessi per sito
- Permessi di modifica (solo responsabile/superuser)
- Validazione dati Pydantic
- Protezione CSRF per form

### Conformità Normativa:
- Campi obbligatori secondo normative italiane
- Enum per condizioni meteo
- Tracking US/USM/USR elaborate
- Gestione sopralluoghi e disposizioni
- Firma digitale e validazione
- Versioning delle modifiche

## 7. PROSSIMI PASSI

1. Copiare i file nella struttura corretta
2. Aggiornare i file esistenti come indicato
3. Eseguire la migration
4. Creare view routes e template (prossimo file)
5. Testare le funzionalità

Il sistema è progettato per integrarsi perfettamente con l'architettura esistente di FastZoom, mantenendo tutte le convenzioni di sicurezza, autenticazione e multi-sito.