# Fix Upload Non Bloccante + Tiles Background Sequenziali

## Problema Originale
Il processo di generazione tiles bloccava l'upload delle foto archeologiche, causando:
- Upload lentissimo (1 foto alla volta con tiles)
- Impossibilità di caricare più foto velocemente
- Nessun feedback sullo stato di avanzamento tiles

## Soluzione Implementata

### FLUSSO CORRETTO

#### 1. Upload Batch (veloce - TUTTE le foto insieme)
```
Frontend: Seleziona 5 foto → Clicca "Inizia Caricamento"
   ↓
API: UNA SOLA chiamata POST con TUTTE le 5 foto
   ↓
Server: 
  - Upload foto 1 → MinIO ✅
  - Upload foto 2 → MinIO ✅
  - Upload foto 3 → MinIO ✅
  - Upload foto 4 → MinIO ✅
  - Upload foto 5 → MinIO ✅
  - Salva tutti i record DB
   ↓
RITORNA SUBITO (10-20 secondi totali per 5 foto)
```

#### 2. Tiles Background (dopo tutti upload - sequenziale)
```
asyncio.create_task(process_tiles_batch_sequential)
   ↓
Background Task:
  - Foto 1: Carica da MinIO → Genera tiles → Notifica "🎉 [1/5] completato"
  - Foto 2: Carica da MinIO → Genera tiles → Notifica "🎉 [2/5] completato"
  - Foto 3: Carica da MinIO → Genera tiles → Notifica "🎉 [3/5] completato"
  - Foto 4: Carica da MinIO → Genera tiles → Notifica "🎉 [4/5] completato"
  - Foto 5: Carica da MinIO → Genera tiles → Notifica "🎉 [5/5] completato"
```

### Modifiche ai File

#### 1. app/routes/api/sites_photos.py
**Modifiche**:
- Aggiunto `import asyncio`
- Upload processa TUTTE le foto in un ciclo
- SOLO DOPO tutti upload: prepara lista foto per tiles
- Avvia UN SOLO task background per batch processing
- API ritorna immediatamente dopo upload

**Codice Chiave**:
```python
# DOPO tutti gli upload
photos_needing_tiles = []
for photo in uploaded_photos:
    if width > 2000 and height > 2000:
        photos_needing_tiles.append({...})

# UN SOLO task background per TUTTE le foto
if photos_needing_tiles:
    asyncio.create_task(
        deep_zoom_minio_service.process_tiles_batch_sequential(
            photos_list=photos_needing_tiles,
            site_id=str(site_id)
        )
    )
```

#### 2. app/services/deep_zoom_minio_service.py
**Modifiche**:
- Nuovo metodo `process_tiles_batch_sequential()` 
- Processa foto UNA ALLA VOLTA in sequenza
- Notifica per ogni foto completata
- Log dettagliato progresso [X/Y]

**Codice Chiave**:
```python
async def process_tiles_batch_sequential(photos_list, site_id):
    for idx, photo_info in enumerate(photos_list, 1):
        logger.info(f"🔄 [{idx}/{total}] Processing...")
        
        # Carica file
        file_content = await minio.get_file(file_path)
        
        # Genera tiles
        await self._process_tiles_background(...)
        
        logger.info(f"✅ [{idx}/{total}] Completato")
```

#### 3. app/services/photo_service.py
**Modifiche**:
- Fix gestione EXIF IFDRational
- Conversione automatica a float/string

**Codice Chiave**:
```python
if hasattr(value, '__class__') and 'IFDRational' in value.__class__.__name__:
    try:
        serializable_exif[key] = float(value)
    except (ValueError, TypeError):
        serializable_exif[key] = str(value)
```

#### 4. app/templates/sites/components/_upload_modal.html
**Modifiche**:
- Nuovo metodo `uploadAllFilesInBatch()`
- UNA SOLA chiamata API con TUTTE le foto
- FormData con tutti i file insieme

**Codice Chiave**:
```javascript
async uploadAllFilesInBatch() {
    const formData = new FormData();
    
    // Add ALL files at once
    this.selectedFiles.forEach(fileData => {
        formData.append('photos', fileData.file);
    });
    
    // Single API call
    const response = await fetch('/api/photos/upload', {
        method: 'POST',
        body: formData
    });
}
```

#### 5. app/templates/sites/photos.html
**Modifiche**:
- Nuova area notifiche con indicatore tiles in corso
- Notifiche dettagliate con count tiles e livelli
- Polling automatico ogni 3 secondi

**UI Notifiche**:
```html
<!-- Indicatore processing -->
<div x-show="photosBeingProcessed.size > 0">
    🔄 Elaborazione Deep Zoom in corso: X foto
</div>

<!-- Notifica completamento -->
🎉 Deep Zoom completato per: foto.jpg (1024 tiles, 8 livelli)
```

## Test del Sistema

### Scenario 1: Upload 5 foto (3 grandi, 2 piccole)
1. User seleziona 5 foto
2. Clicca "Inizia Caricamento"
3. **Risultato**: Upload completa in ~15-20 secondi
4. Modal si chiude
5. Notifica: "✅ 5 foto caricate! 🔄 Tiles in corso per 3 immagini"
6. Background processa sequenzialmente:
   - Notifica: "🎉 [1/3] Tiles completati per foto1.jpg"
   - Notifica: "🎉 [2/3] Tiles completati per foto2.jpg"
   - Notifica: "🎉 [3/3] Tiles completati per foto3.jpg"

### Scenario 2: Upload 1 foto grande
1. Upload completa in ~3-5 secondi
2. Notifica: "✅ Foto caricata! 🔄 Tiles in corso"
3. Dopo ~30-60 secondi: "🎉 Tiles completati (4297 tiles, 15 livelli)"

## Vantaggi

✅ **Upload velocissimo**: Solo tempo trasferimento file
✅ **Non bloccante**: Tiles in background separato
✅ **Feedback chiaro**: Notifiche per ogni step
✅ **Monitoraggio**: Indicatore visivo processi in corso
✅ **Sequenziale**: Tiles una foto alla volta (non sovraccarica)

## Note Tecniche

- **asyncio.create_task()**: Esecuzione veramente asincrona
- **process_tiles_batch_sequential()**: Un task per tutti, processa in sequenza
- **Polling ogni 3s**: Controlla status e aggiorna UI
- **Notifiche automatiche**: Appena tiles completati