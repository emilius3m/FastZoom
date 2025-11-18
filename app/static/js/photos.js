
/**
 * photos.js - Modulo JavaScript principale per la gestione della collezione fotografica archeologica
 * Estratto dal file photos.html per modularizzare la logica
 * 
 * Questo modulo contiene la logica principale per:
 * - Gestione delle foto e filtri
 * Visualizzazione in modal con OpenSeadragon
 * Operazioni CRUD (create, read, update, delete)
 * Gestione WebSocket per notifiche real-time
 * Funzioni di utilità comuni
 * 
 * @author FastZoom Development Team
 * @version 1.0.0
 * @since 2025-11-18
 */

// Costanti globali
const PHOTOS_PER_PAGE = 24;
const MAX_FILE_SIZE_MB = 50;
const ALLOWED_FILE_TYPES = ['image/jpeg', 'image/png', 'image/tiff', 'image/webp'];

function photosManager() {
    return {
        // Data Properties
        photos: [],
        filteredPhotos: [],
        paginatedPhotos: [],
        currentPage: 1,
        itemsPerPage: PHOTOS_PER_PAGE,
        totalPhotos: 0,
        totalSize: 0,
        uniqueTags: 0,
        lastUpload: null,
        isLoading: false,
        viewMode: 'grid',
        selectedPhotos: [],
        userRole: '{{ user_role }}',
        
        // Multi-edit state
        get isMultipleSelection() {
            return this.selectedPhotos.length > 1;
        },

        // Modal States
        showPhotoModal: false,
        showUploadModal: false,
        showEditModal: false,
        showDeleteModal: false,
        showAlert: false,
        alertMessage: '',

        // Photo Modal Data
        currentPhoto: null,
        currentPhotoIndex: 0,
        photoViewMode: 'openseadragon', // OpenSeadragon only
        imageLoaded: false,
        imageError: false,
        showMobileInfo: false,
        showSidebar: false, // Desktop sidebar state

        // OpenSeadragon Modal State
        osdViewer: null,
        osdLoading: false,
        osdError: false,
        osdErrorMessage: '',

        // Ensure viewMode is properly initialized
        get currentViewMode() {
            return this.viewMode;
        },

        // Method to ensure grid view is displayed
        ensureGridView() {
            this.viewMode = 'grid';
            this.updatePagination();
        },

        // Edit Modal Data
        editingPhoto: null,
        isSaving: false,
        selectedPhoto: null,

        // Delete Modal Data
        photoToDelete: null,
        isDeleting: false,

        // Upload Data - gestito dal componente upload modulare
        selectedFiles: [],
        isUploading: false,
        uploadProgress: 0,

        // Bulk Delete Processing
        isBulkDeleting: false,

        // Enhanced Filters
        filters: {
            // Basic filters
            search: '',
            photo_type: '',
            material: '',
            
            // Archaeological context
            excavation_area: '',
            stratigraphic_unit: '',
            chronology_period: '',
            object_type: '',
            conservation_status: '',
            
            // Status filters
            is_published: null,
            is_validated: null,
            has_deep_zoom: null,
            has_inventory: null,
            has_description: null,
            has_photographer: null,
            
            // Date ranges
            upload_date_from: '',
            upload_date_to: '',
            photo_date_from: '',
            photo_date_to: '',
            find_date_from: '',
            find_date_to: '',
            
            // Dimension filters
            min_width: '',
            max_width: '',
            min_height: '',
            max_height: '',
            min_file_size_mb: '',
            max_file_size_mb: '',
            
            // Sorting
            sortBy: 'created_desc'
        },
        
        // UI state
        showAdvancedFilters: false,
        availableTags: [],

        // Computed Properties
        get totalPages() {
            return Math.ceil(this.filteredPhotos.length / this.itemsPerPage);
        },

        get startItem() {
            return (this.currentPage - 1) * this.itemsPerPage + 1;
        },

        get endItem() {
            return Math.min(this.currentPage * this.itemsPerPage, this.filteredPhotos.length);
        },

        get visiblePages() {
            const totalPages = this.totalPages;
            const current = this.currentPage;
            const delta = 2;
            const range = [];

            const start = Math.max(1, current - delta);
            const end = Math.min(totalPages, current + delta);

            for (let i = start; i <= end; i++) {
                range.push(i);
            }

            return range;
        },

        // Initialization
        async init() {
            this.isLoading = true;

            // Make this instance globally accessible
            window.photosManagerInstance = this;

            // Ensure viewMode is set to grid by default
            this.viewMode = 'grid';

            try {
                await this.loadPhotos();
                this.updateStatistics();
                this.extractAvailableTags();
                
                // Don't call applyFilters here since loadPhotos already sets the photos
                // and we want to show all photos initially
                this.filteredPhotos = this.photos;
                this.updatePagination();

                // Initialize deep zoom status checking
                await this.initializeDeepZoomStatus();

                // FIXED: Clean up any stuck processing photos
                this.cleanupStuckProcessingPhotos();

                // FIXED: Start cleanup timer to periodically check for stuck processing photos
                this.startCleanupTimer();

                // Ensure grid view is displayed by default
                this.ensureGridView();
                
                // Connect WebSocket for real-time notifications
                this.connectWebSocket();

                // Check for photo ID in URL
                const urlParams = new URLSearchParams(window.location.search);
                const photoId = urlParams.get('photo');
                if (photoId) {
                    const photoIndex = this.photos.findIndex(p => p.id == photoId);
                    if (photoIndex !== -1) {
                        this.openPhotoModal(photoIndex);
                    }
                }
            } catch (error) {
                console.error('Errore durante inizializzazione:', error);
                this.showAlertMessage(`Errore durante il caricamento delle foto: ${error.message || 'Errore sconosciuto'}. Riprova più tardi.`);
                
                // Ensure data consistency even on error
                try {
                    this.updateStatistics();
                    this.extractAvailableTags();
                    // Don't call applyFilters here either on error
                    this.filteredPhotos = this.photos || [];
                    this.updatePagination();
                } catch (updateError) {
                    console.error('Error updating photo data after init failure:', updateError);
                }
            } finally {
                this.isLoading = false;
            }
        },

        // Data Loading
        async loadPhotos() {
            // Create a timeout controller to prevent hanging requests
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            
            try {
                console.log('Loading photos from API...');
                
                const response = await fetch(`/api/v1/sites/{{ site.id }}/photos`, {
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    signal: controller.signal
                });

                // Clear the timeout since the request completed
                clearTimeout(timeoutId);

                // Handle specific authentication errors
                if (response.status === 401) {
                    console.error('Authentication error - please login again');
                    this.showAlertMessage('Errore di autenticazione. Effettua nuovamente il login.');
                    // Optionally redirect to login page
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                    throw new Error('Errore di autenticazione: sessione scaduta');
                }
                
                if (response.status === 403) {
                    console.error('Authorization error (403): Insufficient permissions');
                    this.showAlertMessage('Non hai i permessi per visualizzare queste foto.');
                    throw new Error('Errore di autorizzazione: permessi insufficienti');
                }

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('API Error:', response.status, errorText);
                    this.showAlertMessage(`Errore nel caricamento foto: ${response.status} ${response.statusText}`);
                    throw new Error(`Errore API ${response.status}: ${response.statusText}`);
                }

                // Check if response is JSON
                const contentType = response.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    console.error('Invalid response type:', contentType);
                    this.showAlertMessage('Il server ha restituito una risposta non valida.');
                    throw new Error('La risposta del server non è in formato JSON');
                }

                const data = await response.json();
                this.photos = Array.isArray(data) ? data.filter(photo => photo && photo.id) : [];
                console.log(`Successfully loaded ${this.photos.length} photos`);

            } catch (error) {
                // Clear the timeout if there's an error
                clearTimeout(timeoutId);
                
                // Handle timeout specifically
                if (error.name === 'AbortError') {
                    console.error('Request timeout: The server took too long to respond');
                    this.showAlertMessage('Timeout del server. Riprova più tardi.');
                } else {
                    console.error('Errore nel caricamento foto:', error);
                    this.showAlertMessage('Impossibile caricare le foto. Riprova più tardi.');
                }
                
                // Set empty array as fallback
                this.photos = [];
                throw error;
            } finally {
                // FIXED: Set isLoading to false here since loadPhotos is called directly from init()
                // and also from applyFilters() which manages its own loading state
                this.isLoading = false;
            }
        },

        // Statistics
        updateStatistics() {
            this.totalPhotos = this.photos.length;
            this.totalSize = this.photos.reduce((sum, photo) => sum + ((photo && photo.file_size) || 0), 0);
            
            // Fix for "Invalid Date" issue - ensure we only process valid dates
            const photosWithDates = this.photos.filter(p => p && p.upload_date);
            this.lastUpload = photosWithDates.length > 0 ?
                Math.max(...photosWithDates.map(p => new Date(p.upload_date).getTime())) : null;
        },

        extractAvailableTags() {
            const tagSet = new Set();
            this.photos.forEach(photo => {
                if (photo && photo.tags) {
                    photo.tags.forEach(tag => tagSet.add(tag));
                }
            });
            this.availableTags = Array.from(tagSet).sort();
            this.uniqueTags = this.availableTags.length;
        },

        // Advanced Filtering with Backend API
        async applyFilters() {
            this.isLoading = true;
            
            // Create a timeout controller to prevent hanging requests
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            
            try {
                console.log('Applying filters and fetching photos...');
                
                // Build query parameters from active filters
                const params = new URLSearchParams();
                
                // Basic filters
                if (this.filters.search?.trim()) params.append('search', this.filters.search.trim());
                if (this.filters.photo_type) params.append('photo_type', this.filters.photo_type);
                if (this.filters.material) params.append('material', this.filters.material);
                
                // Archaeological context
                if (this.filters.excavation_area?.trim()) params.append('excavation_area', this.filters.excavation_area.trim());
                if (this.filters.stratigraphic_unit?.trim()) params.append('stratigraphic_unit', this.filters.stratigraphic_unit.trim());
                if (this.filters.chronology_period?.trim()) params.append('chronology_period', this.filters.chronology_period.trim());
                if (this.filters.object_type?.trim()) params.append('object_type', this.filters.object_type.trim());
                if (this.filters.conservation_status) params.append('conservation_status', this.filters.conservation_status);
                
                // Status filters
                if (this.filters.is_published === true) params.append('is_published', 'true');
                if (this.filters.is_validated === true) params.append('is_validated', 'true');
                if (this.filters.has_deep_zoom === true) params.append('has_deep_zoom', 'true');
                if (this.filters.has_inventory === true) params.append('has_inventory', 'true');
                if (this.has_description === true) params.append('has_description', 'true');
                if (this.filters.has_photographer === true) params.append('has_photographer', 'true');
                
                // Date ranges
                if (this.filters.upload_date_from) params.append('upload_date_from', this.filters.upload_date_from);
                if (this.filters.upload_date_to) params.append('upload_date_to', this.filters.upload_date_to);
                if (this.filters.photo_date_from) params.append('photo_date_from', this.filters.photo_date_from);
                if (this.filters.photo_date_to) params.append('photo_date_to', this.filters.photo_date_to);
                if (this.filters.find_date_from) params.append('find_date_from', this.filters.find_date_from);
                if (this.filters.find_date_to) params.append('find_date_to', this.filters.find_date_to);
                
                // Dimension filters
                if (this.filters.min_width) params.append('min_width', this.filters.min_width);
                if (this.filters.max_width) params.append('max_width', this.filters.max_width);
                if (this.filters.min_height) params.append('min_height', this.filters.min_height);
                if (this.filters.max_height) params.append('max_height', this.filters.max_height);
                if (this.filters.min_file_size_mb) params.append('min_file_size_mb', this.filters.min_file_size_mb);
                if (this.filters.max_file_size_mb) params.append('max_file_size_mb', this.filters.max_file_size_mb);
                
                // Sorting
                if (this.filters.sortBy) params.append('sort_by', this.filters.sortBy);
                
                // Fetch filtered photos from API
                const queryString = params.toString();
                const url = `/api/v1/sites/{{ site.id }}/photos${queryString ? '?' + queryString : ''}`;
                
                const response = await fetch(url, {
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    signal: controller.signal
                });
                
                // Clear the timeout since the request completed
                clearTimeout(timeoutId);
                
                // Enhanced error handling for filters with toast system
                if (!response.ok) {
                    let errorMessage = `Errore nell'applicazione dei filtri: ${response.status} ${response.statusText}`;
                    let errorType = 'error';
                    
                    if (response.status === 401) {
                        errorMessage = 'Sessione scaduta. Effettua nuovamente il login.';
                        errorType = 'auth';
                        
                        if (window.toastSystem) {
                            window.toastSystem.showAuthError(errorMessage);
                        }
                        
                        setTimeout(() => {
                            window.location.href = '/login';
                        }, 3000);
                        
                    } else if (response.status === 403) {
                        errorMessage = 'Non hai i permessi per applicare questi filtri.';
                        errorType = 'permission';
                        
                        if (window.toastSystem) {
                            window.toastSystem.showError(errorMessage, {
                                title: 'Errore di Autorizzazione',
                                details: {
                                    operation: 'apply_filters',
                                    required: 'filter_permissions'
                                }
                            });
                        }
                        
                    } else if (response.status >= 500) {
                        errorMessage = 'Errore del server durante l\'applicazione dei filtri. Riprova più tardi.';
                        errorType = 'server';
                        
                        if (window.toastSystem) {
                            window.toastSystem.showNetworkError(new Error(errorMessage), {
                                retryHandler: () => this.applyFilters()
                            });
                        }
                    } else {
                        if (window.toastSystem) {
                            window.toastSystem.showError(errorMessage, {
                                details: {
                                    operation: 'apply_filters',
                                    status: response.status
                                }
                            });
                        }
                    }
                    
                    console.error('API Error:', response.status, errorMessage);
                    throw new Error(`Errore API ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                this.photos = Array.isArray(data) ? data.filter(photo => photo && photo.id) : [];
                this.filteredPhotos = this.photos;
                this.currentPage = 1;
                this.updatePagination();
                this.updateStatistics();
                
                console.log(`Filters applied: ${this.filteredPhotos.length} photos found`);
                
            } catch (error) {
                // Clear the timeout if there's an error
                clearTimeout(timeoutId);
                
                // Handle timeout specifically
                if (error.name === 'AbortError') {
                    console.error('Request timeout: The server took too long to respond');
                    this.showAlertMessage('Timeout del server. Riprova più tardi.');
                } else {
                    console.error('Error applying filters:', error);
                    this.showAlertMessage('Errore nell\'applicazione dei filtri. Riprova più tardi.');
                }
                
                // Ensure we have valid arrays even on error
                if (!Array.isArray(this.photos)) {
                    this.photos = [];
                }
                if (!Array.isArray(this.filteredPhotos)) {
                    this.filteredPhotos = [];
                }
            } finally {
                // Always reset isLoading state, even if an error occurred
                this.isLoading = false;
            }
        },

        // Count active filters
        getActiveFiltersCount() {
            let count = 0;
            if (this.filters.search?.trim()) count++;
            if (this.filters.photo_type) count++;
            if (this.filters.material) count++;
            if (this.filters.excavation_area?.trim()) count++;
            if (this.filters.stratigraphic_unit?.trim()) count++;
            if (this.filters.chronology_period?.trim()) count++;
            if (this.filters.object_type?.trim()) count++;
            if (this.filters.conservation_status) count++;
            if (this.filters.is_published === true) count++;
            if (this.filters.is_validated === true) count++;
            if (this.filters.has_deep_zoom === true) count++;
            if (this.filters.has_inventory === true) count++;
            if (this.has_description === true) count++;
            if (this.filters.has_photographer === true) count++;
            if (this.filters.upload_date_from) count++;
            if (this.filters.upload_date_to) count++;
            if (this.filters.photo_date_from) count++;
            if (this.filters.photo_date_to) count++;
            if (this.filters.find_date_from) count++;
            if (this.filters.find_date_to) count++;
            if (this.filters.min_width) count++;
            if (this.filters.max_width) count++;
            if (this.filters.min_height) count++;
            if (this.filters.max_height) count++;
            if (this.filters.min_file_size_mb) count++;
            if (this.filters.max_file_size_mb) count++;
            return count;
        },

        // Get list of active filters for display
        getActiveFiltersList() {
            const filtersList = [];
            const filterLabels = {
                search: 'Ricerca',
                photo_type: 'Tipo Foto',
                material: 'Materiale',
                excavation_area: 'Area Scavo',
                stratigraphic_unit: 'US',
                chronology_period: 'Periodo',
                object_type: 'Tipo Oggetto',
                conservation_status: 'Conservazione',
                is_published: 'Pubblicato',
                is_validated: 'Validato',
                has_deep_zoom: 'Deep Zoom',
                has_inventory: 'Con Inventario',
                has_description: 'Con Descrizione',
                has_photographer: 'Con Fotografo',
                upload_date_from: 'Upload da',
                upload_date_to: 'Upload a',
                photo_date_from: 'Foto da',
                photo_date_to: 'Foto a',
                find_date_from: 'Rinv. da',
                find_date_to: 'Rinv. a',
                min_width: 'Largh. min',
                max_width: 'Largh. max',
                min_height: 'Altez. min',
                max_height: 'Altez. max',
                min_file_size_mb: 'Size min',
                max_file_size_mb: 'Size max'
            };
            
            Object.keys(this.filters).forEach(key => {
                const value = this.filters[key];
                if (value && value !== '' && value !== null && key !== 'sortBy') {
                    filtersList.push({
                        key: key,
                        label: filterLabels[key] || key,
                        value: value === true ? '✓' : value
                    });
                }
            });
            
            return filtersList;
        },

        // Clear specific filter
        clearFilter(filterKey) {
            if (filterKey in this.filters) {
                if (typeof this.filters[filterKey] === 'boolean') {
                    this.filters[filterKey] = null;
                } else {
                    this.filters[filterKey] = '';
                }
                this.applyFilters();
            }
        },

        // Set date preset for quick filtering
        setDatePreset(preset) {
            const now = new Date();
            let startDate;
            
            switch (preset) {
                case 'today':
                    startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                    break;
                case 'week':
                    startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                    break;
                case 'month':
                    startDate = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
                    break;
                case 'year':
                    startDate = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
                    break;
            }
            
            if (startDate) {
                this.filters.upload_date_from = startDate.toISOString().split('T')[0];
                this.filters.upload_date_to = now.toISOString().split('T')[0];
                this.applyFilters();
            }
        },

        hasActiveFilters() {
            return this.getActiveFiltersCount() > 0;
        },

        clearAllFilters() {
            // Reset all filter values
            Object.keys(this.filters).forEach(key => {
                if (key === 'sortBy') {
                    this.filters[key] = 'created_desc';
                } else if (typeof this.filters[key] === 'boolean') {
                    this.filters[key] = null;
                } else {
                    this.filters[key] = '';
                }
            });
            this.applyFilters();
        },

        // Pagination
        updatePagination() {
            const start = (this.currentPage - 1) * this.itemsPerPage;
            const end = start + this.itemsPerPage;
            this.paginatedPhotos = this.filteredPhotos.slice(start, end);
        },

        goToPage(page) {
            this.currentPage = page;
            this.updatePagination();
        },

        previousPage() {
            if (this.currentPage > 1) {
                this.goToPage(this.currentPage - 1);
            }
        },

        nextPage() {
            if (this.currentPage < this.totalPages) {
                this.goToPage(this.currentPage + 1);
            }
        },

        // Selection Methods
        selectAllPhotos() {
            // Get all photo IDs from filtered photos, excluding US photos which can't be selected
            const selectablePhotoIds = this.filteredPhotos
                .filter(photo => photo && photo.id && photo.source_type !== 'us_file')
                .map(photo => photo.id);
            
            this.selectedPhotos = selectablePhotoIds;
            console.log(`Selected ${this.selectedPhotos.length} photos`);
        },

        deselectAllPhotos() {
            this.selectedPhotos = [];
            console.log('Deselected all photos');
        },

        // Photo Modal Methods
        openPhotoModal(index) {
            console.log('openPhotoModal called with index:', index);

            // Validate index
            if (index < 0 || index >= this.photos.length) {
                console.error('Invalid photo index:', index);
                this.showAlertMessage('Errore: indice foto non valido');
                return;
            }

            // Store the currently focused element for later return
            this.previouslyFocusedElement = document.activeElement;

            this.currentPhotoIndex = index;
            this.currentPhoto = this.photos[index];

            // Validate current photo
            if (!this.currentPhoto || !this.currentPhoto.id) {
                console.error('Invalid photo at index:', index, this.currentPhoto);
                this.showAlertMessage('Errore: foto non valida');
                return;
            }

            this.showPhotoModal = true;
            this.photoViewMode = 'openseadragon'; // Always use OpenSeadragon only
            this.showSidebar = false; // Hide sidebar initially

            // Reset OpenSeadragon state
            this.osdViewer = null;
            this.osdLoading = true; // Start loading immediately
            this.osdError = false;
            this.osdErrorMessage = '';

            // Make this instance globally accessible for OpenSeadragon
            window.photosManagerInstance = this;

            console.log('Photo modal opened for:', this.currentPhoto?.filename);

            // Update URL
            const url = new URL(window.location);
            url.searchParams.set('photo', this.currentPhoto.id);
            window.history.replaceState(null, '', url.toString());

            // Initialize OpenSeadragon immediately
            this.$nextTick(async () => {
                await this.switchToOpenSeadragon();
                
                // Emit event to notify OpenSeadragon component of photo change
                this.$dispatch('current-photo-changed', {
                    photo: this.currentPhoto
                });
                
                // Focus management after initialization
                const closeButton = document.querySelector('[aria-label="Chiudi modal"]');
                if (closeButton) {
                    closeButton.focus();
                }
            });
        },

        // Photo Modal Methods - OpenSeadragon only
        resetImageState() {
            this.imageLoaded = false;
            this.imageError = false;
            this.photoViewMode = 'openseadragon'; // Always OpenSeadragon
            // Don't destroy OpenSeadragon when just resetting state
        },

        preloadImage() {
            console.log('preloadImage called for:', this.currentPhoto?.filename);
            if (!this.currentPhoto) return;

            const img = new Image();
            img.onload = () => {
                console.log('Image loaded successfully');
                this.imageLoaded = true;
            };
            img.onerror = () => {
                console.log('Image load error');
                this.imageError = true;
            };
            img.src = this.currentPhoto.file_url;
        },

        retryLoadImage() {
            console.log('retryLoadImage called');
            this.imageError = false;
            this.imageLoaded = false;
            this.preloadImage();
        },

        async toggleViewMode() {
            console.log('toggleViewMode: OpenSeadragon-only mode - no toggle available');
            // Do nothing - always stay in OpenSeadragon mode
        },

        async switchToOpenSeadragon() {
            console.log('switchToOpenSeadragon: Starting OpenSeadragon initialization');
            this.photoViewMode = 'openseadragon';
            this.osdLoading = true;
            this.osdError = false;
            this.osdErrorMessage = '';

            try {
                console.log('switchToOpenSeadragon: About to call initOpenSeadragon');
                await this.initOpenSeadragon();
                console.log('switchToOpenSeadragon: initOpenSeadragon completed successfully');
            } catch (error) {
                console.error('switchToOpenSeadragon: Failed to initialize OpenSeadragon:', error);
                this.osdError = true;
                this.osdErrorMessage = error.message || 'Errore inizializzazione del visualizzatore';
                
                // Non usiamo fallback - tutte le immagini devono funzionare con OpenSeadragon
                // Se fallisce, mostriamo l'errore ma manteniamo il tentativo
                console.warn('OpenSeadragon initialization failed but no fallback will be used');
            } finally {
                this.osdLoading = false;
                console.log('switchToOpenSeadragon: Finished (loading set to false)');
            }
        },

        async initOpenSeadragon() {
            console.log('initOpenSeadragon: Function called successfully!');

            // Load OpenSeadragon if not available
            if (typeof OpenSeadragon === 'undefined') {
                console.log('Loading OpenSeadragon script...');
                await this.loadOpenSeadragonScript();
            }

            // Check if photo has deep zoom support
            console.log('Getting deep zoom info...');
            const deepZoomInfo = await this.getDeepZoomInfo();
            console.log('Deep zoom info received:', deepZoomInfo);

            let tileSource;
            if (deepZoomInfo && deepZoomInfo.available && deepZoomInfo.levels > 0) {
                console.log('Using deep zoom tiles with levels:', deepZoomInfo.levels);
                
                // Use OpenSeadragon's built-in TileSource format
                tileSource = {
                    width: deepZoomInfo.width,
                    height: deepZoomInfo.height,
                    tileSize: deepZoomInfo.tile_size || 256,
                    tileOverlap: deepZoomInfo.overlap || 0,
                    minLevel: 0,
                    maxLevel: deepZoomInfo.levels - 1,
                    getTileUrl: function(level, x, y) {
                        // Use the current site and photo IDs from the context
                        const siteId = window.photosManagerInstance?.getCurrentSiteId();
                        const photoId = window.photosManagerInstance?.currentPhoto?.id;
                        
                        if (!siteId || !photoId) {
                            console.error('Site ID or Photo ID not available for tile URL generation');
                            return '';
                        }
                        
                        // Use tile format from deep zoom info (PNG for transparent images, JPG for others)
                        const tileFormat = deepZoomInfo.tile_format || 'jpg';
                        const extension = tileFormat === 'png' ? 'png' : 'jpg';
                        // Use PUBLIC endpoint for OpenSeadragon (no auth headers required)
                        const url = `/api/v1/deepzoom/public/sites/{{ site.id }}/photos/${photoId}/tiles/${level}/${x}_${y}.${extension}`;
                        return url;
                    }
                };
            } else {
                console.log('Using simple image with OpenSeadragon (no tiles available)');
                // SEMPRE usiamo OpenSeadragon, anche senza tiles
                tileSource = {
                    type: 'image',
                    url: this.currentPhoto.file_url,
                    buildPyramid: true,
                    crossOriginPolicy: 'Anonymous'
                };
            }

            console.log('Final tile source:', tileSource);

            // Create OpenSeadragon viewer
            const container = document.getElementById('openseadragon-container');
            if (!container) {
                throw new Error('Container OpenSeadragon non trovato');
            }

            // Store FAB container before clearing
            const fabContainer = document.getElementById('osd-fab-container');
            let fabHTML = '';
            if (fabContainer) {
                fabHTML = fabContainer.outerHTML;
                console.log('Preserved FAB container HTML:', fabHTML.substring(0, 100) + '...');
            }

            // Clear container but preserve FAB container
            container.innerHTML = '';
            
            // Restore FAB container if it was preserved
            if (fabHTML) {
                container.innerHTML = fabHTML;
                console.log('Restored FAB container to container');
            }
            
            console.log('Container cleared, creating OpenSeadragon viewer...');

            // Detect if image might have transparency (PNG format)
            const hasTransparency = this.currentPhoto.filename.toLowerCase().endsWith('.png');
            const backgroundColor = hasTransparency ? '#ffffff' : '#000000';
            
            try {
                this.osdViewer = OpenSeadragon({
                    element: container,
                    tileSources: [tileSource],
                    prefixUrl: '/static/img/openseadragon/',
                    animationTime: 0.5,
                    blendTime: 0.1,
                    constrainDuringPan: true,
                    maxZoomPixelRatio: 2,
                    minZoomLevel: 0.1,
                    maxZoomLevel: 10,
                    zoomPerClick: 2.0,
                    zoomPerScroll: 1.2,
                    showNavigationControl: false,
                    showZoomControl: false,
                    showHomeControl: false,
                    showFullPageControl: false,
                    showRotationControl: false,
                    debugMode: false,
                    // Set background color based on image type
                    backgroundColor: backgroundColor,
                    gestureSettingsMouse: {
                        scrollToZoom: true,
                        clickToZoom: true,
                        dblClickToZoom: true,
                        pinchToZoom: true,
                        flickEnabled: true
                    },
                    gestureSettingsTouch: {
                        scrollToZoom: false,
                        clickToZoom: false,
                        dblClickToZoom: true,
                        pinchToZoom: true,
                        flickEnabled: true
                    }
                });

                console.log('OpenSeadragon instance created:', this.osdViewer);

                // Wait for viewer to be ready
                return new Promise((resolve, reject) => {
                    let resolved = false;
                    const timeoutId = setTimeout(() => {
                        if (!resolved) {
                            console.error('OpenSeadragon initialization timeout after 15 seconds');
                            resolved = true;
                            reject(new Error('Timeout apertura immagine'));
                        }
                    }, 15000);

                    this.osdViewer.addHandler('open', () => {
                        console.log('OpenSeadragon viewer opened successfully');
                        if (!resolved) {
                            resolved = true;
                            clearTimeout(timeoutId);
                            
                            // Initialize FAB controls after OpenSeadragon is ready
                            // Use a longer delay to ensure DOM is fully updated
                            setTimeout(() => {
                                const managerInstance = window.photosManagerInstance;
                                if (managerInstance && managerInstance.initializeFABControls) {
                                    managerInstance.initializeFABControls();
                                } else {
                                    console.warn('photosManagerInstance not available for FAB initialization');
                                }
                            }, 200); // Increased delay to 200ms
                            
                            resolve();
                        }
                    });

                    this.osdViewer.addHandler('open-failed', (event) => {
                        console.error('OpenSeadragon failed to open:', event);
                        if (!resolved) {
                            resolved = true;
                            clearTimeout(timeoutId);
                            reject(new Error('Impossibile aprire immagine: ' + event.message ));
                        }
                    });

                    this.osdViewer.addHandler('tile-load-failed', (event) => {
                        console.warn('Tile load failed:', event);
                        // Non facciamo fallback - registriamo solo l'errore
                        if (!this.osdTileFailureCount) this.osdTileFailureCount = 0;
                        this.osdTileFailureCount++;
                        
                        if (this.osdTileFailureCount > 10) {
                            console.warn('Many tile failures, but continuing with OpenSeadragon');
                        }
                    });

                    this.osdViewer.addHandler('tile-loaded', (event) => {
                        // Reset failure counter on successful tile load
                        if (this.osdTileFailureCount > 0) {
                            this.osdTileFailureCount = Math.max(0, this.osdTileFailureCount - 1);
                        }
                    });
                });

            } catch (error) {
                console.error('Error creating OpenSeadragon viewer:', error);
                throw error;
            }
        },

        // Initialize FAB Controls
        initializeFABControls() {
            console.log('Initializing FAB controls...');
            
            // Wait for DOM to be ready with retry mechanism
            this.initializeFABControlsWithRetry(0);
        },
        
        // Initialize FAB Controls with retry mechanism
        initializeFABControlsWithRetry(attempt) {
            const maxRetries = 10;
            const retryDelay = 100;
            
            // Try multiple selector strategies to find the FAB container
            let fabContainer = document.getElementById('osd-fab-container');
            
            // If not found by ID, try by class name
            if (!fabContainer) {
                fabContainer = document.querySelector('.osd-fab-container');
            }
            
            // If still not found, try within the OpenSeadragon container
            if (!fabContainer) {
                const osdContainer = document.getElementById('openseadragon-container');
                if (osdContainer) {
                    fabContainer = osdContainer.querySelector('#osd-fab-container') ||
                                   osdContainer.querySelector('.osd-fab-container');
                }
            }
            
            // If still not found, create the FAB container dynamically
            if (!fabContainer) {
                const osdContainer = document.getElementById('openseadragon-container');
                if (osdContainer) {
                    console.log('Creating FAB container dynamically...');
                    fabContainer = this.createFABContainer(osdContainer);
                }
            }
            
            if (!fabContainer) {
                if (attempt < maxRetries) {
                    console.log(`FAB container not found, retrying (${attempt + 1}/${maxRetries})...`);
                    setTimeout(() => {
                        this.initializeFABControlsWithRetry(attempt + 1);
                    }, retryDelay);
                    return;
                } else {
                    console.error('FAB container not found after', maxRetries, 'attempts');
                    console.log('Debug: Available containers:', {
                        osdContainer: !!document.getElementById('openseadragon-container'),
                        fabContainer: !!document.getElementById('osd-fab-container'),
                        fabContainerByClass: !!document.querySelector('.osd-fab-container')
                    });
                    return;
                }
            }
            
            console.log('FAB container found, proceeding with initialization...');
            console.log('FAB container element:', fabContainer);
            console.log('FAB container parent:', fabContainer.parentElement);
            console.log('FAB container display style:', window.getComputedStyle(fabContainer).display);
            
            // Check if already initialized
            if (fabContainer.dataset.initialized === 'true') {
                console.log('FAB controls already initialized, skipping...');
                return;
            }
            
            // Show FAB container with animation
            console.log('Setting FAB container display to flex');
            fabContainer.style.display = 'flex';
            fabContainer.style.visibility = 'visible';
            fabContainer.dataset.initialized = 'true';
            
            // Force a reflow to ensure the container is visible
            fabContainer.offsetHeight;
            console.log('FAB container is now visible:', fabContainer.style.display);
            
            // Get buttons
            const zoomInBtn = document.getElementById('osd-zoom-in');
            const zoomOutBtn = document.getElementById('osd-zoom-out');
            const resetBtn = document.getElementById('osd-reset-view');
            const rotateLeftBtn = document.getElementById('osd-rotate-left');
            const rotateRightBtn = document.getElementById('osd-rotate-right');
            const fullscreenBtn = document.getElementById('osd-fullscreen');
            
            // Debug: Log which buttons were found
            console.log('FAB Buttons found:', {
                zoomInBtn: !!zoomInBtn,
                zoomOutBtn: !!zoomOutBtn,
                resetBtn: !!resetBtn,
                rotateLeftBtn: !!rotateLeftBtn,
                rotateRightBtn: !!rotateRightBtn,
                fullscreenBtn: !!fullscreenBtn
            });
            
            // Store reference for cleanup
            this.fabControls = {
                container: fabContainer,
                buttons: [zoomInBtn, zoomOutBtn, resetBtn, rotateLeftBtn, rotateRightBtn, fullscreenBtn]
            };
            
            // Add event listeners
            if (zoomInBtn) {
                console.log('Adding zoomIn event listener');
                zoomInBtn.addEventListener('click', (e) => {
                    console.log('Zoom in button clicked');
                    e.preventDefault();
                    this.zoomIn();
                });
                zoomInBtn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.zoomIn();
                    }
                });
            } else {
                console.error('Zoom in button not found!');
            }
            
            if (zoomOutBtn) {
                console.log('Adding zoomOut event listener');
                zoomOutBtn.addEventListener('click', (e) => {
                    console.log('Zoom out button clicked');
                    e.preventDefault();
                    this.zoomOut();
                });
                zoomOutBtn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.zoomOut();
                    }
                });
            }
            
            if (resetBtn) {
                resetBtn.addEventListener('click', (e) => {
                    console.log('Reset view button clicked');
                    e.preventDefault();
                    this.resetView();
                });
                resetBtn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.resetView();
                    }
                });
            }
            
            if (rotateLeftBtn) {
                rotateLeftBtn.addEventListener('click', (e) => {
                    console.log('Rotate left button clicked');
                    e.preventDefault();
                    this.rotateLeft();
                });
                rotateLeftBtn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.rotateLeft();
                    }
                });
            }
            
            if (rotateRightBtn) {
                rotateRightBtn.addEventListener('click', (e) => {
                    console.log('Rotate right button clicked');
                    e.preventDefault();
                    this.rotateRight();
                });
                rotateRightBtn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.rotateRight();
                    }
                });
            }
            
            if (fullscreenBtn) {
                fullscreenBtn.addEventListener('click', (e) => {
                    console.log('Fullscreen button clicked');
                    e.preventDefault();
                    this.toggleFullscreen();
                });
                fullscreenBtn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.toggleFullscreen();
                    }
                })
            }
            
            // Add keyboard shortcuts
            this.addKeyboardShortcuts();
            
            console.log('FAB controls initialized successfully');
        },
        
        // Create FAB Container dynamically if missing
        createFABContainer(osdContainer) {
            console.log('Creating FAB container dynamically...');
            
            if (!osdContainer) {
                console.error('Cannot create FAB container: OpenSeadragon container not found');
                return null;
            }
            
            // Create the FAB container div
            const fabContainer = document.createElement('div');
            fabContainer.id = 'osd-fab-container';
            fabContainer.className = 'osd-fab-container';
            fabContainer.style.display = 'flex';
            fabContainer.style.visibility = 'visible';
            fabContainer.dataset.initialized = 'false';
            
            // Create all FAB buttons
            const buttonsHTML = `
                <!-- Zoom In Button -->
                <button id="osd-zoom-in" class="osd-fab osd-fab-primary"
                        aria-label="Zoom in"
                        tabindex="0"
                        type="button">
                    <svg viewBox="0 0 24 24">
                        <path d="M19 13h-6v6h-2v-6H5v-2h6v2h6v2z"/>
                    </svg>
                    <span class="osd-fab-tooltip">Zoom In (+)</span>
                </button>
                
                <!-- Zoom Out Button -->
                <button id="osd-zoom-out" class="osd-fab osd-fab-primary"
                        aria-label="Zoom out"
                        tabindex="0"
                        type="button">
                    <svg viewBox="0 0 24 24">
                        <path d="M19 13H5v-2h14v2z"/>
                    </svg>
                    <span class="osd-fab-tooltip">Zoom Out (-)</span>
                </button>
                
                <!-- Reset View Button -->
                <button id="osd-reset-view" class="osd-fab osd-fab-secondary"
                        aria-label="Reset view"
                        tabindex="0"
                        type="button">
                    <svg viewBox="0 0 24 24">
                        <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6V7c0-3.31-2.69-6-6H5zM12 15V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6V7c0-3.31-2.69-6-6H5zM12 5v10h10v2H7v2H7V5H5z"/>
                    </svg>
                    <span class="osd-fab-tooltip">Reset View (0)</span>
                </button>
                
                <!-- Rotate Left Button -->
                <button id="osd-rotate-left" class="osd-fab osd-fab-secondary"
                        aria-label="Rotate left"
                        tabindex="0"
                        type="button">
                    <svg viewBox="0 0 24 24">
                        <path d="M7.11 8.53L5.7 7.11C4.8 8.27 4.24 9.61 4.07 11h2.02c.14-.87.49-1.72 1.02-2.47zM6.09 13H4.07c.17 1.39.72 2.73 1.89l1.41-1.42c-.52-.75-.87-1.59-1.01-2.47zm1.01 5.32c1.16.9 2.51 1.44 1.61 1.61V17.9c-.87-.15-1.71-.49-2.46-1.03L7.1 18.32zM13 4.07V1L8.45 5.55 13 10V6.09c2.84.48 5 2.94 5.91s-2.16 5.43-5.91v2.02c3.95-.49 7-3.85 7.93s-3.05 7.44-7.93s-3.05-7.44-7.93z"/>
                    </svg>
                    <span class="osd-fab-tooltip">Rotate Left (Q)</span>
                </button>
                
                <!-- Rotate Right Button -->
                <button id="osd-rotate-right" class="osd-fab osd-fab-secondary"
                        aria-label="Rotate right"
                        tabindex="0"
                        type="button">
                    <svg viewBox="0 0 24 24">
                        <path d="M15.55 5.55L11 1v3.07C7.06 4.56 4 7.92 4s-2.16 5.43-5.91V10l4.55-4.45zM19.93 11c-.17-1.39-.72-2.73-1.89l-1.42 1.42c.54.75.88 1.6 1.02 2.48h2.02c.14.87.48 1.72 2.48h2.02c-.14.87.48 1.72 2.48h2.02c-.14.87.48 1.72 2.48h-2.02c-.14.87.48-1.72 2.48-2.48z"/>
                    </svg>
                    <span class="osd-fab-tooltip">Rotate Right (E)</span>
                </button>
                
                <!-- Fullscreen Button -->
                <button id="osd-fullscreen" class="osd-fab osd-fab-accent"
                        aria-label="Toggle fullscreen"
                        tabindex="0"
                        type="button">
                    <svg viewBox="0 0 24 20">
                        <path d="M7 14H5v5h5v-2H7v-3h5v5z"/>
                    </svg>
                    <span class="osd-fab-tooltip">Fullscreen (F)</span>
                </button>
            `;
            
            fabContainer.innerHTML = buttonsHTML;
            
            // Append to OpenSeadragon container
            osdContainer.appendChild(fabContainer);
            
            console.log('FAB container created and appended successfully');
            return fabContainer;
        },
        
        // FAB Control Functions
        zoomIn() {
            if (this.osdViewer) {
                this.osdViewer.viewport.zoomBy(1.5);
                this.addRippleEffect('osd-zoom-in');
            }
        },
        
        zoomOut() {
            if (this.osdViewer) {
                this.osdViewer.viewport.zoomBy(0.67);
                this.addRippleEffect('osd-zoom-out');
            }
        },
        
        resetView() {
            if (this.osdViewer) {
                this.osdViewer.viewport.goHome();
                this.addRippleEffect('osd-reset-view');
            }
        },
        
        rotateLeft() {
            if (this.osdViewer) {
                const currentRotation = this.osdViewer.viewport.getRotation();
                this.osdViewer.viewport.setRotation(currentRotation - 90);
                this.addRippleEffect('osd-rotate-left');
            }
        },
        
        rotateRight() {
            if (this.osdViewer) {
                const currentRotation = this.osdViewer.viewport.getRotation();
                this.osdViewer.viewport.setRotation(currentRotation + 90);
                this.addRippleEffect('osd-rotate-right');
            }
        },
        
        toggleFullscreen() {
            const container = document.getElementById('openseadragon-container');
            if (!document.fullscreenElement) {
                container.requestFullscreen().catch(err => {
                    console.error(`Error attempting to enable fullscreen: ${err.message}`);
                });
            } else {
                document.exitFullscreen();
            }
            this.addRippleEffect('osd-fullscreen');
        },
        
        // Add ripple effect to buttons
        addRippleEffect(buttonId) {
            const button = document.getElementById(buttonId);
            if (!button) return;
            
            // Create ripple element
            const ripple = document.createElement('span');
            ripple.style.position = 'absolute';
            ripple.style.borderRadius = '50%';
            ripple.style.background = 'rgba(255, 255, 255, 0.5)';
            ripple.style.width = '20px';
            ripple.style.height = '20px';
            ripple.style.top = '50%';
            ripple.style.left = '50%';
            ripple.style.transform = 'translate(-50%, -50%) scale(0)';
            ripple.style.animation = 'ripple 0.6s ease-out';
            ripple.style.pointerEvents = 'none';
            
            // Add ripple animation
            const style = document.createElement('style');
            style.textContent = `
                @keyframes ripple {
                    to {
                        transform: translate(-50%, -50%) scale(4);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
            
            button.appendChild(ripple);
            
            // Remove ripple after animation
            setTimeout(() => {
                if (ripple.parentNode) {
                    ripple.parentNode.removeChild(ripple);
                }
            }, 600);
        },
        
        // Keyboard shortcuts
        addKeyboardShortcuts() {
            this.keyboardHandler = (e) => {
                // Only handle shortcuts when photo modal is open and not typing in input fields
                if (!this.showPhotoModal || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                    return;
                }
                
                switch(e.key.toLowerCase()) {
                    case '+':
                    case '=':
                    case '_':
                        e.preventDefault();
                        this.zoomIn();
                        break;
                    case '-':
                    case '_':
                    case 'Q':
                        e.preventDefault();
                        this.zoomOut();
                        break;
                    case '0':
                    case ')':
                        e.preventDefault();
                        this.resetView();
                        break;
                    case 'r':
                    case 'R':
                        e.preventDefault();
                        this.rotateRight();
                        break;
                    case 'q':
                    case 'Q':
                        e.preventDefault();
                        this.rotateLeft();
                        break;
                    case 'f':
                    case 'F':
                        e.preventDefault();
                        this.toggleFullscreen();
                        break;
                }
            };
            
            document.addEventListener('keydown', this.keyboardHandler);
        },
        
        // Cleanup FAB controls
        cleanupFABControls() {
            console.log('Cleaning up FAB controls...');
            
            // Hide container and reset initialization flag
            if (this.fabControls && this.fabControls.container) {
                this.fabControls.container.style.display = 'none';
                this.fabControls.container.dataset.initialized = 'false';
            }
            
            // Also try to reset the main container
            const fabContainer = document.getElementById('osd-fab-container');
            if (fabContainer) {
                fabContainer.style.display = 'none';
                fabContainer.dataset.initialized = 'false';
            }
            
            // Remove keyboard shortcuts
            if (this.keyboardHandler) {
                document.removeEventListener('keydown', this.keyboardHandler);
                this.keyboardHandler = null;
            }
            
            // Clear references
            this.fabControls = null;
            
            console.log('FAB controls cleaned up');
        },

        // loadOpenSeadragonScript removed - now handled by the OpenSeadragon component

        async getDeepZoomInfo() {
            if (!this.currentPhoto) return null;

            try {
                // Get current site ID from URL or global variable
                const siteId = this.getCurrentSiteId();
                console.log('Getting deep zoom info for:', siteId, this.currentPhoto.id);
                
                const response = await fetch(`/api/v1/deepzoom/sites/{{ site.id }}/photos/${this.currentPhoto.id}/info`, {
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    }
                });

                // Handle specific authentication errors
                if (response.status === 401) {
                    console.error('Authentication error (401): Token expired or invalid');
                    this.showAlertMessage('Sessione scaduta. Effettua nuovamente il login.');
                    // Optionally redirect to login page
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                    throw new Error('Errore di autenticazione: sessione scaduta');
                }
                
                if (response.status === 403) {
                    console.error('Authorization error (403): Insufficient permissions');
                    this.showAlertMessage('Non hai i permessi per visualizzare le informazioni Deep Zoom di questa foto.');
                    throw new Error('Errore di autorizzazione: permessi insufficienti');
                }

                if (response.ok) {
                    const data = await response.json();
                    console.log('Deep zoom response:', data);
                    
                    // Check if deep zoom is actually available
                    if (data.available === false || data.levels === 0 || data.total_tiles === 0) {
                        console.log('Deep zoom tiles not available for this photo');
                        return null;
                    }
                    
                    return data;
                } else if (response.status === 404) {
                    console.log('Deep zoom info not found for this photo');
                    return null;
                } else {
                    const errorText = await response.text();
                    console.warn('Failed to get deep zoom info:', response.status, response.statusText, errorText);
                    this.showAlertMessage(`Errore nel recupero delle informazioni Deep Zoom: ${response.status} ${response.statusText}`);
                    return null;
                }
            } catch (error) {
                console.warn('Failed to get deep zoom info:', error);
                this.showAlertMessage(`Errore nel recupero delle informazioni Deep Zoom: ${error.message || 'Errore sconosciuto'}. Riprova più tardi.`);
                return null;
            }
        },


        getCurrentSiteId() {
            // Try to get site ID from URL path
            const pathSegments = window.location.pathname.split('/');
            const sitesIndex = pathSegments.indexOf('view');
            if (sitesIndex !== -1 && pathSegments[sitesIndex + 1]) {
                return pathSegments[sitesIndex + 1];
            }

            // Fallback: try to get from global variable
            if (window.currentSiteId) {
                return window.currentSiteId;
            }

            console.error('Could not determine current site ID');
            return null;
        },

        // destroyOpenSeadragon removed - now handled by the OpenSeadragon component

        downloadPhoto() {
            console.log('downloadPhoto called');
            if (!this.currentPhoto) return;

            const link = document.createElement('a');
            link.href = this.currentPhoto.file_url;
            link.download = this.currentPhoto.filename;
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        },

        async sharePhoto() {
            console.log('sharePhoto called');
            if (!this.currentPhoto) return;

            const url = new URL(window.location);
            url.searchParams.set('photo', this.currentPhoto.id);
            const shareUrl = url.toString();

            if (navigator.share) {
                try {
                    await navigator.share({
                        title: this.currentPhoto.filename,
                        text: this.currentPhoto.description || 'Foto archeologica',
                        url: shareUrl
                    });
                } catch (error) {
                    if (error.name !== 'AbortError') {
                        console.error('Share failed:', error);
                        this.fallbackShare(shareUrl);
                    }
                }
            } else {
                this.fallbackShare(shareUrl);
            }
        },

        setCurrentPhoto(index) {
            console.log('setCurrentPhoto called with index:', index);
            if (index >= 0 && index < this.photos.length) {
                const photo = this.photos.find(p => p && p.id === photo.id);
                if (!photo || !photo.id) {
                    console.error('Invalid photo at index:', index, photo);
                    return;
                }

                // Clean up previous FAB controls before switching
                this.cleanupFABControls();

                this.currentPhotoIndex = index;
                this.currentPhoto = photo;
                // Keep OpenSeadragon mode - no reset to standard
                this.imageLoaded = false;
                this.imageError = false;
                // Initialize OpenSeadragon for new photo
                this.switchToOpenSeadragon();
                
                // Emit event to notify OpenSeadragon component of photo change
                this.$nextTick(() => {
                    this.$dispatch('current-photo-changed', {
                        photo: this.currentPhoto
                    });
                });
                
                // Update URL
                const url = new URL(window.location);
                url.searchParams.set('photo', this.currentPhoto.id);
                window.history.replaceState(null, '', url.toString());

                // Initialize OpenSeadragon for new photo
                this.$nextTick(async () => {
                    await this.switchToOpenSeadragon();
                    
                    // Emit event to notify OpenSeadragon component of photo change
                    this.$dispatch('current-photo-changed', {
                        photo: this.currentPhoto
                    });
                    
                    // Focus management after initialization
                    const closeButton = document.querySelector('[aria-label=\"Chiudi modal\"]');
                    if (closeButton) {
                        closeButton.focus();
                    }
                });
            });
        },

        previousPhoto() {
            console.log('previousPhoto called');
            if (this.currentPhotoIndex > 0) {
                this.setCurrentPhoto(this.currentPhotoIndex - 1);
            }
        },

        nextPhoto() {
            console.log('nextPhoto called');
            if (this.currentPhotoIndex < this.photos.length - 1) {
                this.setCurrentPhoto(this.currentPhotoIndex + 1);
            }
        },

        async openEditModal() {
            console.log('openEditModal called');
            if (!this.currentPhoto || !this.currentPhoto.id) {
                console.error('No valid current photo for edit modal');
                this.showAlertMessage('Errore: nessuna foto valida selezionata');
                return;
            }

            // Fetch fresh data from server for photo modal edit button
            try {
                console.log('Fetching fresh data for photo modal edit:', this.currentPhoto.id);
                const response = await fetch(`/api/v1/sites/{{ site.id }}/photos`, {
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    const freshPhotos = await response.json();
                    const freshPhoto = freshPhotos.find(p => p.id === this.currentPhoto.id);
                    if (freshPhoto) {
                        console.log('Fresh data received for modal edit:', freshPhoto);
                        // Update currentPhoto with fresh data
                        const photoIndex = this.photos.findIndex(p => p && p.id === this.currentPhoto.id);
                        if (photoIndex !== -1) {
                            this.photos[photoIndex] = freshPhoto;
                        }
                    }
                } else {
                    console.warn('Failed to fetch fresh photo data for modal edit, using existing data');
                }
            } catch (error) {
                console.error('Error fetching fresh photo data for modal edit:', error);
                this.showAlertMessage('Impossibile caricare dati aggiornati. Verranno usati i dati locali.');
            }

            this.showEditModal = true;

            // Initialize the metadata form with the photo data
            this.$nextTick(() => {
                // Get the metadata form component reference
                const editFormElement = this.$refs.editMetadataForm;
                if (editFormElement) {
                    // Find the Alpine.js component within the element
                    const metadataComponent = Alpine.$data(editFormElement.querySelector('[x-data*=\"metadataFormComponent\"]'));
                    if (metadataComponent) {
                        if (this.isMultipleSelection) {
                            // For multi-edit, don't load specific photo data - form will be empty
                            console.log('Multi-edit mode: form will start empty');
                            if (metadataComponent.clearForm) {
                                metadataComponent.clearForm();
                            }
                        } else if (metadataComponent.loadPhotoData) {
                            console.log('Loading photo data into form component');
                            metadataComponent.loadPhotoData(photo);
                        }
                    } else {
                        console.warn('Metadata form component not found');
                        // Fallback: dispatch event to load photo data
                        if (!this.isMultipleSelection) {
                            this.$dispatch('load-photo-data', { photo: photo });
                        }
                    }
                } else {
                    console.warn('Edit form element not found');
                }
            });
        },

        // Handle metadata form submission for edit
        handleEditMetadataSubmit(event) {
            console.log('handleEditMetadataSubmit called with:', event.detail);
            const metadata = event.detail.data || event.detail.metadata);  // Support both formats
            const metadata = event.detail.data || event.detail.metadata;  // Support both formats
            this.savePhotoEditWithMetadata(metadata);
        },

        // Submit edit form programmatically
        submitEditForm() {
            console.log('submitEditForm called');

            // Validate that we have a photo to edit
            if (this.isMultipleSelection) {
                if (!this.selectedPhotos.length || this.selectedPhotos.length === 0) {
                    console.error('No photos selected for bulk edit');
                    this.showAlertMessage('Errore: nessuna foto selezionata per modifica di massa');
                    return;
                }
            } else {
                if (!this.selectedPhoto || !this.selectedPhoto.id) {
                    console.error('No photo selected for edit');
                    this.showAlertMessage('Errore: nessuna foto selezionata per modifica');
                    return;
                }

            const editFormContainer = this.$refs.editMetadataForm;
            if (editFormContainer) {
                // Find the Alpine component inside the container
                const metadataComponent = Alpine.$data(editFormContainer.querySelector('[x-data*=\"metadataFormComponent\"]'));
                if (metadataComponent && metadataComponent.getMetadata) {
                    const metadata = metadataComponent.getMetadata();
                    console.log('Got metadata from component:', metadata);
                    this.savePhotoEditWithMetadata(metadata);
                } else {
                    console.warn('Metadata component not found for submission');
                    // Fallback: trigger form submission via event
                    const form = editFormContainer.querySelector('form');
                    if (form) {
                        form.dispatchEvent(new Event('submit', { bubbles: true }));
                    }
                }
            } else {
                console.warn('Edit form container not found');
            }
        },

        // Reset edit form
        resetEditForm() {
            console.log('resetEditForm called');
            const editFormContainer = this.$refs.editMetadataForm;
            if (editFormContainer) {
                // Find the Alpine component inside the container
                const metadataComponent = Alpine.$data(editFormContainer.querySelector('[x-data*=\"metadataFormComponent\"]'));
                if (metadataComponent) {
                    if (this.selectedPhoto && !this.isMultipleSelection) {
                        // Single photo edit: reset with current photo data
                        if (metadataComponent.loadPhotoData) {
                            console.log('Resetting form with current photo data');
                            metadataComponent.loadPhotoData(this.selectedPhoto);
                        }
                    } else {
                        // Multiple selection or no photo: clear form
                        if (metadataComponent.resetForm) {
                            console.log('Resetting form to empty state');
                            metadataComponent.resetForm();
                        }
                    }
                } else {
                    console.warn('Metadata component not found for reset');
                }
            }
        },

        closeEditModal() {
            this.showEditModal = false;
            this.selectedPhoto = null;  // Clear selected photo
            this.editingPhoto = null;   // Keep for backward compatibility
            this.isSaving = false;
        },

        removeTag(tagToRemove) {
            if (this.editingPhoto && this.editingPhoto.tags) {
                this.editingPhoto.tags = this.editingPhoto.tags.filter(tag => tag !== tagToRemove);
                this.editingPhoto.tagsString = this.editingPhoto.tags.join(', ');
            }
        },

        // Updated save method that works with metadata form
        async savePhotoEditWithMetadata(metadata) {
            if (this.isMultipleSelection) {
                // Bulk edit mode
                await this.saveBulkEdit(metadata);
            } else {
                // Single photo edit mode
                await this.saveSinglePhotoEdit(metadata);
            }
        },
        
        // Single photo edit method
        async saveSinglePhotoEdit(metadata) {
            if (!this.selectedPhoto || !this.selectedPhoto.id || !metadata) {
                console.error('No valid photo selected or metadata provided');
                this.showAlertMessage('Errore: foto o metadati non validi');
                return;
            }

            this.isSaving = true;

            try {
                console.log('Saving single photo edit with metadata:', metadata);

                const response = await fetch(`/api/v1/sites/{{ site.id }}/photos/${this.selectedPhoto.id}/update`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(metadata)
                });

                // Handle specific authentication errors
                if (response.status === 401) {
                    console.error('Authentication error (401): Token expired or invalid');
                    this.showAlertMessage('Sessione scaduta. Effettua nuovamente il login.');
                    // Optionally redirect to login page
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                    throw new Error('Errore di autenticazione: sessione scaduta');
                }
                
                if (response.status === 403) {
                    console.error('Authorization error (403): Insufficient permissions');
                    this.showAlertMessage('Non hai i permessi per modificare questa foto.');
                    throw new Error('Errore di autorizzazione: permessi insufficienti');
                }

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('API Error:', response.status, errorText);
                    this.showAlertMessage(`Errore durante il salvataggio: ${response.status} ${response.statusText}`);
                    throw new Error(`Errore durante il salvataggio: ${response.status} ${response.statusText}`);
                }

                const updatedPhoto = await response.json();

                // Update local data
                const photoIndex = this.photos.findIndex(p => p && p.id === this.selectedPhoto.id);
                if (photoIndex !== -1) {
                    this.photos[photoIndex] = { ...this.photos[photoIndex], ...updatedPhoto };
                }

                // Update current photo if it's the one being edited
                if (this.currentPhoto && this.currentPhoto.id === this.selectedPhoto.id) {
                    this.currentPhoto = { ...this.currentPhoto, ...updatedPhoto };
                }

                this.extractAvailableTags();
                this.applyFilters();
                this.showAlertMessage('Metadati foto aggiornati con successo!');
                this.closeEditModal();

            } catch (error) {
                console.error('Errore durante il salvataggio:', error);
                this.showAlertMessage(`Errore durante il salvataggio: ${error.message || 'Errore sconosciuto'}. Riprova più tardi.`);
            } finally {
                this.isSaving = false;
            }
        },
        
        // Bulk edit method
        async saveBulkEdit(metadata) {
            if (!this.selectedPhotos.length || !metadata) {
                console.error('No photos selected or metadata provided for bulk edit');
                this.showAlertMessage('Errore: nessuna foto selezionata o metadati forniti');
                return;
            }

            this.isSaving = true;

            try {
                console.log('Saving bulk edit with metadata:', metadata, 'for photos:', this.selectedPhotos);

                // Filter out empty/null values from metadata for bulk edit
                const filteredMetadata = {};
                Object.keys(metadata).forEach(key => {
                    const value = metadata[key];
                    if (value !== null && value !== undefined && value !== '') {
                        // For arrays (like tags), only include if not empty
                        if (Array.isArray(value)) {
                            if (value.length > 0) {
                                filteredMetadata[key] = value;
                            }
                        } else {
                            filteredMetadata[key] = value;
                        }
                    }
                });

                const response = await fetch(`/api/v1/sites/{{ site.id }}/photos/bulk-update`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        photo_ids: this.selectedPhotos,
                        metadata: filteredMetadata
                    })
                });

                // Handle specific authentication errors
                if (response.status === 401) {
                    console.error('Authentication error (401): Token expired or invalid');
                    this.showAlertMessage('Sessione scaduta. Effettua nuovamente il login.');
                    // Optionally redirect to login page
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                    throw new Error('Errore di autenticazione: sessione scaduta');
                }
                
                if (response.status === 403) {
                    console.error('Authorization error (403): Insufficient permissions');
                    this.showAlertMessage('Non hai i permessi per modificare queste foto.');
                    throw new Error('Errore di autorizzazione: permessi insufficienti');
                }

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('API Error:', response.status, errorText);
                    this.showAlertMessage(`Errore durante l'aggiornamento di massa: ${response.status} ${response.statusText}`);
                    throw new Error(`Errore durante l'aggiornamento di massa: ${response.status} ${response.statusText}`);
                }

                const result = await response.json();

                // Refresh data to reflect changes
                await this.loadPhotos();
                this.updateStatistics();
                this.extractAvailableTags();
                
                // Don't call applyFilters here since loadPhotos already sets the photos
                // and we want to show all photos after bulk edit
                this.filteredPhotos = this.photos;
                this.updatePagination();

                this.showAlertMessage(`${this.selectedPhotos.length} foto aggiornate con successo!`);
                this.selectedPhotos = []; // Clear selection

                this.closeEditModal();

            } catch (error) {
                console.error('Errore durante l'aggiornamento di massa:', error);
                this.showAlertMessage(`Errore durante l'aggiornamento: ${error.message || 'Errore sconosciuto'}. Riprova più tardi.`);
            } finally {
                this.isSaving = false;
            }
        },
        
        // Legacy savePhotoEdit method for backward compatibility
        async savePhotoEdit() {
            console.warn('savePhotoEdit: This method is deprecated, use savePhotoEditWithMetadata instead');
            if (this.selectedPhoto) {
                // Try to get metadata from form component
                const editFormElement = this.$refs.editMetadataForm;
                if (editFormElement && editFormElement.getMetadata) {
                    const metadata = editFormElement.getMetadata();
                    await this.savePhotoEditWithMetadata(metadata);
                }
            }
        },

        // Delete Methods
        confirmDeletePhoto(photo) {
            if (!photo || !photo.id) {
                console.error('Invalid photo for deletion:', photo);
                this.showAlertMessage('Errore: foto non valida per eliminazione');
                return;
            }
            this.photoToDelete = photo;
            this.showDeleteModal = true;
        },

        async deletePhoto() {
            if (!this.photoToDelete || !this.photoToDelete.id) {
                console.error('No valid photo to delete');
                this.showAlertMessage('Errore: nessuna foto valida da eliminare');
                return;
            }

            this.isDeleting = true;

            try {
                const response = await fetch(`/api/v1/sites/{{ site.id }}/photos/${this.photoToDelete.id}`, {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    }
                });

                // Handle specific authentication errors
                if (response.status === 401) {
                    console.error('Authentication error (401): Token expired or invalid');
                    this.showAlertMessage('Sessione scaduta. Effettua nuovamente il login.');
                    // Optionally redirect to login page
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                    throw new Error('Errore di autenticazione: sessione scaduta');
                }
                
                if (response.status === 403) {
                    console.error('Authorization error (403): Insufficient permissions');
                    this.showAlertMessage('Non hai i permessi per eliminare questa foto.');
                    throw new Error('Errore di autorizzazione: permessi insufficienti');
                }

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('API Error:', response.status, errorText);
                    this.showAlertMessage(`Errore durante l'eliminazione: ${response.status} ${response.statusText}`);
                    throw new Error(`Errore durante l'eliminazione: ${response.status} ${response.statusText}`);
                }

                // Remove from local data
                this.photos = this.photos.filter(p =>