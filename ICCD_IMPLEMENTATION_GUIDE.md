# 🏺 Sistema ICCD - Implementazione Standard per FastZoom

## 📋 Panoramica

L'implementazione degli **Standard ICCD** (Istituto Centrale per il Catalogo e la Documentazione) nel sistema FastZoom fornisce un sistema di catalogazione archeologica standardizzata conforme alle normative del Ministero della Cultura.

### 🎯 Caratteristiche Implementate

✅ **Schemi Standard ICCD 4.00** - RA, CA, SI  
✅ **Validazione ministeriale** completa  
✅ **Codici NCT univoci** nazionali  
✅ **Generazione PDF** conformi  
✅ **Integrazione** con FastZoom esistente  
✅ **Workflow** P → C → A (Precatalogazione → Catalogazione → Approfondimento)

---

## 🗃️ Struttura Database

### Tabelle Create

| Tabella | Descrizione |
|---------|-------------|
| [`iccd_records`](app/models/iccd_records.py:17) | Schede ICCD complete con dati JSON |
| [`iccd_schema_templates`](app/models/iccd_records.py:168) | Template standard per schemi ICCD |
| [`iccd_validation_rules`](app/models/iccd_records.py:193) | Regole di validazione personalizzabili |

### Modelli Principali

```python
# Scheda ICCD completa
class ICCDRecord(Base):
    nct_region: str          # NCTR - Codice regione (12 = Lazio)
    nct_number: str          # NCTN - Numero catalogo (8 cifre)
    nct_suffix: str          # NCTS - Suffisso opzionale
    schema_type: str         # RA, CA, SI, etc.
    level: str              # P, C, A (Precatalogazione, Catalogazione, Approfondimento)
    iccd_data: dict         # Dati ICCD completi in JSON
    is_validated: bool      # Status validazione
    site_id: UUID          # Collegamento al sito FastZoom
```

---

## 🔗 API Endpoints

### Gestione Schede ICCD

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/iccd/sites/{site_id}/records` | GET | Lista schede ICCD del sito |
| `/api/iccd/sites/{site_id}/records` | POST | Crea nuova scheda ICCD |
| `/api/iccd/sites/{site_id}/records/{record_id}` | GET | Dettagli scheda specifica |
| `/api/iccd/sites/{site_id}/records/{record_id}` | PUT | Aggiorna scheda esistente |
| `/api/iccd/sites/{site_id}/records/{record_id}/pdf` | GET | Genera PDF scheda |
| `/api/iccd/sites/{site_id}/statistics` | GET | Statistiche ICCD del sito |

### Template e Validazione

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/iccd/schema-templates` | GET | Lista template ICCD disponibili |
| `/api/iccd/schema-templates/{schema_type}` | GET | Template specifico (RA, CA, SI) |
| `/api/iccd/validate` | POST | Valida dati ICCD |
| `/api/iccd/sites/{site_id}/initialize` | POST | Inizializza ICCD per sito |

---

## 🖥️ Frontend

### Pagine Implementate

| URL | Descrizione |
|-----|-------------|
| `/sites/{site_id}/iccd` | Lista schede ICCD del sito |
| `/sites/{site_id}/iccd/new` | Form creazione nuova scheda |
| `/sites/{site_id}/iccd/{record_id}` | Visualizzazione scheda |
| `/sites/{site_id}/iccd/{record_id}/edit` | Modifica scheda esistente |

### Componenti Frontend

- **Form interattivo** con Alpine.js
- **Validazione real-time** secondo standard ICCD
- **Progress tracking** per completamento schede
- **Gestione livelli** P/C/A dinamica
- **Selezione materiali** con chips interattive
- **Sistema alert** per feedback utente

---

## 📊 Schemi ICCD Supportati

### RA - Reperto Archeologico 🏺

```json
{
  "CD": "CODICI - Identificativi scheda",
  "OG": "OGGETTO - Definizione e tipologia",
  "LC": "LOCALIZZAZIONE - Geografia e amministrazione", 
  "DT": "CRONOLOGIA - Datazione del reperto",
  "MT": "DATI TECNICI - Materia, tecnica, misure",
  "DA": "DATI ANALITICI - Descrizione e conservazione",
  "AU": "DEFINIZIONE CULTURALE - Ambito culturale (solo livello A)",
  "NS": "NOTIZIE STORICHE - Rinvenimento (solo livello A)",
  "RS": "FONTI DOCUMENTI - Bibliografia (solo livello A)"
}
```

### CA - Complesso Archeologico 🏛️

Schema per strutture architettoniche e complessi edilizi.

### SI - Sito Archeologico 🗺️

Schema per catalogazione siti archeologici completi.

---

## 🔍 Sistema di Validazione

### Livelli di Catalogazione

| Livello | Nome | Sezioni Obbligatorie |
|---------|------|---------------------|
| **P** | Precatalogazione | CD, OG, LC |
| **C** | Catalogazione | CD, OG, LC, DT, MT, DA |
| **A** | Approfondimento | CD, OG, LC, DT, MT, DA, AU, NS, RS |

### Validazioni Implementate

- **NCT Format** - Codice univoco nazionale
- **Terminologia controllata** - Oggetti e materiali standard
- **Coerenza cronologica** - Validazione date e periodi
- **Completezza sezioni** - Verifica campi obbligatori per livello
- **Range valori** - Controllo misure e numeri
- **Pattern validation** - Formati specifici (date, codici)

---

## 📄 Generazione PDF

### Caratteristiche PDF

