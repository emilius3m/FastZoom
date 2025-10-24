# Guida alle Variabili del Template Word - Giornale di Cantiere

## Introduzione

Il sistema di export del Giornale di Cantiere utilizza template Microsoft Word con placeholder per generare documenti personalizzati. I placeholder vengono sostituiti con dati dinamici provenienti dal database durante l'esportazione.

## Formato dei Placeholder

I placeholder nel template Word seguono questo formato:
```
{{nome_variabile}}
```

Dove `nome_variabile` è l'identificatore univoco del dato da inserire. Tutti i placeholder vengono racchiusi tra doppie parentesi graffe.

## Categorie delle Variabili

### 1. Informazioni sul Sito

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{sito_nome}}` | Nome del sito archeologico | Testo | "Scavi di Pompei" |
| `{{sito_codice}}` | Codice identificativo del sito | Testo | "SIT-001" |
| `{{sito_localita}}` | Località geografica del sito | Testo | "Pompei (NA)" |

### 2. Metadati dell'Export

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{data_export}}` | Data di generazione del documento | Data (gg/mm/aaaa) | "24/10/2025" |
| `{{utente_export}}` | Utente che ha generato l'export | Testo | "Mario Rossi" |
| `{{filtri_applicati}}` | Filtri applicati all'export | Testo | "Periodo: 01/10/2025 - 24/10/2025" |

### 3. Statistiche

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{totale_giornali}}` | Numero totale di giornali | Numero | "15" |
| `{{giornali_validati}}` | Numero di giornali validati | Numero | "12" |
| `{{giornali_pendenti}}` | Numero di giornali in attesa di validazione | Numero | "3" |
| `{{operatori_attivi}}` | Numero di operatori attivi | Numero | "8" |
| `{{percentuale_completamento}}` | Percentuale di completamento validazione | Percentuale | "80%" |

### 4. Informazioni del Giornale

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{giornale_data}}` | Data del giornale | Data (gg/mm/aaaa) | "24/10/2025" |
| `{{giornale_ora_inizio}}` | Ora di inizio lavori | Ora (HH:MM) | "09:00" |
| `{{giornale_ora_fine}}` | Ora di fine lavori | Ora (HH:MM) | "17:30" |
| `{{giornale_compilatore}}` | Nome del compilatore del giornale | Testo | "Luca Bianchi" |
| `{{giornale_responsabile}}` | Responsabile dello scavo | Testo | "Prof. Anna Verdi" |

### 5. Condizioni Operative

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{condizioni_meteo}}` | Condizioni meteorologiche | Testo | "Soleggiato" |
| `{{temperatura_min}}` | Temperatura minima | Numero | "15" |
| `{{temperatura_max}}` | Temperatura massima | Numero | "22" |
| `{{note_meteo}}` | Note sulle condizioni meteo | Testo | "Vento moderato da nord" |

### 6. Descrizione Lavori

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{descrizione_lavori}}` | Descrizione dettagliata dei lavori | Testo lungo | "Scavo stratigrafico nell'area..." |
| `{{modalita_lavorazioni}}` | Modalità delle lavorazioni | Testo | "Scavo manuale con piccole attrezzature" |
| `{{attrezzatura_utilizzata}}` | Attrezzature utilizzate | Testo | "Pennelli, spatole, setacci" |
| `{{mezzi_utilizzati}}` | Mezzi meccanici utilizzati | Testo | "Escavatore mini, carrello elevatore" |

### 7. Documentazione Archeologica

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{us_elaborate}}` | Elenco Unità Stratigrafiche elaborate | Elenco separato da virgole | "US 101, US 102, US 105" |
| `{{usm_elaborate}}` | Elenco USM elaborate | Elenco separato da virgole | "USM 201, USM 202" |
| `{{usr_elaborate}}` | Elenco USR elaborate | Elenco separato da virgole | "USR 301" |
| `{{materiali_rinvenuti}}` | Materiali rinvenuti durante lo scavo | Testo | "Ceramica comune, frammenti di metallo" |
| `{{documentazione_prodotta}}` | Documentazione prodotta | Testo | "Fotografie, rilievi, schede US" |

### 8. Eventi e Problemi

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{sopralluoghi}}` | Sopralluoghi effettuati | Testo | "Sopralluogo Soprintendenza ore 11:00" |
| `{{disposizioni_rup}}` | Disposizioni del RUP | Testo | "Procedere con protezione strutture" |
| `{{disposizioni_direttore}}` | Disposizioni del direttore lavori | Testo | "Intensificare monitoraggio umidità" |
| `{{contestazioni}}` | Contestazioni ricevute | Testo | "Nessuna" |
| `{{sospensioni}}` | Sospensioni dei lavori | Testo | "Sospensione pranzo 12:30-13:30" |
| `{{incidenti}}` | Eventi avversi o incidenti | Testo | "Nessuno" |
| `{{forniture}}` | Forniture ricevute | Testo | "Materiali da cantiere consegnati" |

