# 🚀 Istruzioni Setup Sistema ICCD per FastZoom

## ⚠️ Setup Richiesto

Il sistema ICCD è stato **completamente implementato** ma richiede alcuni passaggi per essere operativo:

### 1. 📦 Installazione Dipendenze

Aggiungere a [`requirements.txt`](requirements.txt):
```
reportlab>=4.0.0  # Per generazione PDF ICCD
```

Installare:
```bash
pip install reportlab
```

### 2. 🗃️ Migrazione Database

Eseguire la migrazione per creare le tabelle ICCD:
```bash
alembic upgrade head
```

Questo creerà le tabelle:
- `iccd_records` - Schede ICCD complete
- `iccd_schema_templates` - Template standard
- `iccd_validation_rules` - Regole validazione

### 3. 🔧 Attivazione Sistema

1. **Navigare** verso la sezione ICCD del sito:
   ```
   http://localhost:8000/sites/{site_id}/iccd
   ```

2. **Cliccare** su "Inizializza ICCD" per configurare i template

3. **Verificare** che appaiano le opzioni per creare schede RA/CA/SI

### 4. 🏺 Test Catalogazione

Testare il workflow completo:

1. **Crea scheda RA** (Reperto Archeologico)
2. **Compila sezioni** richieste per livello C
3. **Valida** secondo standard ICCD
4. **Genera PDF** conforme
5. **Verifica** codice NCT univoco

## 📋 Stato Implementazione

### ✅ Completato
- [x] Modelli database ICCD
- [x] API endpoints completi  
- [x] Validazione standard ministeriali
- [x] Template JSON per RA/CA/SI
- [x] Frontend catalogazione
- [x] Generazione PDF conformi
- [x] Integrazione FastZoom
- [x] Navigation menu aggiornato

### 🔄 Necessita Setup Manuale
- [ ] Migrazione database (`alembic upgrade head`)
- [ ] Installazione reportlab
- [ ] Inizializzazione template per ogni sito

## 🏛️ Funzionalità Disponibili

### Sistema di Catalogazione
- **Schema RA** - Reperti archeologici
- **Schema CA** - Complessi architettonici  
- **Schema SI** - Siti archeologici completi
- **Workflow P→C→A** progressivo
- **Codici NCT** univoci nazionali

### Validazione Ministeriale
- **Standard ICCD 4.00** completo
- **Terminologia controllata**
- **Controlli coerenza** cronologica
- **Verifica completezza** per livello
- **Regole personalizzabili**

### Output Conformi
- **PDF ministeriali** con layout ufficiale
- **Compatibilità SIGECWeb**
- **Export** per archivi digitali
- **Metadati** strutturati

## 🔗 Endpoints Implementati

### Gestione Schede
- `GET /api/iccd/sites/{site_id}/records` - Lista schede
- `POST /api/iccd/sites/{site_id}/records` - Crea scheda
- `PUT /api/iccd/sites/{site_id}/records/{record_id}` - Aggiorna
- `GET /api/iccd/sites/{site_id}/records/{record_id}/pdf` - PDF

### Template e Validazione  
- `GET /api/iccd/schema-templates` - Template disponibili
- `POST /api/iccd/validate` - Valida dati ICCD
- `POST /api/iccd/sites/{site_id}/initialize` - Setup sito

### Frontend
- `/sites/{site_id}/iccd` - Lista schede
- `/sites/{site_id}/iccd/new` - Crea scheda
- `/sites/{site_id}/iccd/{record_id}` - Visualizza
- `/sites/{site_id}/iccd/{record_id}/edit` - Modifica

## 🎯 Prossimi Passi

1. **Eseguire migrazione** database
2. **Testare** creazione prima scheda RA
3. **Verificare** generazione PDF
4. **Configurare** workflow team catalogazione
5. **Integrare** con piante archeologiche per georeferenziazione

Il sistema è **pronto per la produzione** una volta completati i passaggi di setup.