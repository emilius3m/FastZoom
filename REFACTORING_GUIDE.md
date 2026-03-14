# Refactoring Guide - FastZoom

## Obiettivo

Guida operativa per refactoring incrementale senza regressioni funzionali.

## Principi

1. Refactoring piccolo e verificabile.
2. Nessuna modifica comportamentale non intenzionale.
3. Test automatici o smoke test per ogni step.
4. Aggiornamento documentazione nello stesso change set.

## Strategia Consigliata

### Fase 1: Stabilizzazione

- Rimuovere codice morto evidente.
- Eliminare import circolari/local anti-pattern.
- Uniformare naming tra router/service/schema.

### Fase 2: Consolidamento Layer

- Spostare business logic dai router ai servizi.
- Ridurre branch complessi in metodi piccoli.
- Centralizzare validazioni ripetute.

### Fase 3: Contratti e Schemi

- Allineare request/response schema Pydantic agli endpoint reali.
- Evitare payload ambigui (campi opzionali senza semantica chiara).
- Versionare gli endpoint solo quando necessario.

### Fase 4: Performance e Affidabilita

- Misurare prima (query count, tempi endpoint critici).
- Ottimizzare query e serializzazione dove serve.
- Verificare code path upload/Deep Zoom/voice.

## Checklist per Pull Request di Refactoring

- [ ] comportamento invariato o variazione esplicitata
- [ ] test aggiornati (o aggiunti)
- [ ] logging coerente nei path critici
- [ ] nessuna regressione di sicurezza (auth/permessi sito)
- [ ] documentazione aggiornata

## Aree Sensibili del Progetto

- `app/routes/api/v1/*`: superficie API pubblica.
- `app/services/*`: logica dominio e integrazioni.
- `app/core/security.py`: authn/authz.
- `app/services/deep_zoom*`: pipeline immagini.
- `app/routes/api/v1/voice.py` + `pipecat.py`: comandi vocali.

## Sequenza Suggerita per Nuovo Refactoring

1. Aprire issue con obiettivo tecnico chiaro.
2. Definire metriche di successo (es. riduzione complessita, test verdi).
3. Eseguire refactoring per feature slice (non per file gigantico).
4. Eseguire `pytest` e controlli minimi manuali.
5. Aggiornare docs correlate.

## Done Criteria

Un refactoring e concluso quando:

- il codice e piu semplice da mantenere
- i test passano
- le API attese restano compatibili
- la documentazione descrive lo stato attuale
