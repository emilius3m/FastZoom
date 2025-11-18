/**
 * PhotoUpload.js - Modulo JavaScript riutilizzabile per l'upload di foto
 * Progettato per funzionare con il componente _photo_upload.html
 * Estremamente configurabile e riutilizzabile in tutto il progetto FastZoom
 * 
 * @author FastZoom Development Team
 * @version 1.0.0
 * @since 2025-11-18
 */

class PhotoUpload {
    /**
     * Costruttore del componente PhotoUpload
     * @param {Object} options - Opzioni di configurazione
     * @param {string} options.uploadUrl - URL dell'endpoint di upload
     * @param {string} options.siteId - ID del sito corrente
     * @param {string} [options.allowedTypes='image/*'] - Tipi di file consentiti
     * @param {string} [options.maxFileSize='50MB'] - Dimensione massima file
     * @param {number} [options.maxFiles=100] - Numero massimo di files
     * @param {Function} [options.onSuccess] - Callback successo
     * @param {Function} [options.onError] - Callback errore
     * @param {Function} [options.onProgress] - Callback progressione
     * @param {boolean} [options.showArchaeologicalFields=true] - Mostra campi archeologici
     * @param {string} [options.theme='default'] - Tema visuale
     * @param {boolean} [options.autoClose=true] - Chiudi automaticamente dopo successo
     * @param {number} [options.autoCloseDelay=2000] - Ritardo chiusura automatica
     */
    constructor(options = {}) {
        // Merge con opzioni di default
        this.config = {
            uploadUrl: options.uploadUrl || this.getDefaultUploadUrl(),
            siteId: options.siteId || this.getCurrentSiteId(),
            allowedTypes: options.allowedTypes || 'image/*',
            maxFileSize: options.maxFileSize || '50MB',
            maxFiles: options.maxFiles || 100,
            onSuccess: options.onSuccess || null,
            onError: options.onError || null,
            onProgress: options.onProgress || null,
            showArchaeologicalFields: options.showArchaeologicalFields !== false,
            theme: options.theme || 'default',
            autoClose: options.autoClose !== false,
            autoCloseDelay: options.autoCloseDelay || 2000,
            ...options
        };

        // Stato interno
        this.state = {
            isOpen: false,
            files: [],
            isUploading: false,
            uploadProgress: 0,
            uploadDetails: [],
            dragActive: false,
            currentRequest: null
        };

        // Dati metadati
        this.metadata = {
            inventory_number: '',
            excavation_area: '',
            stratigraphic_unit: '',
            material: '',
            photo_type: '',
            photo_date: '',
            description: '',
            tags: []
        };

        // Inizializzazione
        this.init();
    }

    /**
     * Inizializza il componente
     */
    init() {
        console.log('PhotoUpload initialized with config:', this.config);
        this.setupEventListeners();
    }

