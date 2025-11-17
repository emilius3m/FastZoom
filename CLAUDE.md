Login endpoint per API/script Python con risposta JSON.

Restituisce:

access_token: Token JWT per autenticazione API (15 min)
refresh_token: Token per rinnovare access_token (7 giorni)
user: Informazioni utente complete con siti
Esempio uso:

response = requests.post(
    "http://localhost:8000/api/v1/auth/login/json",
    json={"username": "user@user.com", "password": "user@user.com"}
)
tokens = response.json()
access_token = tokens["access_token"]



# Guida alla Normalizzazione degli ID dei Siti

## Problema

Nel sistema FastZoom, alcuni siti archeologici hanno ID con formati diversi:
- **UUID standard**: `eb8d88e1-74e3-46d3-8e86-81f926c01cab`
- **Hash esadecimale**: `eeeedd3ceda34bf3b47d749a971b22ba`

Questa inconsistenza può causare problemi quando si tenta di accedere o modificare siti con il formato "hash esadecimale".

## Soluzione Implementata

Abbiamo implementato una funzione di normalizzazione che gestisce entrambi i formati in modo trasparente.

### Funzione `normalize_site_id()`

La funzione è disponibile in:
- `app/routes/view/admin.py`
- `app/routes/api/v1/admin.py`

#### Comportamento

1. **UUID standard con trattini**: Validato e restituito senza modifiche
2. **Hash esadecimale (32 caratteri)**: Convertito in formato UUID standard inserendo i trattini
3. **Formati non validi**: Restituisce `None`

#### Esempi

```python
# UUID standard - rimane invariato
normalize_site_id("eb8d88e1-74e3-46d3-8e86-81f926c01cab")
# Output: "eb8d88e1-74e3-46d3-8e86-81f926c01cab"

# Hash esadecimale - convertito in UUID
normalize_site_id("eeeedd3ceda34bf3b47d749a971b22ba")
# Output: "eeeedd3c-eda3-4bf3-b47d-749a971b22ba"

# Input non valido
normalize_site_id("invalid-id")
# Output: None
```

## Modifiche al Codice

### 1. Backend (Python)

Tutti gli endpoint che accettano `site_id` ora normalizzano l'ID prima di utilizzarlo:

```python
# Prima
site = await db.execute(select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id))

# Dopo
normalized_site_id = normalize_site_id(site_id)
if not normalized_site_id:
    raise HTTPException(status_code=404, detail="ID sito non valido")
site = await db.execute(select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id))
```

### 2. Frontend (JavaScript)

Aggiunta una funzione `normalizeSiteId()` nei template Alpine.js per gestire la normalizzazione lato client:

```javascript
normalizeSiteId(siteId) {
  if (!siteId) return siteId;
  
  // Rimuovi spazi bianchi
  siteId = siteId.trim();
  
  // Se è un UUID standard con trattini, restituiscilo
  if (siteId.includes('-')) {
    return siteId;
  }
  
  // Se è un hash esadecimale senza trattini (32 caratteri)
  if (siteId.length === 32) {
    // Converti in formato UUID standard (inserisci trattini)
    return `${siteId.slice(0,8)}-${siteId.slice(8,12)}-${siteId.slice(12,16)}-${siteId.slice(16,20)}-${siteId.slice(20)}`;
  }
  
  // Altri formati, restituisci come sono
  return siteId;
}
```

## Endpoint Aggiornati

### View Routes
- `GET /admin/sites/{site_id}/edit`
- `GET /admin/sites/{site_id}/users`

### API Routes
- `GET /api/v1/admin/sites/{site_id}`
- `PUT /api/v1/admin/sites/{site_id}`
- `DELETE /api/v1/admin/sites/{site_id}`
- `POST /api/v1/admin/sites/{site_id}/toggle-status`
- `POST /api/v1/admin/sites/{site_id}/dangerous-delete`
- `GET /api/v1/admin/sites/{site_id}/users`

## Test

È possibile verificare il funzionamento della normalizzazione eseguendo:

```bash
python test_site_id_normalization.py
```

## Vantaggi

1. **Compatibilità backward**: I siti esistenti con entrambi i formati continuano a funzionare
2. **Trasparenza**: L'utente non percepisce la differenza tra i formati
3. **Validazione**: Gli ID non validi vengono rifiutati con un messaggio chiaro
4. **Consistenza**: Tutti gli URL interni ora usano ID normalizzati

## Note Tecniche

- La conversione da hash esadecimale a UUID segue lo standard RFC 4122
- La funzione di normalizzazione è idempotente: applicarla più volte non cambia il risultato
- Gli ID normalizzati sono sempre validi come UUID e possono essere usati con le librerie standard Python/JavaScript
- **Fallback multi-livello**: Se l'ID normalizzato non viene trovato nel database, il sistema prova:
  1. L'ID normalizzato (UUID con trattini)
  2. L'ID originale (come fornito nell'URL)
  3. L'hash senza trattini (se l'input è un UUID standard)