- **Layout ministeriale** conforme
- **Intestazione ufficiale** SSABAP-RM
- **Codice NCT prominente**
- **Sezioni strutturate** secondo standard
- **Footer validazione** con timestamp
- **Compatibilità** archivio digitale

### Utilizzo

```python
from app.services.iccd_pdf_service import generate_iccd_pdf_quick

# Genera PDF per record ICCD
pdf_content = generate_iccd_pdf_quick(iccd_record, site_name)
```

---

## 🔧 Configurazione e Setup

### 1. Migrazioni Database

```bash
# Eseguire migrazione per creare tabelle ICCD
alembic upgrade head
```

### 2. Inizializzazione Template

```python
# Inizializza template ICCD per un sito
POST /api/iccd/sites/{site_id}/initialize
```

### 3. Dipendenze Aggiuntive

Aggiungere a [`requirements.txt`](requirements.txt):
```
reportlab>=4.0.0  # Per generazione PDF
```

---

## 📋 Workflow Catalogazione

### 1. Precatalogazione (P)
- Identificazione base (CD)
- Definizione oggetto (OG)
- Localizzazione (LC)

### 2. Catalogazione (C)
- Aggiunge cronologia (DT)
- Dati tecnici (MT)
- Analisi descrittiva (DA)

### 3. Approfondimento (A)
- Definizione culturale (AU)
- Notizie storiche (NS)
- Fonti e documenti (RS)

---

## 🏛️ Conformità Standard

### Standard ICCD 4.00
- **Terminologia controllata** ministeriale
- **Codici NCT** secondo normativa
- **Struttura JSON** conforme
- **Validazione** secondo guidelines ufficiali
- **Export PDF** layout standard

### Compatibilità SIGECWeb
- Struttura dati compatibile
- NCT univoci nazionali
- Metadati standard
- Export in formato ministeriale

---

## 🚀 Utilizzo del Sistema

### Per Catalogatori

1. **Accedi** al sito archeologico
2. **Naviga** a "Catalogazione → Schede ICCD"
3. **Crea** nuova scheda selezionando tipo (RA/CA/SI)
4. **Compila** sezioni richieste per livello
5. **Valida** scheda secondo standard
6. **Salva** e genera PDF ufficiale

### Per Amministratori

1. **Inizializza** sistema ICCD per nuovo sito
2. **Gestisci** template e regole validazione
3. **Valida** schede completate
4. **Monitora** statistiche catalogazione
5. **Esporta** dati per SIGECWeb

---

## 📈 Statistiche e Monitoraggio

### Dashboard ICCD
- Conteggio schede per tipo (RA/CA/SI)
- Percentuale completamento per livello
- Status validazione
- Trend catalogazione

### Metriche Disponibili
- Schede totali/validate
- Distribuzione per periodo cronologico
- Materiali più catalogati
- Produttività catalogatori

---

## 🔄 Integrazione Esistente

### Con Sistema FastZoom
- **Siti archeologici** → Schede ICCD collegate
- **Utenti e permessi** → Controllo accesso
- **Form builder** → Template ICCD integrati
- **Storage MinIO** → PDF e allegati
- **Piante archeologiche** → Georeferenziazione

### Con Workflow Scavo
- **Unità di scavo** → Reperti catalogati ICCD
- **Dati archeologici** → Sincronizzazione automatica
- **Foto reperti** → Collegamento alle schede
- **Team management** → Ruoli catalogazione

---

## 📚 File Implementati

### Backend
- [`app/models/iccd_records.py`](app/models/iccd_records.py) - Modelli database
- [`app/routes/api/iccd_records.py`](app/routes/api/iccd_records.py) - API endpoints
- [`app/services/iccd_validation_service.py`](app/services/iccd_validation_service.py) - Validazione standard
- [`app/services/iccd_pdf_service.py`](app/services/iccd_pdf_service.py) - Generazione PDF
- [`app/services/iccd_integration_service.py`](app/services/iccd_integration_service.py) - Integrazione sistema
- [`app/data/iccd_templates.py`](app/data/iccd_templates.py) - Template JSON standard

### Frontend  
- [`app/templates/sites/iccd_records.html`](app/templates/sites/iccd_records.html) - Lista schede
- [`app/templates/sites/iccd_catalogation.html`](app/templates/sites/iccd_catalogation.html) - Form catalogazione

### Database
- [`alembic/versions/add_iccd_tables.py`](alembic/versions/add_iccd_tables.py) - Migrazione tabelle

### Test
- [`test_iccd_implementation.py`](test_iccd_implementation.py) - Verifica implementazione

---

## 🏛️ Benefici per l'Archeologia

### ✅ **Standardizzazione Nazionale**
- Conformità agli standard ministeriali ICCD
- Interoperabilità con SIGECWeb
- Codici NCT univoci nazionali
- Terminologia controllata

### ✅ **Workflow Efficiente**  
- Catalogazione progressiva P → C → A
- Validazione automatica in tempo reale
- Generazione PDF immediata
- Integrazione con scavo digitale

### ✅ **Qualità Scientifica**
- Metadati standardizzati
- Controllo qualità automatico
- Tracciabilità modifiche
- Sistema validazione peer

### ✅ **Compliance Ministeriale**
- Standard ICCD 4.00 completo
- Export compatibile SIGECWeb
- Documentazione ufficiale
- Archivio digitale conforme

---

Il sistema FastZoom ora supporta completamente la **catalogazione archeologica standardizzata** secondo le normative del Ministero della Cultura, garantendo conformità agli standard ICCD e piena integrazione con i workflow di scavo digitale esistenti.