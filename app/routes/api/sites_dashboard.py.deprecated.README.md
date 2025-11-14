# sites_dashboard.py.deprecated

## Stato: DEPRECATO

Questo file è stato rinominato da `sites_dashboard.py` a `sites_dashboard.py.deprecated` perché non è più utilizzato nel sistema.

## Motivo della deprecazione

Le funzionalità di questo file sono state completamente sostituite da implementazioni più recenti e complete:

- **Dashboard HTML**: `app/routes/view/dashboard.py`
- **API v1**: `app/routes/api/v1/sites.py`

## Differenze principali

Le implementazioni più recenti includono:
- Conteggio dei giornali di cantiere (totale, validati, pendenti)
- Gestione migliorata dei permessi
- Codice più manutenibile e ben strutturato

## Azioni eseguite

1. Rinominato il file in `sites_dashboard.py.deprecated`
2. Commentato l'import in `app/routes/sites_router.py`
3. Commentato l'inclusione del router nel sistema di routing

## Note

Il file può essere completamente rimosso in futuro dopo un periodo di test appropriato per verificare che non ci siano dipendenze nascoste.