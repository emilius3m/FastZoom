# Componente Upload Foto Archeologiche - Documentazione

## Panoramica

Il componente `_photo_upload.html` è un modulo **riutilizzabile** e **configurabile** per l'upload di foto archeologiche completo di metadati. È progettato per essere integrato facilmente in qualsiasi sezione del progetto FastZoom che necessiti di funzionalità di upload file.

## Caratteristiche Principali

### ✅ Funzionalità Core
- **Upload drag & drop** con supporto a trascinamento file
- **Validazione file** (tipo, dimensione, duplicati)
- **Preview immagini** in tempo reale
- **Barra progress** per ogni singolo file e progressione generale
- **Supporto multi-file** con gestione queue
- **Cancellazione upload** durante l'elaborazione

### ✅ Metadati Archeologici
- Numero inventario
- Area di scavo
- Unità stratigrafica (US)
- Materiale (ceramica, bronzo, etc.)
- Tipo foto (vista generale, dettaglio, etc.)
- Data scatto
- Descrizione dettagliata
- Tag multipli

### ✅ Configurabilità Avanzata
- **Personalizzazione completa** tramite data-* attributes
- **Callback personalizzati** per success/error/progress
- **Configurazione limiti** (max files, max dimensione)
- **Temi personalizzati**
- **Modale auto-chiusura** configurabile

## Utilizzo Base

### 1. Includi il template nella tua pagina

```html
<!-- Includi il template -->
{% include 'sites/photos/_photo_upload.html' %}
```

### 2. Attiva il componente

```javascript
// Modo 1: Attraverso button con trigger
document.getElementById('uploadButton').addEventListener('click', () => {
    // Trova il componente e aprilo
    const uploadComponent = document.querySelector('[x-data="photoUploadComponent"]');
    if (uploadComponent && uploadComponent._x_dataStack[0]) {
        uploadComponent._x_dataStack[0].openModal();
    }
});

// Modo 2: Direct API
const uploader = new PhotoUpload({
    uploadUrl: '/api/v1/sites/sito123/photos/upload',
    siteId: 'sito123'
});
uploader.open();
```

## Configurazione Avanzata

### Configurazione tramite data-* attributes

```html
<div x-data="photoUploadComponent"
     data-upload-url="/api/v1/custom/photos/upload"
     data-site-id="sito123"
     data-allowed-types="image/jpeg,image/png,image/tiff"
     data-max-file-size="100MB"
     data-max-files="50"
     data-success-callback="myCustomSuccessHandler"
     data-error-callback="myCustomErrorHandler"
     data-custom-styles="dark"
     data-show-archaeological-fields="true">
    <!-- Component content -->
</div>
```

### Parametri Configurabili

| Parametro | Default | Descrizione | Esempio |
|-----------|---------|-------------|---------|
| `upload_url` | `/api/v1/sites/{site_id}/photos/upload` | Endpoint API | `/api/v1/custom/upload` |
| `site_id` | Auto-detect | ID del sito corrente | `sito-abc123` |
| `allowed_types` | `image/*` | Tipi file consentiti | `image/jpeg,image/png` |
| `max_file_size` | `50MB` | Dimensione massima file | `100MB` |
| `max_files` | `100` | Numero massimo files | `50` |
| `success_callback` | `refreshPhotos` | Funzione callback successo | `handleUploadSuccess` |
| `error_callback` | `showUploadError` | Funzione callback errore | `handleUploadError` |
| `custom_styles` | `default` | Tema visivo | `dark,compact` |
| `show_archaeological_fields` | `true` | Mostra campi archeologici | `false` |

## Callback e Eventi

### Callback Functions

```javascript
// Callback di successo
function myCustomSuccessHandler(result) {
    console.log('Upload completato:', result);
    // result contiene: { uploaded_file_ids: [...], message: "..." }
    
    // Esempio: refresh dati dopo upload
    if (window.photosManagerInstance) {
        window.photosManagerInstance.refreshPhotos(result.uploaded_file_ids);
    }
}

// Callback di errore
function myCustomErrorHandler(error) {
    console.error('Upload fallito:', error);
    // Esempio: mostra errore specifico
    showDetailedError(error.message);
}
```

