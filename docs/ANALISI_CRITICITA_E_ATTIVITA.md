# Analisi del codebase FastZoom: criticità e attività proposte

## 1) Panoramica del codebase

FastZoom è una piattaforma **FastAPI** orientata alla documentazione archeologica con un perimetro applicativo ampio:

- **Entrypoint applicativo** in `app/app.py` con inizializzazione middleware, router API/view, CSRF e startup tasks. 
- **Strato servizi** molto ricco (`app/services/*`) che concentra logica di business, storage (MinIO), deep zoom, dashboard, autorizzazioni.
- **Routing** separato fra API (`app/routes/api` e `app/routes/api/v1`) e view server-side (`app/routes/view`).
- **Persistenza** SQLAlchemy + Alembic, con configurazione e sessioni in `app/database` e modelli in `app/models`.
- **Test suite** Pytest in `tests/`, con marker e configurazioni centralizzate in `pytest.ini`.

## 2) Criticità rilevate

### Criticità A — Bootstrap fragile per dipendenza esterna (MinIO)
Nel servizio MinIO, l'inizializzazione delle bucket viene eseguita nel costruttore (`__init__`) del servizio e l'istanza globale viene creata a import-time. Questo rende fragile il bootstrap locale/CI quando MinIO non è disponibile: basta importare il modulo per innescare tentativi di connessione. 

### Criticità B — Configurazione test non allineata alle dipendenze
`pytest.ini` abilita opzioni `--cov*`, ma nel lock/config principale non emerge `pytest-cov`; in ambiente minimale questo produce errore CLI (`unrecognized arguments: --cov=app ...`).

### Criticità C — Endpoint v1 archeologico ancora stub
La route `v1_get_site_archaeological_plans` è dichiarata ma con TODO e risposta vuota. In produzione rischia di esporre API formalmente presenti ma funzionalmente incomplete.

### Criticità D — Qualità editoriale (refusi/testi incoerenti)
Nel migration helper della API v1 compare la stringa `"Agregazione endpoints archaeological plans in dominio unico"` (refuso: *Aggregazione*).

## 3) Attività proposte (richieste)

Di seguito 4 attività distinte, come richiesto.

### Attività 1 — Correzione refuso
**Titolo:** Correggere il refuso nel migration helper API archeologica.

- **Dove:** `app/routes/api/v1/archaeological.py`
- **Intervento:** sostituire `Agregazione` con `Aggregazione` nelle descrizioni di migrazione.
- **Valore:** migliora professionalità percepita e chiarezza della documentazione API.
- **Definition of Done:** stringhe corrette + controllo rapido endpoint `/api/v1/archaeological/migration/help`.

### Attività 2 — Correzione bug
**Titolo:** Rendere lazy l'inizializzazione MinIO per evitare errori a import-time.

- **Dove:** `app/services/archaeological_minio_service.py`
- **Intervento:**
  1. Evitare chiamate di rete nel costruttore/istanza globale.
  2. Spostare `_initialize_buckets_with_timeout()` in una fase esplicita di startup o in lazy-init al primo uso.
  3. Introdurre fallback robusto per ambiente test (flag `MINIO_ENABLED=false` o dependency override).
- **Valore:** riduce tempi/fallimenti in CI e test locali, separando avvio app da disponibilità MinIO.
- **Definition of Done:** import del modulo senza tentativi socket; test avviabili senza MinIO attivo.

### Attività 3 — Correzione commento/discrepanza documentazione
**Titolo:** Allineare toolchain test e documentazione coverage.

- **Dove:** `pytest.ini`, `pyproject.toml`, `README.md`
- **Intervento (scegliere una policy):**
  - Aggiungere `pytest-cov` alle dipendenze di sviluppo, **oppure**
  - Rimuovere i flag `--cov*` da `pytest.ini` quando il plugin non è garantito.
  - Aggiornare README con prerequisiti test coerenti.
- **Valore:** evita falsi negativi in onboarding/CI e riduce tempo perso in troubleshooting.
- **Definition of Done:** `pytest` parte senza errori di argomenti in ambiente clean.

### Attività 4 — Miglioramento test
**Titolo:** Aggiungere test di regressione su bootstrap senza MinIO.

- **Dove:** nuova suite in `tests/services/` (es. `test_archaeological_minio_bootstrap.py`).
- **Intervento:**
  - Mockare client MinIO e verificare che l'import del servizio non effettui connessioni reali.
  - Testare percorso con MinIO disabilitato e comportamento lazy.
  - Aggiungere marker dedicato (`requires_minio`) per i test che richiedono servizio reale.
- **Valore:** previene regressioni che bloccano tutta la suite test quando MinIO è assente.
- **Definition of Done:** test verde in ambiente senza MinIO e in CI.

## 4) Prioritizzazione suggerita

1. **Bug bootstrap MinIO** (massimo impatto operativo).
2. **Allineamento test toolchain** (sblocca feedback loop).
3. **Test di regressione bootstrap** (stabilizza nel tempo).
4. **Refuso migration helper** (quick win editoriale).
