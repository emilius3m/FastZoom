# Script di Inizializzazione Database FastZoom

Questo documento descrive come utilizzare lo script di inizializzazione per configurare il database FastZoom con dati di esempio.

## File Creati

1. **initialize_database.py** - Script Python principale per l'inizializzazione
2. **initialize_database.bat** - Script batch per Windows
3. **initialize_database.sh** - Script shell per Unix/Linux/macOS

## Cosa Crea lo Script

Lo script di inizializzazione crea i seguenti elementi nel database:

### Siti Archeologici

1. **Sito Archeologico A** (SITE001)
   - Nome: "Sito Archeologico A"
   - Codice: "SITE001"
   - Tipo: Abitato
   - Localizzazione: Roma, Lazio, Italia
   - Status: Attivo
   - Status ricerca: Scavo

2. **Sito Archeologico B** (SITE002)
   - Nome: "Sito Archeologico B"
   - Codice: "SITE002"
   - Tipo: Necropoli
   - Localizzazione: Firenze, Toscana, Italia
   - Status: Attivo
   - Status ricerca: Ricognizione

### Utente Amministratore

- **Email**: user@user.com
- **Username**: user
- **Password**: user@user.com
- **Nome**: User
- **Cognome**: Test
- **Permessi**: Amministratore per entrambi i siti

## Come Eseguire lo Script

### Su Windows

1. Apri il Prompt dei comandi o PowerShell
2. Naviga alla directory principale del progetto FastZoom
3. Esegui uno dei seguenti comandi:

   ```cmd
   # Metodo 1: Usa il file batch
   initialize_database.bat
   
   # Metodo 2: Esegui direttamente lo script Python
   python initialize_database.py
   ```

### Su Unix/Linux/macOS

1. Apri il terminale
2. Naviga alla directory principale del progetto FastZoom
3. Rendi eseguibile lo script shell (se necessario):

   ```bash
   chmod +x initialize_database.sh
   ```

4. Esegui uno dei seguenti comandi:

   ```bash
   # Metodo 1: Usa lo script shell
   ./initialize_database.sh
   
   # Metodo 2: Esegui direttamente lo script Python
   python3 initialize_database.py
   ```

## Comportamento dello Script

### Verifica Precedente Esecuzione

Lo script verifica se i dati esistono già nel database prima di crearli:

- Se i siti archeologici esistono già, non vengono ricreati
- Se l'utente esiste già, non viene ricreato
- Se i permessi esistono già, vengono verificati e aggiornati se necessario

### Output dello Script

Durante l'esecuzione, lo script fornisce output dettagliati su:

- Verifica dell'esistenza dei dati
- Creazione dei siti archeologici
- Creazione dell'utente
- Assegnazione dei permessi
- Riepilogo finale con le informazioni di accesso

### Gestione Errori

In caso di errore durante l'esecuzione:

- Lo script mostra un messaggio di errore dettagliato
- Le transazioni del database vengono annullate (rollback)
- Lo script termina con un codice di errore

## Requisiti

### Python

- Python 3.7 o superiore
- Tutte le dipendenze del progetto FastZoom devono essere installate

### Database

- Il database deve essere configurato secondo le impostazioni in `app/core/config.py`
- Di default, viene utilizzato SQLite con il file `archaeological_catalog.db`

## Dopo l'Esecuzione

Una volta completata l'inizializzazione:

1. Avvia l'applicazione FastZoom
2. Accedi con le credenziali fornite
3. Vedrai entrambi i siti archeologici nel tuo dashboard
4. Avrai permessi completi di amministrazione su entrambi i siti

## Troubleshooting

### Problemi Comuni

1. **"Python non è installato"**
   - Installa Python dal sito ufficiale: https://www.python.org/
   - Assicurati che Python sia nel PATH del sistema

2. **"Modulo non trovato"**
   - Assicurati di essere nella directory principale del progetto
   - Installa le dipendenze con: `pip install -r requirements.txt`

3. **"Errore di connessione al database"**
   - Verifica che il database sia configurato correttamente
   - Controlla i permessi di accesso al file del database

4. **"Permesso negato"**
   - Su Windows, esegui il Prompt dei comandi come amministratore
   - Su Unix/Linux/macOS, verifica i permessi della directory

### Log e Debug

Per abilitare il debug, modifica il file `app/core/config.py` e imposta:

```python
DEBUG: bool = True
```

Questo fornirà output più dettagliato durante l'esecuzione.

## Personalizzazione

Per modificare i dati di esempio:

1. Apri il file `initialize_database.py`
2. Modifica le sezioni corrispondenti:
   - `sites_data` per i siti archeologici
   - Dati utente nella funzione `create_user`
   - Permessi nella funzione `assign_admin_permissions`

## Supporto

Per problemi o domande sull'inizializzazione del database:

1. Controlla i log dell'applicazione
2. Verifica la configurazione in `app/core/config.py`
3. Consulta la documentazione del progetto FastZoom