    /**
     * Configura gli event listeners globali
     */
    setupEventListeners() {
        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.state.isOpen) {
                this.close();
            }
        });

        // Prevent drag events on document when upload modal is closed
        document.addEventListener('dragover', (e) => {
            if (!this.state.isOpen) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'none';
            }
        });

        document.addEventListener('drop', (e) => {
            if (!this.state.isOpen) {
                e.preventDefault();
            }
        });
    }

    /**
     * Apre la modale di upload
     * @param {Object} initialMetadata - Metadati iniziali da pre-compilare
     */
    open(initialMetadata = {}) {
        if (this.state.isOpen) return;

        this.state.isOpen = true;
        this.state.files = [];
        this.state.uploadProgress = 0;
        this.state.uploadDetails = [];
        this.state.dragActive = false;

        // Pre-compila metadati se forniti
        this.metadata = { ...this.metadata, ...initialMetadata };

        // Disabilita scroll del body
        document.body.style.overflow = 'hidden';

        // Trigger evento custom
        this.emit('upload:opened', { metadata: this.metadata });
    }

    /**
     * Chiude la modale di upload
     */
    close() {
        if (!this.state.isOpen) return;

        this.state.isOpen = false;

        // Riabilita scroll del body
        document.body.style.overflow = '';

        // Pulizia stato
        this.reset();

        // Trigger evento custom
        this.emit('upload:closed');
    }

    /**
     * Resetta lo stato del componente
     */
    reset() {
        this.state.files = [];
        this.state.isUploading = false;
        this.state.uploadProgress = 0;
        this.state.uploadDetails = [];
        this.state.dragActive = false;

        // Reset metadati
        this.metadata = {
            inventory_number: '',
            excavation_area: '',
            stratigraphic_unit: '',
            material: '',
            photo_type: '',
            photo_date: '',
            description: '',
            tags: []
        };

        // Reset campi form
        this.resetFormFields();
    }

    /**
     * Resetta i campi del form
     */
    resetFormFields() {
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';

        const tagsInput = document.getElementById('tagsInput');
        if (tagsInput) tagsInput.value = '';
    }

    /**
     * Gestisce la selezione dei file
     * @param {FileList|Array} files - File selezionati
     */
    handleFileSelect(files) {
        const fileArray = Array.from(files);
        this.addFiles(fileArray);
    }

    /**
     * Aggiunge file alla lista
     * @param {Array} newFiles - Nuovi file da aggiungere
     */
    addFiles(newFiles) {
        const maxFileSizeBytes = this.parseFileSize(this.config.maxFileSize);
        const currentFilesCount = this.state.files.length;
        const availableSlots = this.config.maxFiles - currentFilesCount;

        if (availableSlots <= 0) {
            this.notify(`Hai raggiunto il limite massimo di ${this.config.maxFiles} file`, 'warning');
            return;
        }

        // Limita numero di file
        const filesToAdd = newFiles.slice(0, availableSlots);

        filesToAdd.forEach(file => {
            if (this.validateFile(file)) {
                this.createFileObject(file);
            }
        });

        // Trigger evento custom
        this.emit('files:added', { 
            files: this.state.files, 
            totalFiles: this.state.files.length 
        });
    }

    /**
     * Crea un oggetto file con preview
     * @param {File} file - File da processare
     */
    createFileObject(file) {
        if (file.type.startsWith('image/')) {
            // Crea preview per immagini
            const reader = new FileReader();
            reader.onload = (e) => {
                const fileObj = {
                    id: this.generateFileId(),
                    file: file,
                    name: file.name,
                    size: file.size,
                    type: file.type,
                    preview: e.target.result,
                    error: null,
                    status: 'ready'
                };
                this.state.files.push(fileObj);
                this.updateUI();
            };
            reader.readAsDataURL(file);
        } else {
            // File non immagine
            const fileObj = {
                id: this.generateFileId(),
                file: file,
                name: file.name,
                size: file.size,
                type: file.type,
                preview: '/static/img/file-icon.png',
                error: null,
                status: 'ready'
            };
            this.state.files.push(fileObj);
            this.updateUI();
        }
    }

    /**
     * Genera un ID univoco per il file
     * @returns {string} ID univoco
     */
    generateFileId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    }

    /**
     * Rimuove un file dalla lista
     * @param {string} fileId - ID del file da rimuovere
     */
    removeFile(fileId) {
        const index = this.state.files.findIndex(f => f.id === fileId);
        if (index !== -1) {
            this.state.files.splice(index, 1);
            this.updateUI();
            this.emit('file:removed', { fileId, remainingFiles: this.state.files.length });
        }
    }

    /**
     * Rimuove tutti i file
     */
    clearFiles() {
        this.state.files = [];
        this.updateUI();
        this.emit('files:cleared');
    }

    /**
     * Valida un file
     * @param {File} file - File da validare
     * @returns {boolean} True se valido
     */
    validateFile(file) {
        // Valida tipo file
        if (!this.validateFileType(file)) {
            this.notify(`File ${file.name}: tipo non supportato`, 'error');
            return false;
        }

        // Valida dimensione file
        const maxFileSizeBytes = this.parseFileSize(this.config.maxFileSize);
        if (file.size > maxFileSizeBytes) {
            this.notify(`File ${file.name}: dimensione troppo grande (${this.formatFileSize(file.size)} > ${this.config.maxFileSize})`, 'error');
            return false;
        }

        // Controlla duplicati
        const isDuplicate = this.state.files.some(f => 
            f.name === file.name && f.size === file.size
        );
        if (isDuplicate) {
            this.notify(`File ${file.name}: già selezionato`, 'warning');
            return false;
        }

        return true;
    }

    /**
     * Valida il tipo di file
     * @param {File} file - File da validare
     * @returns {boolean} True se valido
     */
    validateFileType(file) {
        if (this.config.allowedTypes === '*') return true;
        if (this.config.allowedTypes === 'image/*') return file.type.startsWith('image/');

        const allowedTypes = this.config.allowedTypes.split(',').map(type => type.trim());
        return allowedTypes.some(type => {
            if (type.endsWith('/*')) {
                return file.type.startsWith(type.slice(0, -1));
            }
            return file.type === type;
        });
    }

    /**
     * Avvia l'upload dei file
     */
    async uploadFiles() {
        if (this.state.files.length === 0) {
            this.notify('Nessun file da caricare', 'error');
            return;
        }

        if (this.state.isUploading) {
            this.notify('Upload già in corso', 'warning');
            return;
        }

        this.state.isUploading = true;
        this.state.uploadProgress = 0;
        
        // Inizializza dettagli upload
        this.state.uploadDetails = this.state.files.map((fileObj, index) => ({
            id: fileObj.id,
            index,
            fileName: fileObj.name,
            progress: 0,
            status: 'pending'
        }));

        try {
            const formData = new FormData();

            // Aggiungi file
            this.state.files.forEach((fileObj, index) => {
                formData.append(`files[${index}]`, fileObj.file);
            });

            // Aggiungi metadati
            const metadataToUpload = {
                ...this.metadata,
                site_id: this.config.siteId,
                upload_timestamp: new Date().toISOString(),
                file_count: this.state.files.length
            };

            formData.append('metadata', JSON.stringify(metadataToUpload));

            // Crea XMLHttpRequest per progress tracking
            const xhr = new XMLHttpRequest();
            this.state.currentRequest = xhr;

            // Configura eventi XHR
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    this.state.uploadProgress = Math.round(percentComplete);
                    
                    // Aggiorna dettagli individuali (stima)
                    this.state.uploadDetails.forEach(detail => {
                        if (detail.status === 'pending') {
                            detail.progress = Math.min(this.state.uploadProgress, 99);
                        }
                    });

                    // Trigger callback progress
                    if (this.config.onProgress) {
                        this.config.onProgress(this.state.uploadProgress);
                    }

                    this.emit('upload:progress', { 
                        progress: this.state.uploadProgress,
                        loaded: e.loaded,
                        total: e.total
                    });
                }
            });

            xhr.addEventListener('load', () => {
                this.state.currentRequest = null;
                this.handleUploadResponse(xhr);
            });

            xhr.addEventListener('error', () => {
                this.state.currentRequest = null;
                this.handleUploadError(new Error('Network error during upload'));
            });

            xhr.addEventListener('abort', () => {
                this.state.currentRequest = null;
                this.handleUploadError(new Error('Upload cancelled'));
            });

            // Invia richiesta
            xhr.open('POST', this.config.uploadUrl);
            xhr.setRequestHeader('Authorization', `Bearer ${localStorage.getItem('access_token')}`);
            xhr.send(formData);

            this.emit('upload:started', { 
                fileCount: this.state.files.length,
                totalSize: this.state.files.reduce((sum, f) => sum + f.size, 0)
            });

        } catch (error) {
            console.error('Upload preparation error:', error);
            this.handleUploadError(error);
        }
    }

    /**
     * Gestisce la risposta dell'upload
     * @param {XMLHttpRequest} xhr - Oggetto XMLHttpRequest
     */
    handleUploadResponse(xhr) {
        try {
            if (xhr.status === 200 || xhr.status === 201) {
                const result = JSON.parse(xhr.responseText);
                this.handleUploadSuccess(result);
            } else {
                const errorText = xhr.responseText || 'Unknown error';
                throw new Error(`Upload failed: ${xhr.status} ${xhr.statusText} - ${errorText}`);
            }
        } catch (error) {
            this.handleUploadError(error);
        }
    }

    /**
     * Gestisce successo dell'upload
     * @param {Object} result - Risultato dell'upload
     */
    handleUploadSuccess(result) {
        // Aggiorna stato finale
        this.state.uploadProgress = 100;
        this.state.uploadDetails.forEach(detail => {
            detail.status = 'completed';
            detail.progress = 100;
        });

        this.state.isUploading = false;

        // Notifica successo
        const message = `Upload completato con successo! ${this.state.files.length} file caricati`;
        this.notify(message, 'success');

        // Trigger callback successo
        if (this.config.onSuccess) {
            this.config.onSuccess(result);
        }

        // Trigger evento custom
        this.emit('upload:completed', { 
            result,
            fileCount: this.state.files.length,
            uploadedFileIds: result.uploaded_file_ids || []
        });

        // Chiudi automaticamente se configurato
        if (this.config.autoClose) {
            setTimeout(() => {
                this.close();
            }, this.config.autoCloseDelay);
        }
    }

    /**
     * Gestisce errore durante l'upload
     * @param {Error} error - Errore ocorso
     */
    handleUploadError(error) {
        this.state.isUploading = false;

        // Aggiorna stato errore
        this.state.uploadDetails.forEach(detail => {
            if (detail.status === 'pending' || detail.status === 'uploading') {
                detail.status = 'error';
            }
        });

        // Notifica errore
        this.notify(`Errore durante l'upload: ${error.message}`, 'error');

        // Trigger callback errore
        if (this.config.onError) {
            this.config.onError(error);
        }

        // Trigger evento custom
        this.emit('upload:error', { error, files: this.state.files });
    }

    /**
     * Cancella l'upload corrente
     */
    cancelUpload() {
        if (this.state.currentRequest) {
            this.state.currentRequest.abort();
            this.notify('Upload annullato', 'info');
            this.emit('upload:cancelled');
        }
    }

    /**
     * Converte stringa dimensione in bytes
     * @param {string} sizeStr - Stringa dimensione (es: "50MB")
     * @returns {number} Dimensione in bytes
     */
    parseFileSize(sizeStr) {
        const units = { B: 1, KB: 1024, MB: 1024 * 1024, GB: 1024 * 1024 * 1024 };
        const match = sizeStr.match(/^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)$/i);
        if (!match) return 0;
        return parseFloat(match[1]) * (units[match[2].toUpperCase()] || 1);
    }

    /**
     * Formatta bytes in stringa leggibile
     * @param {number} bytes - Bytes da formattare
     * @returns {string} Stringa formattata
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Ottiene l'URL di upload di default
     * @returns {string} URL di upload
     */
    getDefaultUploadUrl() {
        const siteId = this.getCurrentSiteId();
        return `/api/v1/sites/${siteId}/photos/upload`;
    }

    /**
     * Ottiene l'ID del sito corrente
     * @returns {string|null} ID del sito
     */
    getCurrentSiteId() {
        // Try URL path
        const pathSegments = window.location.pathname.split('/');
        const sitesIndex = pathSegments.indexOf('view');
        if (sitesIndex !== -1 && pathSegments[sitesIndex + 1]) {
            return pathSegments[sitesIndex + 1];
        }

        // Fallback global variable
        if (window.currentSiteId) {
            return window.currentSiteId;
        }

        return null;
    }

    /**
     * Mostra una notifica
     * @param {string} message - Messaggio da mostrare
     * @param {string} type - Tipo di notifica (success, error, warning, info)
     */
    notify(message, type = 'info') {
        // Usa toast system se disponibile, altrimenti fallback
        if (window.toastSystem) {
            const toastMethod = type === 'error' ? 'showError' :
                               type === 'success' ? 'showSuccess' :
                               type === 'warning' ? 'showWarning' : 'showInfo';
            window.toastSystem[toastMethod](message);
        } else {
            this.showToast(message, type);
        }
    }

    /**
     * Implementazione toast fallback
     * @param {string} message - Messaggio
     * @param {string} type - Tipo
     */
    showToast(message, type) {
        const toast = document.createElement('div');
        const bgColors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };

        toast.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transition-all duration-300 transform translate-x-full ${bgColors[type] || bgColors.info} text-white`;
        toast.innerHTML = `
            <div class="flex items-center">
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;

        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.classList.remove('translate-x-full');
        }, 10);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('translate-x-full');
                setTimeout(() => {
                    if (toast.parentElement) {
                        toast.remove();
                    }
                }, 300);
            }
        }, 5000);
    }

    /**
     * Emette un evento custom
     * @param {string} eventName - Nome evento
     * @param {Object} data - Dati evento
     */
    emit(eventName, data = {}) {
        const event = new CustomEvent(eventName, { detail: data });
        document.dispatchEvent(event);
    }

    /**
     * Aggiorna l'interfaccia utente
     */
    updateUI() {
        // Qui si possono aggiungere aggiornamenti UI specifici
        // Se si usa Alpine.js, l'UI si aggiornerà automaticamente
        this.emit('ui:updated', { state: this.state });
    }

    /**
     * Imposta i metadati
     * @param {Object} metadata - Metadati da impostare
     */
    setMetadata(metadata) {
        this.metadata = { ...this.metadata, ...metadata };
        this.emit('metadata:updated', { metadata: this.metadata });
    }

    /**
     * Ottiene i metadati correnti
     * @returns {Object} Metadati correnti
     */
    getMetadata() {
        return { ...this.metadata };
    }

    /**
     * Ottiene lo stato corrente
     * @returns {Object} Stato corrente
     */
    getState() {
        return { ...this.state };
    }

    /**
     * Distrugge il componente
     */
    destroy() {
        // Cancella upload corrente
        if (this.state.currentRequest) {
            this.state.currentRequest.abort();
        }

        // Pulisci event listeners
        document.removeEventListener('keydown', this.handleKeyDown);

        // Chiudi modale
        if (this.state.isOpen) {
            this.close();
        }

        this.emit('upload:destroyed');
    }
}

