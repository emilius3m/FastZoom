# Harris Matrix - Technical Notes

## Componenti Principali

- API routes: `app/routes/api/v1/harris_matrix.py`
- Mapping routes: `app/routes/api/v1/harris_matrix_mapping.py`
- Validation routes: `app/routes/api/v1/harris_matrix_validation.py`
- Services: `app/services/harris_matrix_*.py`

## Modello Dati (alto livello)

Le relazioni stratigrafiche sono lette da campi JSON (`sequenza_fisica`) in entita US/USM.
Il servizio produce un grafo con:

- `nodes`
- `edges`
- `metadata` (conteggi, livelli, indicatori)

## Convenzioni Relazioni

Tipi piu usati:

- `copre`
- `taglia`
- `si_appoggia_a`
- `si_lega_a`
- `riempie`
- `uguale_a`

Le varianti inverse vengono normalizzate in fase di parsing.

## Sicurezza e Accesso

Gli endpoint verificano accesso sito tramite dipendenze authn/authz.
Nessun dato Harris Matrix deve essere esposto senza controllo sito.

## Performance

Raccomandazioni:

1. evitare payload eccessivi in un singolo sito senza paginazione quando possibile
2. validare JSON relazionale in scrittura
3. usare operazioni batch quando supportate

## Evoluzione

Per nuove relazioni o regole:

1. aggiornare parser/validator service
2. mantenere backward compatibility su output base (`nodes`, `edges`)
3. aggiungere test dedicati
4. aggiornare questa documentazione
