# ER Diagram - FastZoom

## Stato Documento

Questo file e una sintesi architetturale aggiornata del dominio dati FastZoom.
Per il dettaglio completo dei campi fare sempre riferimento ai modelli SQLAlchemy in `app/models/`.

## Domini Principali

- Identity e Access
  - utenti, profili, ruoli, permessi per sito, token blacklist
- Siti archeologici
  - anagrafica sito, stato, metadati geografici
- Stratigrafia
  - US, USM, relazioni Harris Matrix e mapping
- Media e documenti
  - foto, metadati, Deep Zoom, document management
- Operativita cantiere
  - giornale, operatori, mezzi, cantieri
- Catalogazione
  - moduli ICCD e schede correlate

## Relazioni Chiave

1. `users` <-> `user_site_permissions` <-> `archaeological_sites`
2. `archaeological_sites` -> entita operative (US/USM, foto, documenti, cantieri)
3. `sequenza_fisica` (US/USM) -> grafo Harris Matrix
4. oggetti media -> storage object (MinIO) + metadati applicativi

## Fonti di Verita

- Modelli ORM: `app/models/`
- Migrazioni: `alembic/` e `app/migrations/`
- Servizi di dominio: `app/services/`

## Nota Operativa

Se schema o naming cambiano, aggiornare nello stesso ciclo:

1. modelli
2. migrazioni
3. servizi/query
4. documentazione
