<!-- Photo Modal - Versione corretta con miglioramenti -->
<div class="modal fade" id="photoModal" tabindex="-1" aria-labelledby="photoModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-fullscreen">
        <div class="modal-content">
            <!-- Header migliorato -->
            <div class="modal-header bg-dark text-white">
                <h5 class="modal-title" id="photoModalLabel">
                    <i class="fas fa-image me-2"></i>
                    <span id="modal-photo-title">Foto Archeologica</span>
                </h5>
                
                <!-- Controlli header -->
                <div class="header-controls d-flex align-items-center gap-2">
                    <!-- Deep Zoom Status Indicator -->
                    <div id="deep-zoom-indicator" class="badge bg-secondary d-none">
                        <i class="fas fa-search-plus me-1"></i>
                        <span id="deep-zoom-status">Checking...</span>
                    </div>
                    
                    <!-- Navigation arrows -->
                    <button type="button" class="btn btn-sm btn-outline-light" id="prevPhotoBtn" title="Foto precedente">
                        <i class="fas fa-chevron-left"></i>
                    </button>
                    <span class="badge bg-secondary" id="photo-counter">1 / 1</span>
                    <button type="button" class="btn btn-sm btn-outline-light" id="nextPhotoBtn" title="Foto successiva">
                        <i class="fas fa-chevron-right"></i>
                    </button>
                    
                    <!-- Actions -->
                    <div class="dropdown">
                        <button class="btn btn-sm btn-outline-light dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            <i class="fas fa-cog"></i>
                        </button>
                        <ul class="dropdown-menu dropdown-menu-end">
                            <li><a class="dropdown-item" href="#" id="downloadPhotoBtn">
                                <i class="fas fa-download me-2"></i>Download
                            </a></li>
                            <li><a class="dropdown-item" href="#" id="sharePhotoBtn">
                                <i class="fas fa-share me-2"></i>Condividi
                            </a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item text-danger" href="#" id="deletePhotoBtn">
                                <i class="fas fa-trash me-2"></i>Elimina
                            </a></li>
                        </ul>
                    </div>
                    
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
            </div>

            <div class="modal-body p-0 d-flex h-100">
                <!-- Left Panel - Photo Display -->
                <div class="photo-display-panel flex-fill position-relative">
                    <!-- Loading state -->
                    <div id="photo-loading" class="position-absolute top-50 start-50 translate-middle d-none">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>
                    
                    <!-- Error state -->
                    <div id="photo-error" class="position-absolute top-50 start-50 translate-middle text-center d-none">
                        <i class="fas fa-exclamation-triangle fa-3x text-warning mb-3"></i>
                        <p class="text-muted">Errore nel caricamento dell'immagine</p>
                        <button class="btn btn-outline-primary btn-sm" onclick="retryPhotoLoad()">
                            <i class="fas fa-refresh me-2"></i>Riprova
                        </button>
                    </div>
                    
                    <!-- Photo container -->
                    <div id="photo-container" class="h-100 d-flex align-items-center justify-content-center bg-black">
                        <!-- Standard photo view -->
                        <img id="modal-photo-img" class="img-fluid" style="max-height: 100%; max-width: 100%; object-fit: contain;" />
                        
                        <!-- Deep Zoom container (hidden by default) -->
                        <div id="deep-zoom-container" class="w-100 h-100 d-none"></div>
                    </div>
                    
                    <!-- Deep Zoom Progress Overlay -->
                    <div id="deep-zoom-progress" class="position-absolute bottom-0 start-0 end-0 bg-dark bg-opacity-75 text-white p-3 d-none">
                        <div class="d-flex align-items-center justify-content-between mb-2">
                            <span class="fw-bold">
                                <i class="fas fa-cogs me-2"></i>
                                Processamento Deep Zoom
                            </span>
                            <button class="btn btn-sm btn-outline-light" onclick="hideDeepZoomProgress()">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                        
                        <div class="progress mb-2" style="height: 6px;">
                            <div id="deep-zoom-progress-bar" class="progress-bar bg-success" role="progressbar" style="width: 0%"></div>
                        </div>
                        
                        <div class="d-flex justify-content-between">
                            <small id="deep-zoom-step" class="text-muted">Inizializzazione...</small>
                            <small id="deep-zoom-percentage" class="text-light">0%</small>
                        </div>
                    </div>
                    
                    <!-- Photo controls overlay -->
                    <div class="position-absolute top-50 start-0 translate-middle-y ps-3">
                        <button type="button" class="btn btn-dark btn-sm opacity-75" id="prevPhotoBtn2" title="Foto precedente">
                            <i class="fas fa-chevron-left"></i>
                        </button>
                    </div>
                    <div class="position-absolute top-50 end-0 translate-middle-y pe-3">
                        <button type="button" class="btn btn-dark btn-sm opacity-75" id="nextPhotoBtn2" title="Foto successiva">
                            <i class="fas fa-chevron-right"></i>
                        </button>
                    </div>
                    
                    <!-- Deep Zoom controls -->
                    <div class="position-absolute bottom-0 end-0 m-3">
                        <div class="btn-group-vertical" role="group">
                            <button type="button" class="btn btn-dark btn-sm" id="toggle-deep-zoom" title="Attiva/Disattiva Deep Zoom" disabled>
                                <i class="fas fa-search-plus"></i>
                            </button>
                            <button type="button" class="btn btn-dark btn-sm d-none" id="zoom-in" title="Zoom In">
                                <i class="fas fa-plus"></i>
                            </button>
                            <button type="button" class="btn btn-dark btn-sm d-none" id="zoom-out" title="Zoom Out">
                                <i class="fas fa-minus"></i>
                            </button>
                            <button type="button" class="btn btn-dark btn-sm d-none" id="zoom-reset" title="Reset Zoom">
                                <i class="fas fa-expand-arrows-alt"></i>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Right Panel - Metadata -->
                <div class="metadata-panel bg-light" style="width: 400px; min-width: 350px;">
                    <!-- Tabs per organizzare i metadati -->
                    <ul class="nav nav-tabs sticky-top bg-white" id="metadata-tabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="general-tab" data-bs-toggle="tab" data-bs-target="#general-metadata" type="button" role="tab">
                                <i class="fas fa-info-circle me-1"></i>Generale
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="archaeological-tab" data-bs-toggle="tab" data-bs-target="#archaeological-metadata" type="button" role="tab">
                                <i class="fas fa-landmark me-1"></i>Archeologico
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="technical-tab" data-bs-toggle="tab" data-bs-target="#technical-metadata" type="button" role="tab">
                                <i class="fas fa-camera me-1"></i>Tecnico
                            </button>
                        </li>
                    </ul>

                    <div class="tab-content h-100">
                        <!-- General Metadata Tab -->
                        <div class="tab-pane fade show active" id="general-metadata" role="tabpanel">
                            <div class="p-3 h-100 overflow-auto">
                                <form id="photo-metadata-form">
                                    <!-- Titolo e descrizione -->
                                    <div class="mb-3">
                                        <label for="photo-title" class="form-label fw-bold">
                                            <i class="fas fa-tag me-2"></i>Titolo
                                        </label>
                                        <input type="text" class="form-control" id="photo-title" placeholder="Titolo della foto...">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="photo-description" class="form-label fw-bold">
                                            <i class="fas fa-align-left me-2"></i>Descrizione
                                        </label>
                                        <textarea class="form-control" id="photo-description" rows="3" placeholder="Descrizione dettagliata..."></textarea>
                                    </div>
                                    
                                    <!-- Tipo foto e fotografo -->
                                    <div class="row mb-3">
                                        <div class="col-6">
                                            <label for="photo-type" class="form-label fw-bold">Tipo Foto</label>
                                            <select class="form-select" id="photo-type">
                                                <option value="">Seleziona tipo</option>
                                                <option value="CONTEXT">Contesto</option>
                                                <option value="FIND">Reperto</option>
                                                <option value="DETAIL">Dettaglio</option>
                                                <option value="DOCUMENTATION">Documentazione</option>
                                                <option value="PANORAMIC">Panoramica</option>
                                                <option value="RESTORATION">Restauro</option>
                                                <option value="ANALYSIS">Analisi</option>
                                            </select>
                                        </div>
                                        <div class="col-6">
                                            <label for="photo-photographer" class="form-label fw-bold">Fotografo</label>
                                            <input type="text" class="form-control" id="photo-photographer" placeholder="Nome fotografo">
                                        </div>
                                    </div>
                                    
                                    <!-- Keywords -->
                                    <div class="mb-3">
                                        <label for="photo-keywords" class="form-label fw-bold">
                                            <i class="fas fa-tags me-2"></i>Keywords
                                        </label>
                                        <div id="keywords-container" class="mb-2">
                                            <!-- Keywords dinamiche -->
                                        </div>
                                        <div class="input-group">
                                            <input type="text" class="form-control" id="new-keyword" placeholder="Aggiungi keyword...">
                                            <button type="button" class="btn btn-outline-secondary" onclick="addKeyword()">
                                                <i class="fas fa-plus"></i>
                                            </button>
                                        </div>
                                    </div>
                                    
                                    <!-- Copyright e licenza -->
                                    <div class="row mb-3">
                                        <div class="col-6">
                                            <label for="photo-copyright" class="form-label fw-bold">Copyright</label>
                                            <input type="text" class="form-control" id="photo-copyright" placeholder="Detentore copyright">
                                        </div>
                                        <div class="col-6">
                                            <label for="photo-license" class="form-label fw-bold">Licenza</label>
                                            <select class="form-select" id="photo-license">
                                                <option value="">Seleziona licenza</option>
                                                <option value="CC0">CC0 - Pubblico Dominio</option>
                                                <option value="CC_BY">CC BY - Attribuzione</option>
                                                <option value="CC_BY_SA">CC BY-SA - Attribuzione-Condividi allo stesso modo</option>
                                                <option value="ALL_RIGHTS_RESERVED">Tutti i diritti riservati</option>
                                                <option value="INSTITUTIONAL">Uso istituzionale</option>
                                            </select>
                                        </div>
                                    </div>
                                </form>
                            </div>
                        </div>

                        <!-- Archaeological Metadata Tab -->
                        <div class="tab-pane fade" id="archaeological-metadata" role="tabpanel">
                            <div class="p-3 h-100 overflow-auto">
                                <!-- Inventario e catalogazione -->
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="inventory-number" class="form-label fw-bold">N. Inventario</label>
                                        <input type="text" class="form-control" id="inventory-number" placeholder="es. INV-2024-001">
                                    </div>
                                    <div class="col-6">
                                        <label for="old-inventory-number" class="form-label fw-bold">N. Inv. Precedente</label>
                                        <input type="text" class="form-control" id="old-inventory-number" placeholder="Numero precedente">
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="catalog-number" class="form-label fw-bold">N. Catalogo</label>
                                    <input type="text" class="form-control" id="catalog-number" placeholder="Numero di catalogo">
                                </div>
                                
                                <!-- Contesto di scavo -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-map-marked-alt me-2"></i>Contesto di Scavo
                                </h6>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="excavation-area" class="form-label">Area di Scavo</label>
                                        <input type="text" class="form-control" id="excavation-area" placeholder="es. Settore A">
                                    </div>
                                    <div class="col-6">
                                        <label for="stratigraphic-unit" class="form-label">US</label>
                                        <input type="text" class="form-control" id="stratigraphic-unit" placeholder="Unità Stratigrafica">
                                    </div>
                                </div>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="grid-square" class="form-label">Quadrato</label>
                                        <input type="text" class="form-control" id="grid-square" placeholder="es. Q12">
                                    </div>
                                    <div class="col-6">
                                        <label for="depth-level" class="form-label">Quota (cm)</label>
                                        <input type="number" class="form-control" id="depth-level" step="0.1" placeholder="0.0">
                                    </div>
                                </div>
                                
                                <!-- Dati di rinvenimento -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-calendar me-2"></i>Rinvenimento
                                </h6>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="find-date" class="form-label">Data Rinvenimento</label>
                                        <input type="date" class="form-control" id="find-date">
                                    </div>
                                    <div class="col-6">
                                        <label for="finder" class="form-label">Scavatore</label>
                                        <input type="text" class="form-control" id="finder" placeholder="Nome scavatore">
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="excavation-campaign" class="form-label">Campagna</label>
                                    <input type="text" class="form-control" id="excavation-campaign" placeholder="es. Campagna 2024">
                                </div>
                                
                                <!-- Classificazione oggetto -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-cube me-2"></i>Classificazione
                                </h6>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="material-type" class="form-label">Materiale</label>
                                        <select class="form-select" id="material-type">
                                            <option value="">Seleziona materiale</option>
                                            <option value="CERAMIC">Ceramica</option>
                                            <option value="METAL">Metallo</option>
                                            <option value="STONE">Pietra</option>
                                            <option value="GLASS">Vetro</option>
                                            <option value="BONE">Osso</option>
                                            <option value="WOOD">Legno</option>
                                            <option value="TEXTILE">Tessuto</option>
                                            <option value="COMPOSITE">Composito</option>
                                            <option value="OTHER">Altro</option>
                                        </select>
                                    </div>
                                    <div class="col-6">
                                        <label for="object-type" class="form-label">Tipo Oggetto</label>
                                        <input type="text" class="form-control" id="object-type" placeholder="es. Vaso, Fibula">
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="material-details" class="form-label">Dettagli Materiale</label>
                                    <textarea class="form-control" id="material-details" rows="2" placeholder="Descrizione dettagliata del materiale..."></textarea>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="object-function" class="form-label">Funzione</label>
                                    <input type="text" class="form-control" id="object-function" placeholder="es. Contenitore, Ornamento">
                                </div>
                            </div>
                        </div>

                        <!-- Technical Metadata Tab -->
                        <div class="tab-pane fade" id="technical-metadata" role="tabpanel">
                            <div class="p-3 h-100 overflow-auto">
                                <!-- Dimensioni -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-ruler me-2"></i>Dimensioni
                                </h6>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="length-cm" class="form-label">Lunghezza (cm)</label>
                                        <input type="number" class="form-control" id="length-cm" step="0.1" placeholder="0.0">
                                    </div>
                                    <div class="col-6">
                                        <label for="width-cm" class="form-label">Larghezza (cm)</label>
                                        <input type="number" class="form-control" id="width-cm" step="0.1" placeholder="0.0">
                                    </div>
                                </div>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="height-cm" class="form-label">Altezza (cm)</label>
                                        <input type="number" class="form-control" id="height-cm" step="0.1" placeholder="0.0">
                                    </div>
                                    <div class="col-6">
                                        <label for="diameter-cm" class="form-label">Diametro (cm)</label>
                                        <input type="number" class="form-control" id="diameter-cm" step="0.1" placeholder="0.0">
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="weight-grams" class="form-label">Peso (g)</label>
                                    <input type="number" class="form-control" id="weight-grams" step="0.01" placeholder="0.00">
                                </div>
                                
                                <!-- Cronologia -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-history me-2"></i>Cronologia
                                </h6>
                                
                                <div class="mb-3">
                                    <label for="chronology-period" class="form-label">Periodo</label>
                                    <input type="text" class="form-control" id="chronology-period" placeholder="es. Età del Ferro, Romano">
                                </div>
                                
                                <div class="mb-3">
                                    <label for="chronology-culture" class="form-label">Cultura</label>
                                    <input type="text" class="form-control" id="chronology-culture" placeholder="es. Etrusca, Villanoviana">
                                </div>
                                
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label for="dating-from" class="form-label">Datazione da (a.C./d.C.)</label>
                                        <input type="text" class="form-control" id="dating-from" placeholder="es. -500">
                                    </div>
                                    <div class="col-6">
                                        <label for="dating-to" class="form-label">Datazione a (a.C./d.C.)</label>
                                        <input type="text" class="form-control" id="dating-to" placeholder="es. -400">
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="dating-notes" class="form-label">Note Cronologiche</label>
                                    <textarea class="form-control" id="dating-notes" rows="2" placeholder="Note sulla datazione..."></textarea>
                                </div>
                                
                                <!-- Conservazione -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-shield-alt me-2"></i>Conservazione
                                </h6>
                                
                                <div class="mb-3">
                                    <label for="conservation-status" class="form-label">Stato di Conservazione</label>
                                    <select class="form-select" id="conservation-status">
                                        <option value="">Seleziona stato</option>
                                        <option value="EXCELLENT">Ottimo</option>
                                        <option value="GOOD">Buono</option>
                                        <option value="FAIR">Discreto</option>
                                        <option value="POOR">Scarso</option>
                                        <option value="FRAGMENTARY">Frammentario</option>
                                        <option value="RESTORED">Restaurato</option>
                                    </select>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="conservation-notes" class="form-label">Note Conservazione</label>
                                    <textarea class="form-control" id="conservation-notes" rows="2" placeholder="Note sullo stato di conservazione..."></textarea>
                                </div>
                                
                                <!-- Dati tecnici foto -->
                                <h6 class="fw-bold border-bottom pb-2 mb-3">
                                    <i class="fas fa-camera me-2"></i>Dati Tecnici Foto
                                </h6>
                                
                                <div id="technical-photo-data" class="small text-muted">
                                    <!-- Popolato dinamicamente con EXIF -->
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Footer con pulsanti azione -->
                    <div class="sticky-bottom bg-white border-top p-3">
                        <div class="d-flex gap-2">
                            <button type="button" class="btn btn-primary flex-fill" onclick="savePhotoMetadata()">
                                <i class="fas fa-save me-2"></i>Salva Modifiche
                            </button>
                            <button type="button" class="btn btn-outline-secondary" onclick="resetPhotoMetadata()">
                                <i class="fas fa-undo me-2"></i>Ripristina
                            </button>
                        </div>
                        
                        <!-- Save status -->
                        <div id="save-status" class="text-center mt-2 small d-none">
                            <span class="text-success">
                                <i class="fas fa-check-circle me-1"></i>
                                Salvato con successo
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- JavaScript per il modal -->
<script>
class PhotoModal {
    constructor() {
        this.currentPhotoIndex = 0;
        this.photos = [];
        this.deepZoomViewer = null;
        this.deepZoomActive = false;
        this.deepZoomTaskTracker = new Map();
        this.originalMetadata = {};
        this.keywords = [];
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        // Navigation buttons
        document.getElementById('prevPhotoBtn')?.addEventListener('click', () => this.previousPhoto());
        document.getElementById('nextPhotoBtn')?.addEventListener('click', () => this.nextPhoto());
        document.getElementById('prevPhotoBtn2')?.addEventListener('click', () => this.previousPhoto());
        document.getElementById('nextPhotoBtn2')?.addEventListener('click', () => this.nextPhoto());
        
        // Deep zoom toggle
        document.getElementById('toggle-deep-zoom')?.addEventListener('click', () => this.toggleDeepZoom());
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (document.getElementById('photoModal').classList.contains('show')) {
                switch(e.key) {
                    case 'ArrowLeft':
                        e.preventDefault();
                        this.previousPhoto();
                        break;
                    case 'ArrowRight':
                        e.preventDefault();
                        this.nextPhoto();
                        break;
                    case 'Escape':
                        e.preventDefault();
                        bootstrap.Modal.getInstance(document.getElementById('photoModal')).hide();
                        break;
                    case 's':
                        if (e.ctrlKey) {
                            e.preventDefault();
                            this.savePhotoMetadata();
                        }
                        break;
                }
            }
        });
        
        // Modal events
        document.getElementById('photoModal').addEventListener('hidden.bs.modal', () => {
            this.cleanup();
        });
        
        // Form auto-save (debounced)
        this.setupAutoSave();
        
        // Download handler
        document.getElementById('downloadPhotoBtn')?.addEventListener('click', () => this.downloadPhoto());
        
        // Delete handler
        document.getElementById('deletePhotoBtn')?.addEventListener('click', () => this.deletePhoto());
    }
    
    setupAutoSave() {
        let autoSaveTimeout;
        const formElements = document.querySelectorAll('#photo-metadata-form input, #photo-metadata-form textarea, #photo-metadata-form select');
        
        formElements.forEach(element => {
            element.addEventListener('input', () => {
                clearTimeout(autoSaveTimeout);
                autoSaveTimeout = setTimeout(() => {
                    this.autoSaveMetadata();
                }, 2000); // Auto-save dopo 2 secondi di inattività
            });
        });
    }
    
    async openModal(photos, startIndex = 0) {
        try {
            this.photos = Array.isArray(photos) ? photos : [photos];
            this.currentPhotoIndex = Math.max(0, Math.min(startIndex, this.photos.length - 1));
            
            // Mostra modal
            const modal = new bootstrap.Modal(document.getElementById('photoModal'));
            modal.show();
            
            // Carica foto corrente
            await this.loadPhoto(this.currentPhotoIndex);
            
        } catch (error) {
            console.error('Error opening photo modal:', error);
            this.showError('Errore nell\'apertura del modal');
        }
    }
    
    async loadPhoto(index) {
        if (index < 0 || index >= this.photos.length) return;
        
        try {
            // Show loading
            this.showLoading(true);
            this.hideError();
            
            const photo = this.photos[index];
            this.currentPhotoIndex = index;
            
            // Update header
            document.getElementById('modal-photo-title').textContent = photo.title || photo.filename || 'Foto Archeologica';
            document.getElementById('photo-counter').textContent = `${index + 1} / ${this.photos.length}`;
            
            // Update navigation buttons state
            document.getElementById('prevPhotoBtn').disabled = index === 0;
            document.getElementById('nextPhotoBtn').disabled = index === this.photos.length - 1;
            document.getElementById('prevPhotoBtn2').disabled = index === 0;
            document.getElementById('nextPhotoBtn2').disabled = index === this.photos.length - 1;
            
            // Load photo image
            await this.loadPhotoImage(photo);
            
            // Load metadata
            await this.loadPhotoMetadata(photo);
            
            // Check deep zoom status
            await this.checkDeepZoomStatus(photo);
            
            this.showLoading(false);
            
        } catch (error) {
            console.error('Error loading photo:', error);
            this.showError('Errore nel caricamento della foto');
            this.showLoading(false);
        }
    }
    
    async loadPhotoImage(photo) {
        return new Promise((resolve, reject) => {
            const img = document.getElementById('modal-photo-img');
            
            img.onload = () => {
                // Reset deep zoom
                this.resetDeepZoom();
                resolve();
            };
            
            img.onerror = () => {
                reject(new Error('Failed to load image'));
            };
            
            // Set image source
            if (photo.file_url) {
                img.src = photo.file_url;
            } else if (photo.photo_id) {
                img.src = `/sites/${siteId}/photos/${photo.photo_id}/stream`;
            } else {
                reject(new Error('No image URL available'));
            }
        });
    }
    
    async loadPhotoMetadata(photo) {
        try {
            // Store original metadata for reset functionality
            this.originalMetadata = { ...photo };
            
            // General tab
            document.getElementById('photo-title').value = photo.title || '';
            document.getElementById('photo-description').value = photo.description || '';
            document.getElementById('photo-type').value = photo.photo_type || '';
            document.getElementById('photo-photographer').value = photo.photographer || '';
            document.getElementById('photo-copyright').value = photo.copyright_holder || '';
            document.getElementById('photo-license').value = photo.license_type || '';
            
            // Load keywords
            this.loadKeywords(photo.keywords);
            
            // Archaeological tab
            document.getElementById('inventory-number').value = photo.inventory_number || '';
            document.getElementById('old-inventory-number').value = photo.old_inventory_number || '';
            document.getElementById('catalog-number').value = photo.catalog_number || '';
            document.getElementById('excavation-area').value = photo.excavation_area || '';
            document.getElementById('stratigraphic-unit').value = photo.stratigraphic_unit || '';
            document.getElementById('grid-square').value = photo.grid_square || '';
            document.getElementById('depth-level').value = photo.depth_level || '';
            document.getElementById('find-date').value = photo.find_date ? photo.find_date.split('T')[0] : '';
            document.getElementById('finder').value = photo.finder || '';
            document.getElementById('excavation-campaign').value = photo.excavation_campaign || '';
            document.getElementById('material-type').value = photo.material || '';
            document.getElementById('material-details').value = photo.material_details || '';
            document.getElementById('object-type').value = photo.object_type || '';
            document.getElementById('object-function').value = photo.object_function || '';
            
            // Technical tab
            document.getElementById('length-cm').value = photo.length_cm || '';
            document.getElementById('width-cm').value = photo.width_cm || '';
            document.getElementById('height-cm').value = photo.height_cm || '';
            document.getElementById('diameter-cm').value = photo.diameter_cm || '';
            document.getElementById('weight-grams').value = photo.weight_grams || '';
            document.getElementById('chronology-period').value = photo.chronology_period || '';
            document.getElementById('chronology-culture').value = photo.chronology_culture || '';
            document.getElementById('dating-from').value = photo.dating_from || '';
            document.getElementById('dating-to').value = photo.dating_to || '';
            document.getElementById('dating-notes').value = photo.dating_notes || '';
            document.getElementById('conservation-status').value = photo.conservation_status || '';
            document.getElementById('conservation-notes').value = photo.conservation_notes || '';
            
            // Load technical photo data
            this.loadTechnicalPhotoData(photo);
            
        } catch (error) {
            console.error('Error loading metadata:', error);
        }
    }
    
    loadKeywords(keywords) {
        this.keywords = [];
        const container = document.getElementById('keywords-container');
        container.innerHTML = '';
        
        if (keywords) {
            const keywordList = Array.isArray(keywords) ? keywords : 
                              typeof keywords === 'string' ? JSON.parse(keywords) : [];
            
            keywordList.forEach(keyword => {
                this.addKeywordToUI(keyword);
            });
        }
    }
    
    addKeywordToUI(keyword) {
        if (this.keywords.includes(keyword)) return;
        
        this.keywords.push(keyword);
        const container = document.getElementById('keywords-container');
        
        const badge = document.createElement('span');
        badge.className = 'badge bg-secondary me-1 mb-1';
        badge.innerHTML = `
            ${keyword}
            <button type="button" class="btn-close btn-close-white ms-1" style="font-size: 0.6em;" 
                    onclick="photoModal.removeKeyword('${keyword}')"></button>
        `;
        
        container.appendChild(badge);
    }
    
    removeKeyword(keyword) {
        this.keywords = this.keywords.filter(k => k !== keyword);
        this.loadKeywords(this.keywords);
    }
    
    loadTechnicalPhotoData(photo) {
        const container = document.getElementById('technical-photo-data');
        
        const technicalData = [
            { label: 'Dimensioni', value: `${photo.width || '?'} × ${photo.height || '?'} px` },
            { label: 'Dimensione File', value: this.formatFileSize(photo.file_size) },
            { label: 'Formato', value: photo.filename ? photo.filename.split('.').pop().toUpperCase() : 'N/A' },
            { label: 'Data Scatto', value: photo.photo_date ? new Date(photo.photo_date).toLocaleString('it-IT') : 'N/A' },
            { label: 'Fotocamera', value: photo.camera_model || 'N/A' },
            { label: 'Obiettivo', value: photo.lens_model || 'N/A' },
            { label: 'ISO', value: photo.iso || 'N/A' },
            { label: 'Apertura', value: photo.f_number ? `f/${photo.f_number}` : 'N/A' },
            { label: 'Tempo Esposizione', value: photo.exposure_time || 'N/A' },
            { label: 'Focale', value: photo.focal_length ? `${photo.focal_length}mm` : 'N/A' },
            { label: 'GPS', value: photo.gps_latitude && photo.gps_longitude ? 
                `${photo.gps_latitude.toFixed(6)}, ${photo.gps_longitude.toFixed(6)}` : 'N/A' },
        ];
        
        container.innerHTML = technicalData.map(item => `
            <div class="row mb-1">
                <div class="col-5 fw-bold">${item.label}:</div>
                <div class="col-7">${item.value}</div>
            </div>
        `).join('');
    }
    
    async checkDeepZoomStatus(photo) {
        try {
            const indicator = document.getElementById('deep-zoom-indicator');
            const toggleBtn = document.getElementById('toggle-deep-zoom');
            
            // Check if photo has deep zoom or if there's an active task
            if (photo.has_deep_zoom) {
                indicator.classList.remove('d-none', 'bg-secondary', 'bg-warning');
                indicator.classList.add('bg-success');
                document.getElementById('deep-zoom-status').textContent = 'Deep Zoom Disponibile';
                toggleBtn.disabled = false;
            } else {
                // Check for active deep zoom task
                const response = await fetch(`/sites/${siteId}/api/photos/${photo.photo_id}/deep-zoom-status`);
                if (response.ok) {
                    const status = await response.json();
                    
                    if (status.active_background_task) {
                        // Show progress for active task
                        this.trackDeepZoomProgress(photo.photo_id, status.active_background_task.task_id);
                    } else {
                        indicator.classList.add('d-none');
                        toggleBtn.disabled = true;
                    }
                } else {
                    indicator.classList.add('d-none');
                    toggleBtn.disabled = true;
                }
            }
        } catch (error) {
            console.error('Error checking deep zoom status:', error);
            document.getElementById('deep-zoom-indicator').classList.add('d-none');
            document.getElementById('toggle-deep-zoom').disabled = true;
        }
    }
    
    trackDeepZoomProgress(photoId, taskId) {
        if (this.deepZoomTaskTracker.has(taskId)) return;
        
        const indicator = document.getElementById('deep-zoom-indicator');
        const progressOverlay = document.getElementById('deep-zoom-progress');
        
        // Show progress indicator
        indicator.classList.remove('d-none', 'bg-secondary', 'bg-success');
        indicator.classList.add('bg-warning');
        document.getElementById('deep-zoom-status').textContent = 'Processing...';
        
        // Show progress overlay
        progressOverlay.classList.remove('d-none');
        
        const intervalId = setInterval(async () => {
            try {
                const response = await fetch(`/sites/${siteId}/api/background-tasks/${taskId}/progress`);
                
                if (response.ok) {
                    const progress = await response.json();
                    
                    // Update progress UI
                    document.getElementById('deep-zoom-progress-bar').style.width = `${progress.progress_percentage}%`;
                    document.getElementById('deep-zoom-percentage').textContent = `${progress.progress_percentage}%`;
                    document.getElementById('deep-zoom-step').textContent = progress.current_step || 'Processing...';
                    
                    if (progress.status === 'completed') {
                        // Task completed successfully
                        clearInterval(intervalId);
                        this.deepZoomTaskTracker.delete(taskId);
                        
                        // Update UI to show deep zoom available
                        indicator.classList.remove('bg-warning');
                        indicator.classList.add('bg-success');
                        document.getElementById('deep-zoom-status').textContent = 'Deep Zoom Disponibile';
                        document.getElementById('toggle-deep-zoom').disabled = false;
                        
                        // Hide progress overlay after a delay
                        setTimeout(() => {
                            progressOverlay.classList.add('d-none');
                        }, 3000);
                        
                        // Update photo object
                        const currentPhoto = this.photos[this.currentPhotoIndex];
                        if (currentPhoto.photo_id === photoId) {
                            currentPhoto.has_deep_zoom = true;
                        }
                        
                    } else if (progress.status === 'failed') {
                        // Task failed
                        clearInterval(intervalId);
                        this.deepZoomTaskTracker.delete(taskId);
                        
                        indicator.classList.remove('bg-warning');
                        indicator.classList.add('bg-danger');
                        document.getElementById('deep-zoom-status').textContent = 'Processing Failed';
                        
                        setTimeout(() => {
                            indicator.classList.add('d-none');
                            progressOverlay.classList.add('d-none');
                        }, 5000);
                    }
                } else {
                    // Error fetching progress
                    clearInterval(intervalId);
                    this.deepZoomTaskTracker.delete(taskId);
                }
            } catch (error) {
                console.error('Error tracking deep zoom progress:', error);
                clearInterval(intervalId);
                this.deepZoomTaskTracker.delete(taskId);
            }
        }, 2000);
        
        this.deepZoomTaskTracker.set(taskId, intervalId);
    }
    
    hideDeepZoomProgress() {
        document.getElementById('deep-zoom-progress').classList.add('d-none');
    }
    
    async toggleDeepZoom() {
        const photo = this.photos[this.currentPhotoIndex];
        
        if (this.deepZoomActive) {
            // Disable deep zoom
            this.resetDeepZoom();
        } else {
            // Enable deep zoom
            if (photo.has_deep_zoom) {
                await this.initializeDeepZoom(photo);
            } else {
                // Try to start deep zoom processing
                await this.startDeepZoomProcessing(photo);
            }
        }
    }
    
    async initializeDeepZoom(photo) {
        try {
            // Hide standard image
            document.getElementById('modal-photo-img').classList.add('d-none');
            
            // Show deep zoom container
            const container = document.getElementById('deep-zoom-container');
            container.classList.remove('d-none');
            container.innerHTML = ''; // Clear previous viewer
            
            // Initialize OpenSeadragon (assumendo che sia incluso)
            if (typeof OpenSeadragon !== 'undefined') {
                this.deepZoomViewer = OpenSeadragon({
                    element: container,
                    prefixUrl: '/static/images/openseadragon/',
                    tileSources: `/sites/${siteId}/photos/${photo.photo_id}/deepzoom/info`,
                    showNavigationControl: true,
                    showZoomControl: true,
                    showHomeControl: true,
                    showFullPageControl: false,
                    gestureSettingsMouse: {
                        clickToZoom: false,
                        dblClickToZoom: true,
                        scrollToZoom: true,
                        pinchToZoom: true
                    }
                });
                
                this.deepZoomActive = true;
                
                // Show zoom controls
                document.querySelectorAll('#zoom-in, #zoom-out, #zoom-reset').forEach(btn => {
                    btn.classList.remove('d-none');
                });
                
                // Setup zoom controls
                document.getElementById('zoom-in').onclick = () => this.deepZoomViewer.viewport.zoomBy(1.2);
                document.getElementById('zoom-out').onclick = () => this.deepZoomViewer.viewport.zoomBy(0.8);
                document.getElementById('zoom-reset').onclick = () => this.deepZoomViewer.viewport.goHome();
                
            } else {
                throw new Error('OpenSeadragon not loaded');
            }
            
        } catch (error) {
            console.error('Error initializing deep zoom:', error);
            this.showError('Errore nell\'inizializzazione del Deep Zoom');
            this.resetDeepZoom();
        }
    }
    
    async startDeepZoomProcessing(photo) {
        try {
            const response = await fetch(`/sites/${siteId}/photos/${photo.photo_id}/deepzoom/process`, {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                // Progress tracking will be handled automatically by checkDeepZoomStatus
                this.showSuccess('Deep Zoom processing avviato in background');
            } else {
                throw new Error('Failed to start deep zoom processing');
            }
        } catch (error) {
            console.error('Error starting deep zoom processing:', error);
            this.showError('Errore nell\'avvio del processamento Deep Zoom');
        }
    }
    
    resetDeepZoom() {
        // Hide deep zoom container
        document.getElementById('deep-zoom-container').classList.add('d-none');
        
        // Show standard image
        document.getElementById('modal-photo-img').classList.remove('d-none');
        
        // Hide zoom controls
        document.querySelectorAll('#zoom-in, #zoom-out, #zoom-reset').forEach(btn => {
            btn.classList.add('d-none');
        });
        
        // Destroy viewer
        if (this.deepZoomViewer) {
            this.deepZoomViewer.destroy();
            this.deepZoomViewer = null;
        }
        
        this.deepZoomActive = false;
    }
    
    previousPhoto() {
        if (this.currentPhotoIndex > 0) {
            this.loadPhoto(this.currentPhotoIndex - 1);
        }
    }
    
    nextPhoto() {
        if (this.currentPhotoIndex < this.photos.length - 1) {
            this.loadPhoto(this.currentPhotoIndex + 1);
        }
    }
    
    async savePhotoMetadata() {
        try {
            const photo = this.photos[this.currentPhotoIndex];
            const formData = this.getFormData();
            
            const response = await fetch(`/sites/${siteId}/photos/${photo.photo_id}/update`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showSaveSuccess();
                
                // Update local photo data
                Object.assign(this.photos[this.currentPhotoIndex], formData);
                this.originalMetadata = { ...this.photos[this.currentPhotoIndex] };
                
            } else {
                throw new Error(`Server error: ${response.status}`);
            }
            
        } catch (error) {
            console.error('Error saving metadata:', error);
            this.showSaveError();
        }
    }
    
    async autoSaveMetadata() {
        // Silent auto-save without user feedback
        try {
            const photo = this.photos[this.currentPhotoIndex];
            const formData = this.getFormData();
            
            const response = await fetch(`/sites/${siteId}/photos/${photo.photo_id}/update`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            if (response.ok) {
                // Update local data silently
                Object.assign(this.photos[this.currentPhotoIndex], formData);
            }
            
        } catch (error) {
            console.error('Auto-save failed:', error);
        }
    }
    
    getFormData() {
        return {
            // General
            title: document.getElementById('photo-title').value,
            description: document.getElementById('photo-description').value,
            photo_type: document.getElementById('photo-type').value,
            photographer: document.getElementById('photo-photographer').value,
            keywords: this.keywords,
            copyright_holder: document.getElementById('photo-copyright').value,
            license_type: document.getElementById('photo-license').value,
            
            // Archaeological
            inventory_number: document.getElementById('inventory-number').value,
            old_inventory_number: document.getElementById('old-inventory-number').value,
            catalog_number: document.getElementById('catalog-number').value,
            excavation_area: document.getElementById('excavation-area').value,
            stratigraphic_unit: document.getElementById('stratigraphic-unit').value,
            grid_square: document.getElementById('grid-square').value,
            depth_level: document.getElementById('depth-level').value || null,
            find_date: document.getElementById('find-date').value || null,
            finder: document.getElementById('finder').value,
            excavation_campaign: document.getElementById('excavation-campaign').value,
            material: document.getElementById('material-type').value,
            material_details: document.getElementById('material-details').value,
            object_type: document.getElementById('object-type').value,
            object_function: document.getElementById('object-function').value,
            
            // Technical
            length_cm: document.getElementById('length-cm').value || null,
            width_cm: document.getElementById('width-cm').value || null,
            height_cm: document.getElementById('height-cm').value || null,
            diameter_cm: document.getElementById('diameter-cm').value || null,
            weight_grams: document.getElementById('weight-grams').value || null,
            chronology_period: document.getElementById('chronology-period').value,
            chronology_culture: document.getElementById('chronology-culture').value,
            dating_from: document.getElementById('dating-from').value,
            dating_to: document.getElementById('dating-to').value,
            dating_notes: document.getElementById('dating-notes').value,
            conservation_status: document.getElementById('conservation-status').value,
            conservation_notes: document.getElementById('conservation-notes').value
        };
    }
    
    resetPhotoMetadata() {
        this.loadPhotoMetadata(this.originalMetadata);
    }
    
    async downloadPhoto() {
        const photo = this.photos[this.currentPhotoIndex];
        
        try {
            // Create download link
            const link = document.createElement('a');
            link.href = photo.file_url || `/sites/${siteId}/photos/${photo.photo_id}/stream`;
            link.download = photo.filename || `photo_${photo.photo_id}.jpg`;
            
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
        } catch (error) {
            console.error('Error downloading photo:', error);
            this.showError('Errore nel download della foto');
        }
    }
    
    async deletePhoto() {
        const photo = this.photos[this.currentPhotoIndex];
        
        if (!confirm(`Sei sicuro di voler eliminare la foto "${photo.filename || photo.title}"?`)) {
            return;
        }
        
        try {
            const response = await fetch(`/sites/${siteId}/photos/${photo.photo_id}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                // Remove from photos array
                this.photos.splice(this.currentPhotoIndex, 1);
                
                if (this.photos.length === 0) {
                    // No more photos, close modal
                    bootstrap.Modal.getInstance(document.getElementById('photoModal')).hide();
                } else {
                    // Load next photo or previous if at end
                    if (this.currentPhotoIndex >= this.photos.length) {
                        this.currentPhotoIndex = this.photos.length - 1;
                    }
                    await this.loadPhoto(this.currentPhotoIndex);
                }
                
                this.showSuccess('Foto eliminata con successo');
                
                // Trigger refresh of photo grid if available
                if (typeof refreshPhotoGrid === 'function') {
                    refreshPhotoGrid();
                }
                
            } else {
                throw new Error(`Server error: ${response.status}`);
            }
            
        } catch (error) {
            console.error('Error deleting photo:', error);
            this.showError('Errore nell\'eliminazione della foto');
        }
    }
    
    cleanup() {
        // Clear deep zoom progress trackers
        this.deepZoomTaskTracker.forEach((intervalId, taskId) => {
            clearInterval(intervalId);
        });
        this.deepZoomTaskTracker.clear();
        
        // Reset deep zoom
        this.resetDeepZoom();
        
        // Clear data
        this.photos = [];
        this.currentPhotoIndex = 0;
        this.originalMetadata = {};
        this.keywords = [];
    }
    
    showLoading(show) {
        const loading = document.getElementById('photo-loading');
        if (show) {
            loading.classList.remove('d-none');
        } else {
            loading.classList.add('d-none');
        }
    }
    
    hideError() {
        document.getElementById('photo-error').classList.add('d-none');
    }
    
    showError(message) {
        const errorDiv = document.getElementById('photo-error');
        errorDiv.querySelector('p').textContent = message;
        errorDiv.classList.remove('d-none');
    }
    
    showSuccess(message) {
        // Create toast or use existing notification system
        if (typeof showNotification === 'function') {
            showNotification(message, 'success');
        } else {
            alert(message);
        }
    }
    
    showSaveSuccess() {
        const status = document.getElementById('save-status');
        status.classList.remove('d-none');
        setTimeout(() => {
            status.classList.add('d-none');
        }, 3000);
    }
    
    showSaveError() {
        if (typeof showNotification === 'function') {
            showNotification('Errore nel salvataggio delle modifiche', 'error');
        } else {
            alert('Errore nel salvataggio delle modifiche');
        }
    }
    
    formatFileSize(bytes) {
        if (!bytes) return 'N/A';
        
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;
        
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        
        return `${size.toFixed(1)} ${units[unitIndex]}`;
    }
}

// Global functions for HTML onclick events
function addKeyword() {
    const input = document.getElementById('new-keyword');
    const keyword = input.value.trim();
    
    if (keyword && !photoModal.keywords.includes(keyword)) {
        photoModal.addKeywordToUI(keyword);
        input.value = '';
    }
}

function savePhotoMetadata() {
    photoModal.savePhotoMetadata();
}

function resetPhotoMetadata() {
    photoModal.resetPhotoMetadata();
}

function retryPhotoLoad() {
    const photo = photoModal.photos[photoModal.currentPhotoIndex];
    photoModal.loadPhoto(photoModal.currentPhotoIndex);
}

// Initialize global instance
const photoModal = new PhotoModal();

// Global function to open modal (used by photo grid)
function openPhotoModal(photos, startIndex = 0) {
    photoModal.openModal(photos, startIndex);
}
</script>

<!-- CSS Styles -->
<style>
.photo-display-panel {
    background: #000;
    min-height: 70vh;
}

.metadata-panel {
    max-height: 100vh;
    overflow-y: auto;
}

#deep-zoom-container {
    background: #000;
}

#deep-zoom-progress {
    backdrop-filter: blur(5px);
}

.deep-zoom-progress .progress {
    background-color: rgba(255, 255, 255, 0.2);
}

.header-controls .btn {
    border-color: rgba(255, 255, 255, 0.5);
}

.header-controls .btn:hover {
    background-color: rgba(255, 255, 255, 0.1);
}

#deep-zoom-indicator {
    transition: all 0.3s ease;
}

#deep-zoom-indicator.bg-warning {
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
}

.modal-fullscreen .modal-body {
    height: calc(100vh - 120px);
}

#photo-container img {
    transition: transform 0.3s ease;
}

.photo-display-panel .btn {
    backdrop-filter: blur(10px);
    background-color: rgba(0, 0, 0, 0.7);
}

.metadata-panel .nav-tabs {
    border-bottom: 1px solid #dee2e6;
}

.tab-content {
    height: calc(100% - 42px); /* Height minus tabs */
}

/* Keywords styling */
#keywords-container .badge {
    cursor: default;
}

#keywords-container .btn-close {
    cursor: pointer;
}

/* Form styling improvements */
.form-label.fw-bold {
    color: #495057;
}

.border-bottom {
    border-color: #dee2e6 !important;
}

/* Save status animation */
#save-status {
    transition: all 0.3s ease;
}

/* Responsive adjustments */
@media (max-width: 768px) {
    .metadata-panel {
        width: 100% !important;
        min-width: auto !important;
    }
    
    .modal-body {
        flex-direction: column;
    }
    
    .photo-display-panel {
        height: 50vh;
    }
}
</style>