### Eventi Custom

Il componente emette eventi custom che puoi ascoltare:

```javascript
document.addEventListener('upload:opened', (e) => {
    console.log('Modale upload aperta', e.detail);
});

document.addEventListener('upload:completed', (e) => {
    console.log('Upload completato', e.detail);
    const { result, fileCount, uploadedFileIds } = e.detail;
    
    // Esegui azioni post-upload
    updateFileCounter(fileCount);
    processUploadedFiles(uploadedFileIds);
});

document.addEventListener('upload:error', (e) => {
    console.log('Upload fallito', e.detail);
    logUploadError(e.detail.error);
});

document.addEventListener('files:added', (e) => {
    console.log('File aggiunti:', e.detail);
    updateUIWithNewFiles(e.detail.files);
});
```

## Esempi di Utilizzo nel Progetto FastZoom

### 1. Pagina Photos (Integrazione Esistente)

```html
<!-- In photos.html -->
{% if can_write %}
<!-- Upload Button -->
<button @click="showUploadModal = true"
        class="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg">
    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
    </svg>
    Carica Foto
</button>

<!-- Modale Upload riutilizzabile -->
<div x-data="photoUploadComponent" 
     x-show="showUploadModal"
     class="hidden"
     data-success-callback="refreshPhotos"
     data-site-id="{{ site.id }}">
    <!-- Template incluso dinamicamente -->
</div>
{% endif %}
```

### 2. Sezione Documenti (Nuovo Utilizzo)

```html
<!-- In documentation.html -->
<button id="uploadDocButton" 
        class="btn btn-primary">
    Carica Documento Fotografico
</button>

<div x-data="photoUploadComponent"
     data-upload-url="/api/v1/sites/{{ site.id }}/documents/upload"
     data-site-id="{{ site.id }}"
     data-allowed-types="image/*,.pdf,.doc,.docx"
     data-show-archaeological-fields="false"
     data-success-callback="refreshDocuments"
     class="hidden">
    <!-- Component configurato per documenti -->
</div>

<script>
document.getElementById('uploadDocButton').addEventListener('click', () => {
    const uploadModal = document.querySelector('[x-data="photoUploadComponent"]');
    uploadModal.classList.remove('hidden');
    uploadModal._x_dataStack[0].modalTitle = 'Carica Documento Fotografico';
    uploadModal._x_dataStack[0].openModal();
});
</script>
```

### 3. Dashboard Amministratore (Mass Upload)

```html
<!-- In dashboard admin -->
<div x-data="photoUploadComponent"
     data-upload-url="/api/v1/admin/bulk-upload"
     data-max-files="500"
     data-max-file-size="200MB"
     data-success-callback="handleBulkUploadSuccess"
     data-error-callback="handleBulkUploadError"
     data-auto-close="false">
    <h3>Upload Massivo Foto</h3>
    <!-- Component configurato per bulk upload -->
</div>

<script>
function handleBulkUploadSuccess(result) {
    // Esegui operazioni post-bulk upload
    showBulkUploadReport(result);
    refreshDashboardStatistics();
}
</script>
```

## Integrazione con Alpine.js

### Sincronizzazione con dati esistenti

```javascript
function photosManager() {
    return {
        // ... altri dati esistenti
        
        // Integrazione upload component
        handleUploadSuccess(uploadedFileIds) {
            console.log('Upload completato, file IDs:', uploadedFileIds);
            
            // Refresh lista foto
            this.refreshPhotos(uploadedFileIds);
            
            // Chiudi modale upload
            this.showUploadModal = false;
        },
        
        handleUploadError(error) {
            this.showAlertMessage(`Errore upload: ${error.message}`, 'error');
        },
        
        // Apri modale upload
        openUploadModal() {
            this.showUploadModal = true;
            
            // Pre-compila metadati se necessario
            this.$nextTick(() => {
                const uploadComponent = document.querySelector('[x-data="photoUploadComponent"]');
                if (uploadComponent && uploadComponent._x_dataStack[0]) {
                    uploadComponent._x_dataStack[0].setMetadata({
                        excavation_area: this.currentExcavationArea,
                        material: this.currentMaterial
                    });
                }
            });
        }
    };
}
```

