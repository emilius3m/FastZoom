// archaeological_map.js - Alpine.js component per gestione mappe archeologiche con Leaflet

document.addEventListener('alpine:init', () => {
    Alpine.data('archaeologicalMapManager', () => ({
        // Mappa e layer
        map: null,
        gridLayer: null,
        gridLabels: null,
        markersLayer: null,
        unitsLayer: null,
        
        // Stato applicazione
        currentPlan: null,
        selectedPlanId: '',
        availablePlans: [],
        
        // Modalità operative
        isDataCollectionMode: false,
        isGridMode: false,
        
        // Dati
        excavationUnits: [],
        archaeologicalData: [],
        availableModules: [],
        
        // UI State
        showPlanUploadModal: false,
        showModuleSelector: false,
        showUnitModal: false,
        showLayersPanel: false,
        isUploadingPlan: false,
        
        // Configurazione griglia
        gridConfig: {
            unitSize: 5,           // Dimensione unità in metri (standard 5x5m)
            majorGridSize: 20,     // Linee principali ogni 20m
            showLabels: true,
            showMajorGrid: true,
            showMinorGrid: true
        },
        
        // Coordinate temporanee per creazione
        currentCoordinates: null,
        selectedModule: null,
        newUnit: {
            id: '',
            coordinates_x: 0,
            coordinates_y: 0,
            size_x: 5,
            size_y: 5,
            status: 'planned',
            supervisor: '',
            notes: ''
        },
        
        // Nuovo piano
        newPlan: {
            name: '',
            description: '',
            plan_type: 'general',
            origin_x: 0.0,
            origin_y: 0.0,
            scale_factor: 1.0,
            drawing_scale: '',
            surveyor: '',
            is_primary: false
        },
        
        // === INIZIALIZZAZIONE ===
        
        async initMap() {
            try {
                // Inizializza mappa Leaflet con CRS personalizzato
                const archaeoCRS = L.extend({}, L.CRS.Simple, {
                    transformation: new L.Transformation(1, 0, -1, 0)
                });
                
                this.map = L.map('archaeological-map', {
                    crs: archaeoCRS,
                    minZoom: -2,
                    maxZoom: 4,
                    center: [0, 0],
                    zoom: 0,
                    zoomControl: true,
                    attributionControl: false
                });
                
                // Inizializza layer
                this.markersLayer = L.layerGroup().addTo(this.map);
                this.unitsLayer = L.layerGroup().addTo(this.map);
                this.gridLayer = L.layerGroup().addTo(this.map);
                this.gridLabels = L.layerGroup().addTo(this.map);
                
                // Event listener per click sulla mappa
                this.map.on('click', (e) => {
                    this.handleMapClick(e);
                });
                
                // Carica piante disponibili
                await this.loadAvailablePlans();
                
                // Carica moduli di raccolta dati
                await this.loadAvailableModules();
                
                console.log('Archaeological map initialized successfully');
                
            } catch (error) {
                console.error('Error initializing map:', error);
            }
        },
        
        async loadAvailablePlans() {
            try {
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans`);
                if (response.ok) {
                    const data = await response.json();
                    this.availablePlans = data.plans;
                    
                    // Seleziona la pianta primaria se disponibile
                    const primaryPlan = this.availablePlans.find(p => p.is_primary);
                    if (primaryPlan) {
                        this.selectedPlanId = primaryPlan.id;
                        await this.switchPlan();
                    }
                }
            } catch (error) {
                console.error('Error loading plans:', error);
            }
        },
        
        async loadAvailableModules() {
            try {
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/data-collection-modules`);
                if (response.ok) {
                    this.availableModules = await response.json();
                }
            } catch (error) {
                console.error('Error loading modules:', error);
            }
        },
        
        // === GESTIONE PIANTE ===
        
        async switchPlan() {
            if (!this.selectedPlanId) {
                this.currentPlan = null;
                return;
            }
            
            try {
                // Carica dettagli pianta
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/${this.selectedPlanId}`);
                if (response.ok) {
                    this.currentPlan = await response.json();
                    
                    // Configura griglia
                    this.gridConfig = { ...this.gridConfig, ...this.currentPlan.grid_config };
                    
                    // Carica pianta come image overlay
                    await this.loadPlanImage();
                    
                    // Carica unità di scavo
                    await this.loadExcavationUnits();
                    
                    // Carica dati archeologici
                    await this.loadArchaeologicalData();
                    
                    // Crea griglia
                    this.createGridOverlay();
                }
            } catch (error) {
                console.error('Error switching plan:', error);
            }
        },
        
        async loadPlanImage() {
            if (!this.currentPlan) return;
            
            try {
                // Remove existing plan overlay
                this.map.eachLayer((layer) => {
                    if (layer instanceof L.ImageOverlay) {
                        this.map.removeLayer(layer);
                    }
                });
                
                // Add new plan overlay
                const imageUrl = `/api/archaeological-plans/sites/${siteId}/plans/${this.currentPlan.id}/image`;
                const bounds = [
                    [this.currentPlan.bounds.south || 0, this.currentPlan.bounds.west || 0],
                    [this.currentPlan.bounds.north || 1000, this.currentPlan.bounds.east || 1500]
                ];
                
                const planOverlay = L.imageOverlay(imageUrl, bounds, {
                    opacity: 0.9,
                    interactive: false
                }).addTo(this.map);
                
                // Fit map to plan bounds
                this.map.fitBounds(bounds);
                
            } catch (error) {
                console.error('Error loading plan image:', error);
            }
        },
        
        async uploadPlan() {
            this.isUploadingPlan = true;
            
            try {
                const formData = new FormData();
                const fileInput = this.$refs.planFileInput;
                
                if (!fileInput.files.length) {
                    alert('Seleziona un file');
                    return;
                }
                
                formData.append('plan_file', fileInput.files[0]);
                formData.append('name', this.newPlan.name);
                formData.append('description', this.newPlan.description);
                formData.append('plan_type', this.newPlan.plan_type);
                formData.append('origin_x', this.newPlan.origin_x);
                formData.append('origin_y', this.newPlan.origin_y);
                formData.append('drawing_scale', this.newPlan.drawing_scale);
                formData.append('surveyor', this.newPlan.surveyor);
                formData.append('is_primary', this.newPlan.is_primary);
                
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/upload`, {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const result = await response.json();
                    console.log('Plan uploaded:', result);
                    
                    // Ricarica piante
                    await this.loadAvailablePlans();
                    
                    // Seleziona la nuova pianta
                    this.selectedPlanId = result.plan_id;
                    await this.switchPlan();
                    
                    // Chiudi modal
                    this.showPlanUploadModal = false;
                    this.resetNewPlan();
                    
                } else {
                    const error = await response.json();
                    alert('Errore durante il caricamento: ' + error.detail);
                }
                
            } catch (error) {
                console.error('Error uploading plan:', error);
                alert('Errore durante il caricamento');
            } finally {
                this.isUploadingPlan = false;
            }
        },
        
        resetNewPlan() {
            this.newPlan = {
                name: '',
                description: '',
                plan_type: 'general',
                origin_x: 0.0,
                origin_y: 0.0,
                scale_factor: 1.0,
                drawing_scale: '',
                surveyor: '',
                is_primary: false
            };
        },
        
        async deletePlan() {
            if (!this.currentPlan) {
                alert('Nessuna pianta selezionata');
                return;
            }
            
            if (confirm(`Sei sicuro di voler eliminare la pianta "${this.currentPlan.name}"? Questa azione non può essere annullata.`)) {
                try {
                    const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/${this.currentPlan.id}`, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        console.log('Plan deleted:', this.currentPlan.id);
                        
                        // Reset current plan
                        this.currentPlan = null;
                        this.selectedPlanId = '';
                        
                        // Clear map
                        this.map.eachLayer((layer) => {
                            if (layer instanceof L.ImageOverlay) {
                                this.map.removeLayer(layer);
                            }
                        });
                        this.unitsLayer.clearLayers();
                        this.markersLayer.clearLayers();
                        this.gridLayer.clearLayers();
                        this.gridLabels.clearLayers();
                        
                        // Reload plans
                        await this.loadAvailablePlans();
                        
                        alert('Pianta eliminata con successo');
                    } else {
                        const error = await response.json();
                        alert('Errore durante l\'eliminazione: ' + error.detail);
                    }
                } catch (error) {
                    console.error('Error deleting plan:', error);
                    alert('Errore durante l\'eliminazione');
                }
            }
        },
        
        // === GESTIONE GRIGLIA ===
        
        createGridOverlay() {
            if (!this.currentPlan) return;
            
            // Clear existing grid
            this.gridLayer.clearLayers();
            this.gridLabels.clearLayers();
            
            const { unitSize, majorGridSize } = this.gridConfig;
            const bounds = this.currentPlan.bounds;
            const { north, south, east, west } = bounds;
            
            // Create grid lines
            this.createGridLines(unitSize, majorGridSize, north, south, east, west);
            
            // Add grid labels
            if (this.gridConfig.showLabels) {
                this.addGridLabels(majorGridSize, north, south, east, west);
            }
        },
        
        createGridLines(unitSize, majorGridSize, north, south, east, west) {
            // Vertical lines (east-west)
            for (let x = west; x <= east; x += unitSize) {
                const isMajor = x % majorGridSize === 0;
                
                if ((isMajor && this.gridConfig.showMajorGrid) || 
                    (!isMajor && this.gridConfig.showMinorGrid)) {
                    
                    const line = L.polyline([
                        [south, x],
                        [north, x]
                    ], {
                        color: isMajor ? '#2563eb' : '#94a3b8',
                        weight: isMajor ? 2 : 1,
                        opacity: isMajor ? 0.8 : 0.5,
                        className: `grid-line ${isMajor ? 'major' : 'minor'}`
                    }).addTo(this.gridLayer);
                    
                    if (isMajor) {
                        line.bindTooltip(`E ${x}m`, {
                            permanent: false,
                            direction: 'top'
                        });
                    }
                }
            }
            
            // Horizontal lines (nord-sud)
            for (let y = south; y <= north; y += unitSize) {
                const isMajor = y % majorGridSize === 0;
                
                if ((isMajor && this.gridConfig.showMajorGrid) || 
                    (!isMajor && this.gridConfig.showMinorGrid)) {
                    
                    const line = L.polyline([
                        [y, west],
                        [y, east]
                    ], {
                        color: isMajor ? '#2563eb' : '#94a3b8',
                        weight: isMajor ? 2 : 1,
                        opacity: isMajor ? 0.8 : 0.5,
                        className: `grid-line ${isMajor ? 'major' : 'minor'}`
                    }).addTo(this.gridLayer);
                    
                    if (isMajor) {
                        line.bindTooltip(`N ${y}m`, {
                            permanent: false,
                            direction: 'left'
                        });
                    }
                }
            }
        },
        
        addGridLabels(majorGridSize, north, south, east, west) {
            for (let x = west; x <= east; x += majorGridSize) {
                for (let y = south; y <= north; y += majorGridSize) {
                    const label = L.marker([y, x], {
                        icon: L.divIcon({
                            html: `<div class="grid-label">${this.formatGridCoordinate(x, y)}</div>`,
                            className: 'grid-coordinate-label',
                            iconSize: [60, 20],
                            iconAnchor: [30, 10]
                        })
                    }).addTo(this.gridLabels);
                }
            }
        },
        
        formatGridCoordinate(x, y) {
            const { majorGridSize } = this.gridConfig;
            const gridX = Math.floor(x / majorGridSize);
            const gridY = Math.floor(y / majorGridSize);
            const letter = String.fromCharCode(65 + (gridY + 5)); // A, B, C...
            return `${letter}${gridX + 5}`;
        },
        
        updateGridVisibility() {
            this.createGridOverlay();
        },
        
        // === GESTIONE UNITÀ DI SCAVO ===
        
        async loadExcavationUnits() {
            if (!this.currentPlan) return;
            
            try {
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/${this.currentPlan.id}/excavation-units`);
                if (response.ok) {
                    const data = await response.json();
                    this.excavationUnits = data.excavation_units;
                    this.drawExcavationUnits();
                }
            } catch (error) {
                console.error('Error loading excavation units:', error);
            }
        },
        
        drawExcavationUnits() {
            this.unitsLayer.clearLayers();
            
            this.excavationUnits.forEach(unit => {
                this.drawUnitOnMap(unit);
            });
        },
        
        drawUnitOnMap(unit) {
            const { x, y } = unit.coordinates;
            const { x: sizeX, y: sizeY } = unit.size;
            
            // Rettangolo unità di scavo
            const bounds = [
                [y, x],
                [y + sizeY, x + sizeX]
            ];
            
            const rectangle = L.rectangle(bounds, {
                color: unit.status_color,
                weight: 2,
                fillOpacity: 0.3,
                className: `excavation-unit status-${unit.status}`
            }).addTo(this.unitsLayer);
            
            // Etichetta unità
            const center = rectangle.getBounds().getCenter();
            const label = L.marker(center, {
                icon: L.divIcon({
                    html: `<div class="unit-label">${unit.id}</div>`,
                    className: 'excavation-unit-label',
                    iconSize: [40, 16],
                    iconAnchor: [20, 8]
                })
            }).addTo(this.unitsLayer);
            
            // Popup informativo
            const popupContent = this.createUnitPopupContent(unit);
            rectangle.bindPopup(popupContent);
        },
        
        createUnitPopupContent(unit) {
            return `
                <div class="excavation-popup">
                    <h4 class="font-semibold">${unit.id}</h4>
                    <div class="text-sm text-gray-600">
                        <p><strong>Coordinate:</strong> ${unit.coordinates.x}E, ${unit.coordinates.y}N</p>
                        <p><strong>Dimensione:</strong> ${unit.size.x}x${unit.size.y}m</p>
                        <p><strong>Stato:</strong> ${unit.status_display}</p>
                        ${unit.supervisor ? `<p><strong>Responsabile:</strong> ${unit.supervisor}</p>` : ''}
                        ${unit.notes ? `<p><strong>Note:</strong> ${unit.notes}</p>` : ''}
                    </div>
                    <div class="mt-2 flex space-x-2">
                        <button onclick="Alpine.store('gridManager').editUnit('${unit.id}')" 
                                class="text-xs bg-blue-500 text-white px-2 py-1 rounded">
                            Modifica
                        </button>
                        <button onclick="Alpine.store('gridManager').viewUnitData('${unit.id}')" 
                                class="text-xs bg-green-500 text-white px-2 py-1 rounded">
                            Dati Scavo
                        </button>
                    </div>
                </div>
            `;
        },
        
        async createExcavationUnit() {
            try {
                const unitData = {
                    id: this.newUnit.id,
                    coordinates_x: this.newUnit.coordinates_x,
                    coordinates_y: this.newUnit.coordinates_y,
                    size_x: parseFloat(this.newUnit.size_x),
                    size_y: parseFloat(this.newUnit.size_y),
                    status: this.newUnit.status,
                    supervisor: this.newUnit.supervisor,
                    notes: this.newUnit.notes
                };
                
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/${this.currentPlan.id}/excavation-units`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(unitData)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    console.log('Excavation unit created:', result);
                    
                    // Ricarica unità
                    await this.loadExcavationUnits();
                    
                    // Chiudi modal
                    this.showUnitModal = false;
                    this.resetNewUnit();
                    
                } else {
                    const error = await response.json();
                    alert('Errore durante la creazione: ' + error.detail);
                }
                
            } catch (error) {
                console.error('Error creating excavation unit:', error);
                alert('Errore durante la creazione');
            }
        },
        
        // === GESTIONE DATI ARCHEOLOGICI ===
        
        async loadArchaeologicalData() {
            if (!this.currentPlan) return;
            
            try {
                const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/${this.currentPlan.id}/archaeological-data`);
                if (response.ok) {
                    const data = await response.json();
                    this.archaeologicalData = data.archaeological_data;
                    this.drawArchaeologicalData();
                }
            } catch (error) {
                console.error('Error loading archaeological data:', error);
            }
        },
        
        drawArchaeologicalData() {
            this.markersLayer.clearLayers();
            
            this.archaeologicalData.forEach(dataPoint => {
                this.addMarkerToMap(dataPoint);
            });
        },
        
        addMarkerToMap(dataPoint) {
            // Icone personalizzate per tipo di dato
            const iconMap = {
                'ceramic': '🏺',
                'structure': '🏛️',
                'stratigraphy': '📐',
                'sample': '🧪',
                'find': '💎',
                'default': '📍'
            };
            
            const icon = iconMap[dataPoint.module_category] || iconMap.default;
            
            const customIcon = L.divIcon({
                html: `<div class="marker-icon">${icon}</div>`,
                className: 'custom-archaeological-marker',
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            });
            
            const marker = L.marker([dataPoint.coordinates.y, dataPoint.coordinates.x], {
                icon: customIcon
            }).addTo(this.markersLayer);
            
            // Popup con dati raccolti
            const popupContent = this.createDataPopupContent(dataPoint);
            marker.bindPopup(popupContent);
        },
        
        createDataPopupContent(dataPoint) {
            return `
                <div class="data-popup">
                    <h4 class="font-semibold">${dataPoint.module_name}</h4>
                    <div class="text-sm text-gray-600">
                        <p><strong>Coordinate:</strong> ${dataPoint.coordinates.x}E, ${dataPoint.coordinates.y}N</p>
                        <p><strong>Rilevatore:</strong> ${dataPoint.collector_name}</p>
                        <p><strong>Data:</strong> ${new Date(dataPoint.collection_date).toLocaleDateString()}</p>
                        ${dataPoint.is_validated ? '<p class="text-green-600">✓ Validato</p>' : '<p class="text-orange-600">⏳ In attesa di validazione</p>'}
                    </div>
                </div>
            `;
        },
        
        // === EVENT HANDLERS ===
        
        handleMapClick(e) {
            const latlng = e.latlng;
            
            if (this.isDataCollectionMode) {
                this.addDataPoint(latlng);
            } else if (this.isGridMode) {
                this.addExcavationUnit(latlng);
            }
        },
        
        async addDataPoint(latlng) {
            this.currentCoordinates = latlng;
            this.showModuleSelector = true;
        },
        
        addExcavationUnit(latlng) {
            const gridCoord = this.snapToGrid(latlng);
            const unitId = this.generateUnitId(gridCoord);
            
            // Verifica se l'unità esiste già
            if (this.excavationUnits.find(u => u.id === unitId)) {
                alert('Unità di scavo già presente in questa posizione');
                return;
            }
            
            this.showUnitCreationModal(gridCoord, unitId);
        },
        
        snapToGrid(latlng) {
            const { unitSize } = this.gridConfig;
            const origin = this.currentPlan || { origin_x: 0, origin_y: 0 };
            
            // Snap alle coordinate griglia
            const snappedX = Math.round((latlng.lng - origin.origin_x) / unitSize) * unitSize + origin.origin_x;
            const snappedY = Math.round((latlng.lat - origin.origin_y) / unitSize) * unitSize + origin.origin_y;
            
            return { x: snappedX, y: snappedY };
        },
        
        generateUnitId(gridCoord) {
            const { x, y } = gridCoord;
            const { majorGridSize } = this.gridConfig;
            
            // Sistema standard archeologico
            const majorX = Math.floor(x / majorGridSize);
            const majorY = Math.floor(y / majorGridSize);
            const minorX = Math.abs(x % majorGridSize) / this.gridConfig.unitSize;
            const minorY = Math.abs(y % majorGridSize) / this.gridConfig.unitSize;
            
            const letter = String.fromCharCode(65 + (majorY + 5));
            return `${letter}${majorX + 5}-${minorX}${minorY}`;
        },
        
        showUnitCreationModal(gridCoord, unitId) {
            this.newUnit = {
                id: unitId,
                coordinates_x: gridCoord.x,
                coordinates_y: gridCoord.y,
                size_x: 5,
                size_y: 5,
                status: 'planned',
                supervisor: '',
                notes: ''
            };
            this.showUnitModal = true;
        },
        
        // === MODALITÀ OPERATIVE ===
        
        toggleDataCollection() {
            this.isDataCollectionMode = !this.isDataCollectionMode;
            if (this.isDataCollectionMode) {
                this.isGridMode = false;
            }
            this.updateMapCursor();
        },
        
        toggleGridMode() {
            this.isGridMode = !this.isGridMode;
            if (this.isGridMode) {
                this.isDataCollectionMode = false;
            }
            this.updateMapCursor();
        },
        
        updateMapCursor() {
            const container = this.map.getContainer();
            if (this.isDataCollectionMode || this.isGridMode) {
                container.style.cursor = 'crosshair';
            } else {
                container.style.cursor = '';
            }
        },
        
        // === UTILITY ===
        
        selectModule(module) {
            this.selectedModule = module;
            this.showModuleSelector = false;
            // TODO: Implementare form di raccolta dati
            console.log('Selected module:', module);
        },
        
        cancelUnitCreation() {
            this.showUnitModal = false;
            this.resetNewUnit();
        },
        
        resetNewUnit() {
            this.newUnit = {
                id: '',
                coordinates_x: 0,
                coordinates_y: 0,
                size_x: 5,
                size_y: 5,
                status: 'planned',
                supervisor: '',
                notes: ''
            };
        },
        
        getStatusClass(status) {
            const classes = {
                'planned': 'bg-gray-100 text-gray-800',
                'in_progress': 'bg-orange-100 text-orange-800',
                'completed': 'bg-green-100 text-green-800',
                'suspended': 'bg-red-100 text-red-800'
            };
            return classes[status] || classes.planned;
        },
        
        editUnit(unit) {
            console.log('Edit unit:', unit);
            // TODO: Implementare modifica unità
        },
        
        viewUnitData(unit) {
            console.log('View unit data:', unit);
            // TODO: Implementare visualizzazione dati unità
        },
        
        async removeUnit(unitId) {
            if (confirm('Sei sicuro di voler eliminare questa unità di scavo?')) {
                try {
                    const response = await fetch(`/api/archaeological-plans/sites/${siteId}/plans/${this.currentPlan.id}/excavation-units/${unitId}`, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        console.log('Unit deleted:', unitId);
                        // Ricarica unità
                        await this.loadExcavationUnits();
                    } else {
                        const error = await response.json();
                        alert('Errore durante l\'eliminazione: ' + error.detail);
                    }
                } catch (error) {
                    console.error('Error deleting unit:', error);
                    alert('Errore durante l\'eliminazione');
                }
            }
        },
        
        exportData() {
            console.log('Export data');
            // TODO: Implementare esportazione dati
        }
    }));
});

// Global site ID (to be set by template)
let siteId;