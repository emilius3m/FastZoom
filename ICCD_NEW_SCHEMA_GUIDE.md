# Guida: Come Aggiungere una Nuova Scheda ICCD al Sistema

Questa guida documenta tutti i passaggi necessari per aggiungere una nuova scheda ICCD al sistema FastZoom.

**Esempio pratico**: Integrazione della scheda F 4.00 (Fotografia)

---

## 📋 Prerequisiti

Prima di iniziare, assicurati di avere:
1. ✅ Il file dello schema completo ICCD (es. `iccd_f_schema_complete.py`)
2. ✅ Le funzioni di validazione implementate nel file dello schema
3. ✅ Conoscenza della gerarchia ICCD (padre/figlio, dipendenze)

---

## 🔧 Passaggi per l'Integrazione

### 1️⃣ Verifica del File Schema Completo

**File**: `app/data/iccd_[tipo]_schema_complete.py`

Assicurati che il file contenga:
```python
# Funzione principale che restituisce lo schema
def get_iccd_[tipo]_[versione]_schema() -> Dict[str, Any]:
    return {
        "id": "iccd_[tipo]_[versione]",
        "name": "ICCD [TIPO] [VERSIONE] - [Nome]",
        "version": "[VERSIONE]",
        "category": "[categoria]",
        "schema": { ... },
        "ui_schema": { ... }
    }

# Schema esportato come costante
SCHEMA_[TIPO]_[VERSIONE] = get_iccd_[tipo]_[versione]_schema()

# Funzione di validazione
def validate_[tipo]_record(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    # ... logica validazione
```

**Esempio scheda F**:
```python
SCHEMA_F_400 = get_iccd_f_400_schema()

def validate_f_record(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    # Validazione
```

---

### 2️⃣ Aggiornamento `app/data/iccd_templates.py`

**Operazioni**:
1. Importa lo schema e le funzioni dal file completo
2. Aggiungi le funzioni all'export list `__all__`

**Codice da aggiungere**:
```python
# Import
from app.data.iccd_f_schema_complete import SCHEMA_F_400, get_iccd_f_400_schema, validate_f_record

# Export list
__all__ = [
    # ... altri schema
    'SCHEMA_F_400', 'get_iccd_f_400_schema', 'validate_f_record',
]
```

---

### 3️⃣ Aggiornamento `app/services/iccd_integration_service.py`

**Operazioni**:
1. Importa la funzione getter dello schema
2. Crea la costante dello schema
3. Aggiungi il template al dizionario `ICCD_TEMPLATES`
4. Aggiungi il tipo agli schemi di default

**Codice da aggiungere**:

```python
# 1. Import (dopo gli altri import)
from app.data.iccd_f_schema_complete import get_iccd_f_400_schema

# 2. Crea costante schema (dopo SCHEMA_MA_300)
SCHEMA_F_400 = get_iccd_f_400_schema()

# 3. Aggiungi al dizionario ICCD_TEMPLATES
ICCD_TEMPLATES = {
    # ... altri template
    "F": {
        "name": "ICCD F 4.00 - Fotografia",
        "description": "Schema standard ICCD per catalogazione fotografia storica e contemporanea (v. 4.00) - COMPLETO 23 paragrafi",
        "category": "fotografia",
        "icon": "📷",
        "schema": SCHEMA_F_400["schema"],
        "ui_schema": SCHEMA_F_400["ui_schema"]
    }
}

# 4. Aggiungi agli schemi di default (linea ~343)
default_schemas = ["RA", "CA", "SI", "MA", "F"]
```

**Icone consigliate**:
- 🗺️ SI (Siti)
- 🏛️ CA/MA (Complessi/Monumenti)
- 🏺 RA (Reperti)
- 📷 F (Fotografia)
- 💰 NU (Numismatica)

---

### 4️⃣ Aggiornamento `app/schema/iccd_schemas.py`

**Operazione**: Aggiungi il tipo di schema all'enum `SchemaType`

**Codice da aggiungere**:
```python
class SchemaType(str, Enum):
    """Tipi di schede ICCD supportate"""
    SI = "SI"   # Siti Archeologici
    RA = "RA"   # Reperti Archeologici
    CA = "CA"   # Complessi Archeologici
    MA = "MA"   # Monumenti Archeologici
    F = "F"     # Fotografia  ← NUOVO
    NU = "NU"   # Numismatica
    TMA = "TMA" # Tabula Peutingeriana
```

---

### 5️⃣ Aggiornamento `app/templates/iccd/create_card_selector.html`

**Operazione**: Aggiungi il colore per la visualizzazione del badge della scheda

**Codice da modificare** (funzione `getCardTypeColor`, linea ~265):
```javascript
getCardTypeColor(type) {
    const colors = {
        'SI': 'bg-green-600',
        'CA': 'bg-blue-600', 
        'MA': 'bg-purple-600',
        'RA': 'bg-orange-600',
        'F': 'bg-pink-600',      // ← NUOVO
        'SAS': 'bg-gray-600',
        'NU': 'bg-yellow-600',
        'TMA': 'bg-red-600',
        'AT': 'bg-indigo-600'
    };
    return colors[type] || 'bg-gray-600';
}
```