### 9. Note e Problematiche

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{note_generali}}` | Note generali sul giornale | Testo lungo | "Giornata produttiva con buoni progressi..." |
| `{{problematiche}}` | Problematiche riscontrate | Testo | "Ritardo forniture materiali" |

### 10. Validazione

| Placeholder | Descrizione | Tipo/Formato | Esempio |
|-------------|-------------|--------------|---------|
| `{{stato_validazione}}` | Stato di validazione del giornale | Testo | "Validato" o "In Attesa" |
| `{{data_validazione}}` | Data e ora di validazione | Data/Ora (gg/mm/aaaa HH:MM) | "24/10/2025 18:00" |

## Tabelle Dinamiche

### Tabella Giornali (per export multipli)

Quando si esportano più giornali, il sistema compila automaticamente una tabella con le seguenti colonne:
- Data
- Orari (inizio-fine)
- Responsabile
- Condizioni meteo
- Stato validazione
- Note (troncate a 50 caratteri)

### Tabella Operatori

Per ogni giornale singolo, viene compilata una tabella con gli operatori presenti:
- Nome completo
- Qualifica
- Ruolo

## Come Utilizzare le Variabili nel Template Word

1. **Creare il Template**:
   - Aprire Microsoft Word
   - Progettare il layout desiderato
   - Inserire i placeholder nelle posizioni appropriate

2. **Inserire Placeholder**:
   - Digitare `{{nome_variabile}}` esattamente come indicato
   - Assicurarsi che non ci siano spazi extra all'interno delle parentesi
   - I placeholder possono essere inseriti in paragrafi, tabelle, intestazioni e piè di pagina

3. **Salvare il Template**:
   - Salvare il documento come `.docx` nella directory `app/templates/word/`
   - Utilizzare un nome descrittivo (es. `Giornale_Template_con_Placeholder.docx`)

## Come Aggiungere Nuove Variabili

1. **Modificare il Servizio di Export**:
   - Aprire il file `app/services/giornale_word_export.py`
   - Aggiungere la nuova variabile nel metodo appropriato (`export_single_giornale` o `export_giornali_list`)
   - Utilizzare il metodo `_replace_text(doc, '{{nuova_variabile}}', valore)`

2. **Aggiungere Placeholder nel Template**:
   - Inserire `{{nuova_variabile}}` nel documento Word
   - Testare l'export per verificare il corretto funzionamento

## Formattazione dei Dati

### Date
Le date vengono automaticamente formattate nel formato italiano (gg/mm/aaaa).

### Ore
Le ore vengono formattate nel formato 24 ore (HH:MM).

### Liste
Per le variabili che contengono liste (come `us_elaborate`), gli elementi vengono automaticamente uniti con virgole e spazi.

### Testo Lungo
I campi di testo lunghi mantengono la formattazione originale del template Word.

## Best Practices per la Creazione del Template

1. **Layout Consistente**:
   - Mantenere un layout coerente con i documenti ufficiali del Ministero della Cultura
   - Utilizzare caratteri standard (Times New Roman, Arial, Calibri)

2. **Posizionamento Placeholder**:
   - Inserire i placeholder in posizioni logiche
   - Lasciare spazio sufficiente per contenuti di lunghezza variabile
   - Evitare di inserire placeholder in celle di tabelle che potrebbero dover espandersi

3. **Test del Template**:
   - Testare sempre il template con dati reali
   - Verificare che tutti i placeholder vengano sostituiti correttamente
   - Controllare la formattazione del documento generato

4. **Backup**:
   - Mantenere sempre una copia di backup del template originale
   - Versionare i template quando si apportano modifiche significative

## Risoluzione Problemi Comuni

### Placeholder Non Sostituiti
- Verificare la sintassi esatta del placeholder
- Controllare che non ci siano spazi extra
- Assicurarsi che il dato sia presente nel database

### Formattazione Errata
- Verificare che il placeholder sia in un paragrafo separato se necessario
- Controllare che non ci siano caratteri speciali che interferiscano
- Testare con diversi tipi di dati

### Tabelle Non Compilate
- Assicurarsi che la tabella abbia le intestazioni corrette
- Verificare che i dati siano disponibili nel formato atteso
- Controllare il numero di colonne nella tabella

## Esempio di Utilizzo

```
GIORNALE DI CANTIERE
Sito: {{sito_nome}} ({{sito_codice}})
Località: {{sito_localita}}

Data: {{giornale_data}}
Orario: {{giornale_ora_inizio}} - {{giornale_ora_fine}}
Responsabile: {{giornale_responsabile}}

CONDIZIONI METEO: {{condizioni_meteo}}
Temperatura: {{temperatura_min}}°C - {{temperatura_max}}°C

DESCRIZIONE LAVORI:
{{descrizione_lavori}}

US ELABORATE: {{us_elaborate}}
```

## Supporto

Per problemi o domande sul sistema di template Word:
- Controllare la documentazione tecnica del progetto
- Verificare i log di errore del sistema
- Consultare il team di sviluppo per modifiche complesse