## Styling e Temi

### Temi Predefiniti

```css
/* Tema Default (light) */
.photo-upload-modal.default { /* ... */ }

/* Tema Dark */
.photo-upload-modal.dark { 
    background: #1f2937; 
    color: white; 
}

/* Tema Compact */
.photo-upload-modal.compact { 
    max-width: 600px; 
}

/* Tema Fullscreen */
.photo-upload-modal.fullscreen { 
    max-width: 95vw; 
    max-height: 95vh; 
}
```

### Personalizzazione CSS

```html
<!-- Aggiungi classi personalizzate -->
<style>
.custom-upload-theme {
    --upload-primary-color: #dc2626;
    --upload-bg-color: #fef2f2;
    --upload-border-color: #fca5a5;
}

.custom-upload-theme .upload-button {
    background: var(--upload-primary-color);
}

.custom-upload-theme .drag-area {
    border-color: var(--upload-border-color);
    background: var(--upload-bg-color);
}
</style>
```

## API Backend Richiesta

### Endpoint Expected

L'endpoint di upload dovrebbe accettare:

```
POST /api/v1/sites/{site_id}/photos/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

{
  "files[0]": File,
  "files[1]": File,
  "metadata": {
    "inventory_number": "string",
    "excavation_area": "string", 
    "stratigraphic_unit": "string",
    "material": "string",
    "photo_type": "string",
    "photo_date": "date",
    "description": "string",
    "tags": ["string"],
    "site_id": "string",
    "upload_timestamp": "datetime"
  }
}
```

### Response Expected

```json
{
  "success": true,
  "message": "Upload completato con successo",
  "uploaded_file_ids": ["file_id_1", "file_id_2"],
  "processed_count": 2,
  "failed_count": 0,
  "details": [
    {
      "filename": "photo1.jpg",
      "status": "success",
      "file_id": "file_id_1"
    }
  ]
}
```

## Best Practices

### ✅ Raccomandazioni
1. **Validazione backend**: valida sempre i file lato server
2. **Rate limiting**: implementa limitazioni per prevenire abusi
3. **Monitoring**: logga tutti gli upload per debugging
4. **Security**: verifica permissions e sanitizza input
5. **Error handling**: gestisci gracefully errori di rete

### ❌ Evitare
1. **File payload troppo grandi**: usa chunk upload per file grandi
2. **Bloccare UI**: mantieni sempre UI responsive durante upload
3. **Memory leaks**: distruggi component quando non necessari
4. **No validation**: non fidarti solo della validazione client-side

## Troubleshooting

### Problemi Comuni

**Upload non parte**:
- Verifica URL endpoint
- Controlla token di autenticazione
- Verifica file format supportati

**Progress bar non funziona**:
- Assicurati che il server supporti upload progress
- Controlla che non ci siano proxy che interferiscano

**Metadati non salvati**:
- Verifica che i campi form siano popolati
- Controlla che il backend processi correttamente JSON metadata

**File troppo grandi**:
- Aumenta `max_file_size` nel componente
- Configura limiti upload nel backend (nginx, php, etc.)

## Version History

- **v1.0.0** (2025-11-18): Versione iniziale con tutte le funzionalità base

## Support e Contributi

Per bug report e feature requests:
- Creare issue nel progetto FastZoom
- Contattare il team di sviluppo
- Fare PR con test adeguati

---

*Questo componente è parte integrante del sistema modulare FastZoom per la gestione di collezioni fotografiche archeologiche.*