**Colori Tailwind disponibili**: 
- `bg-green-600`, `bg-blue-600`, `bg-purple-600`, `bg-orange-600`, `bg-pink-600`, `bg-yellow-600`, `bg-red-600`, `bg-indigo-600`, `bg-gray-600`

---

### 6️⃣ Aggiornamento `app/services/iccd_hierarchy_service.py`

**Operazione**: Aggiungi la scheda alle opzioni di creazione disponibili

**Posizione**: Metodo `get_creation_options`, linea ~403

**Considera la gerarchia**:
- **Scheda indipendente** (come CA, MA, F): richiede solo SI esistente, `requires_parent: False`
- **Scheda dipendente** (come RA): richiede un padre specifico, `requires_parent: True`

**Codice da aggiungere** (scheda indipendente):
```python
elif si_count == 1:
    # SI exists - can create CA, MA, RA, F
    options["available_types"].extend([
        # ... altre schede
        {
            "type": "F",
            "name": "Scheda Fotografia",
            "description": "Per fotografie storiche e contemporanee",
            "requires_parent": False,
            "constraint": "Richiede scheda SI esistente"
        }
    ])
```

**Per schede con padre obbligatorio** (come RA):
```python
{
    "type": "RA",
    "name": "Scheda Reperto Archeologico",
    "description": "Per reperti mobili",
    "requires_parent": True,  # ← Richiede padre
    "constraint": "Richiede un padre (SI, CA o MA)"
}
```

---

## 📊 Riepilogo File Modificati

| # | File | Azione | Descrizione |
|---|------|--------|-------------|
| 1 | `app/data/iccd_templates.py` | Import & Export | Importa schema e funzioni, aggiunge a `__all__` |
| 2 | `app/services/iccd_integration_service.py` | Template & Config | Crea schema, aggiunge template e default |
| 3 | `app/schema/iccd_schemas.py` | Enum | Aggiunge tipo a `SchemaType` |
| 4 | `app/templates/iccd/create_card_selector.html` | UI | Aggiunge colore badge |
| 5 | `app/services/iccd_hierarchy_service.py` | Gerarchia | Aggiunge opzioni creazione |

---

## ✅ Checklist di Verifica

Dopo aver completato tutti i passaggi, verifica:

- [ ] Il file schema completo esiste ed è corretto
- [ ] Import/export in `iccd_templates.py` funzionano
- [ ] Template aggiunto a `ICCD_TEMPLATES`
- [ ] Schema aggiunto a `default_schemas`
- [ ] Enum `SchemaType` aggiornato
- [ ] Colore badge aggiunto nel template HTML
- [ ] Opzioni creazione aggiornate in `iccd_hierarchy_service.py`
- [ ] La scheda appare nel selettore "Crea Nuova Scheda ICCD"
- [ ] La validazione dello schema funziona correttamente

---

## 🎯 Testing

Per testare la nuova scheda:

1. **Riavvia il server** FastAPI
2. Accedi a un sito con scheda SI esistente
3. Vai su "Catalogazione ICCD" > "Crea Nuova Scheda"
4. Verifica che la nuova scheda appaia nell'elenco
5. Prova a creare una scheda e verifica la validazione

---

## 🔍 Regole Gerarchiche ICCD

### Gerarchia Standard:
```
SI (Sito Archeologico)
├── CA (Complesso Archeologico)
│   └── RA (Reperto)
├── MA (Monumento Archeologico)
│   └── RA (Reperto)
├── F (Fotografia)
└── RA (Reperto) - può avere SI come padre diretto
```

### Regole:
1. **SI**: Solo 1 per sito, radice della gerarchia
2. **CA/MA/F**: Richiedono SI esistente, non richiedono padre esplicito
3. **RA**: Richiede padre obbligatorio (SI, CA o MA)
4. **Altre schede**: Seguono regole standard (padre opzionale)

---

## 🐛 Troubleshooting

### Problema: La scheda non appare nel selettore
**Soluzione**: Verifica `iccd_hierarchy_service.py` → metodo `get_creation_options`

### Problema: Errore import schema
**Soluzione**: Verifica nome costante in `iccd_templates.py` (es. `SCHEMA_F_400` non `SCHEMA_F_300`)

### Problema: Validazione non funziona
**Soluzione**: Verifica che `validate_[tipo]_record` sia correttamente implementato e importato

### Problema: Colore badge non appare
**Soluzione**: Usa colori Tailwind standard (es. `bg-pink-600`, non colori custom)

---

## 📝 Note Aggiuntive

- Le schede ICCD seguono lo standard ministeriale ICCD MiC
- Ogni scheda ha versioni specifiche (es. 3.00, 4.00)
- Gli schemi sono definiti in Python come dizionari JSON Schema
- La validazione è gestita tramite `jsonschema`
- Il sistema supporta gerarchie multi-livello

---

## 📚 Riferimenti

- [Normative ICCD](http://www.iccd.beniculturali.it/)
- [JSON Schema Documentation](https://json-schema.org/)
- FastZoom ICCD Implementation Guide

---

**Autore**: FastZoom Development Team  
**Data**: 2025-01-04  
**Versione**: 1.0