// Esporta per uso come modulo ES6 e CommonJS
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PhotoUpload;
}

// Esporta globalmente per compatibilità
if (typeof window !== 'undefined') {
    window.PhotoUpload = PhotoUpload;
}

/**
 * Esempi di utilizzo:
 * 
 * // 1. Configurazione base
 * const uploader = new PhotoUpload({
 *     uploadUrl: '/api/v1/sites/site123/photos/upload',
 *     siteId: 'site123'
 * });
 * 
 * // 2. Configurazione avanzata
 * const uploader = new PhotoUpload({
 *     uploadUrl: '/api/v1/sites/site123/photos/upload',
 *     siteId: 'site123',
 *     allowedTypes: 'image/jpeg,image/png,image/tiff',
 *     maxFileSize: '100MB',
 *     maxFiles: 50,
 *     onSuccess: (result) => console.log('Upload completato:', result),
 *     onError: (error) => console.error('Upload fallito:', error),
 *     onProgress: (progress) => console.log('Progress:', progress + '%'),
 *     autoClose: false
 * });
 * 
 * // 3. Apri modale con metadati pre-compilati
 * uploader.open({
 *     excavation_area: 'Area A',
 *     material: 'ceramic',
 *     photo_type: 'general_view'
 * });
 * 
 * // 4. Eventi custom
 * document.addEventListener('upload:completed', (e) => {
 *     console.log('Upload completato:', e.detail);
 * });
 */