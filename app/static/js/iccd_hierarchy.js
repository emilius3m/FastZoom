/**
 * Sistema Gerarchico ICCD - Component Alpine.js
 * Gestione completa della gerarchia dal generale al particolare
 */

function iccdHierarchicalSystem() {
    return {
        // Stato del sistema
        currentLevel: 'site', // site -> complex -> monument -> artifact
        selectedRecord: null,
        hierarchyTree: {
            organized: {
                level1: { SI: null },
                level2: { CA: [], MA: [], SAS: [] },
                level3: { RA: [], NU: [], TMA: [], AT: [] }
            }
        },

        // Workflow ICCD
        iccdWorkflow: {
            'SI': { level: 1, name: 'Sito Archeologico', children: ['CA', 'SAS', 'MA'] },
            'CA': { level: 2, name: 'Complesso Archeologico', children: ['MA', 'RA', 'TMA'] },
            'MA': { level: 2, name: 'Monumento Archeologico', children: ['RA', 'NU', 'TMA', 'AT'] },
            'SAS': { level: 2, name: 'Saggio Stratigrafico', children: ['RA', 'NU', 'TMA', 'AT'] },
            'RA': { level: 3, name: 'Reperto Archeologico', children: [] },
            'NU': { level: 3, name: 'Bene Numismatico', children: [] },
            'TMA': { level: 3, name: 'Tabella Materiali', children: [] },
            'AT': { level: 3, name: 'Antropologia Fisica', children: [] }
        },

        // Authority files
        authorityFiles: {
            excavations: [], // DSC
            surveys: [],     // RCG
            bibliography: [], // BIB
            authors: []      // AUT
        },

        // Moduli speciali
        activeModules: [],

        // UI State
        loading: false,
        showAlert: false,
        alertMessage: '',
        alertType: 'info',
        breadcrumb: [],

        async init() {
            this.loading = true;
            try {
                await this.loadSiteHierarchy();
                await this.loadAuthorityFiles();
                this.initializeWorkflow();
            } catch (error) {
                console.error('Errore inizializzazione sistema ICCD:', error);
                this.showAlertMessage('Errore inizializzazione sistema ICCD', 'error');
            } finally {
                this.loading = false;
            }
        },

        async loadSiteHierarchy() {
            try {
                const response = await fetch(`/api/v1/iccd/site/${window.siteId}/hierarchy/tree`);
                if (response.ok) {
                    this.hierarchyTree = await response.json();
                    this.buildHierarchicalView();
                } else {
                    throw new Error('Errore caricamento gerarchia');
                }
            } catch (error) {
                console.error('Errore caricamento gerarchia:', error);
                throw error;
            }
        },

        buildHierarchicalView() {
            // Costruisce la vista ad albero gerarchico
            const siteRecord = this.hierarchyTree.site;

            if (siteRecord) {
                // Organizza secondo schemas ICCD
                this.organizeByICCDLevel(this.hierarchyTree);
            }
        },

        organizeByICCDLevel(tree) {
            const organized = {
                level1: { // CONTENITORE TERRITORIALE
                    SI: tree.site || null
                },
                level2: { // BENI IMMOBILI
                    CA: tree.complexes || [],
                    MA: tree.monuments || [],
                    SAS: tree.stratigraphic_surveys || []
                },
                level3: { // BENI MOBILI
                    RA: tree.artifacts || [],
                    NU: tree.numismatics || [],
                    TMA: tree.material_tables || [],
                    AT: tree.anthropology || []
                }
            };

            this.hierarchyTree.organized = organized;
        },

        async createICCDRecord(schemaType, parentId = null) {
            // For SI records, redirect to the form instead of creating directly
            if (schemaType === 'SI') {
                window.location.href = `/sites/${window.siteId}/iccd/new/SI`;
                return;
            }

            // For other schemas types, check if SI exists first
            if (!this.hierarchyTree.organized?.level1?.SI && schemaType !== 'SI') {
                this.showAlertMessage('È necessario creare prima la Scheda SI (Sito Archeologico)', 'warning');
                return;
            }

            const recordData = this.initializeSchemaData(schemaType);

            // Assegna gerarchia
            if (parentId) {
                recordData.parent_id = parentId;
            }

            try {
                const response = await fetch(`/api/v1/iccd/site/${window.siteId}/records`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    },
                    body: JSON.stringify({
                        schema_type: schemaType,
                        parent_id: parentId,
                        site_id: window.siteId,
                        data: recordData
                    })
                });

                if (response.ok) {
                    const result = await response.json();
                    await this.loadSiteHierarchy(); // Ricarica gerarchia
                    this.showAlertMessage(`Scheda ${schemaType} creata: ${result.nct}`, 'success');
                } else {
                    const error = await response.json();
                    throw new Error(error.detail || 'Errore creazione scheda');
                }
            } catch (error) {
                console.error('Errore creazione scheda:', error);
                this.showAlertMessage(error.message || 'Errore creazione scheda', 'error');
            }
        },

        initializeSchemaData(schemaType) {
            const baseData = {
                CD: {
                    TSK: schemaType,
                    LIR: 'C',
                    NCT: {
                        NCTR: '12',
                        NCTN: this.generateNCTNumber(),
                        NCTS: ''
                    },
                    ESC: 'SSABAP-RM'
                }
            };

            // Aggiungi sezioni specifiche per tipo
            switch (schemaType) {
                case 'SI':
                    return this.initializeSiteSchema(baseData);
                case 'CA':
                    return this.initializeComplexSchema(baseData);
                case 'MA':
                    return this.initializeMonumentSchema(baseData);
                case 'RA':
                    return this.initializeArtifactSchema(baseData);
                case 'NU':
                    return this.initializeNumismaticSchema(baseData);
                case 'TMA':
                    return this.initializeMaterialTableSchema(baseData);
                case 'AT':
                    return this.initializeAnthropologySchema(baseData);
                case 'SAS':
                    return this.initializeStratigraphicSchema(baseData);
                default:
                    return baseData;
            }
        },

        initializeSiteSchema(baseData) {
            return {
                ...baseData,
                LC: {
                    PVC: {
                        PVCS: 'Italia',
                        PVCR: 'Lazio',
                        PVCP: 'RM',
                        PVCC: 'Roma'
                    },
                    PVL: {
                        PVLN: 'Domus Flavia'
                    }
                },
                OG: {
                    OGT: {
                        OGTD: 'area archeologica'
                    }
                }
            };
        },

        initializeComplexSchema(baseData) {
            return {
                ...baseData,
                LC: {
                    PVC: {
                        PVCS: 'Italia',
                        PVCR: 'Lazio',
                        PVCP: 'RM',
                        PVCC: 'Roma'
                    },
                    PVL: {
                        PVLN: 'Domus Flavia - Complesso'
                    }
                },
                OG: {
                    OGT: {
                        OGTD: 'complesso archeologico'
                    }
                }
            };
        },

        initializeMonumentSchema(baseData) {
            return {
                ...baseData,
                LC: {
                    PVC: {
                        PVCS: 'Italia',
                        PVCR: 'Lazio',
                        PVCP: 'RM',
                        PVCC: 'Roma'
                    },
                    PVL: {
                        PVLN: 'Domus Flavia - Monumento'
                    }
                },
                OG: {
                    OGT: {
                        OGTD: 'monumento archeologico'
                    }
                }
            };
        },

        initializeArtifactSchema(baseData) {
            return {
                ...baseData,
                LC: {
                    PVC: {
                        PVCS: 'Italia',
                        PVCR: 'Lazio',
                        PVCP: 'RM',
                        PVCC: 'Roma'
                    },
                    PVL: {
                        PVLN: 'Domus Flavia'
                    }
                },
                OG: {
                    OGT: {
                        OGTD: 'reperto archeologico'
                    }
                }
            };
        },

        initializeNumismaticSchema(baseData) {
            return {
                ...baseData,
                OG: {
                    OGT: {
                        OGTD: 'moneta'
                    }
                }
            };
        },

        initializeMaterialTableSchema(baseData) {
            return {
                ...baseData,
                OG: {
                    OGT: {
                        OGTD: 'lotto materiali'
                    }
                }
            };
        },

        initializeAnthropologySchema(baseData) {
            return {
                ...baseData,
                OG: {
                    OGT: {
                        OGTD: 'resto umano'
                    }
                }
            };
        },

        initializeStratigraphicSchema(baseData) {
            return {
                ...baseData,
                OG: {
                    OGT: {
                        OGTD: 'saggio stratigrafico'
                    }
                }
            };
        },

        async createRelation(sourceId, targetId, relationType, level = '1') {
            try {
                const response = await fetch(`/api/v1/iccd/site/${window.siteId}/relations`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    },
                    body: JSON.stringify({
                        source_record_id: sourceId,
                        target_record_id: targetId,
                        relation_type: relationType,
                        relation_level: level
                    })
                });

                if (response.ok) {
                    await this.loadSiteHierarchy();
                    this.showAlertMessage('Relazione creata con successo', 'success');
                } else {
                    const error = await response.json();
                    throw new Error(error.detail || 'Errore creazione relazione');
                }
            } catch (error) {
                console.error('Errore creazione relazione:', error);
                this.showAlertMessage(error.message || 'Errore creazione relazione', 'error');
            }
        },

        async loadAuthorityFiles() {
            try {
                const response = await fetch(`/api/v1/iccd/site/${window.siteId}/authority-files`);
                if (response.ok) {
                    this.authorityFiles = await response.json();
                } else {
                    throw new Error('Errore caricamento authority files');
                }
            } catch (error) {
                console.error('Errore caricamento authority files:', error);
                // Non bloccare l'inizializzazione per questo errore
            }
        },

        async createAuthorityFile(type, data) {
            try {
                const response = await fetch(`/api/v1/iccd/site/${window.siteId}/authority-files`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    },
                    body: JSON.stringify({
                        authority_type: type,
                        site_id: window.siteId,
                        name: data.name || `${type} - ${new Date().getFullYear()}`,
                        description: data.description || '',
                        data: data.data || {}
                    })
                });

                if (response.ok) {
                    await this.loadAuthorityFiles();
                    this.showAlertMessage(`Authority File ${type} creato`, 'success');
                } else {
                    const error = await response.json();
                    throw new Error(error.detail || 'Errore creazione authority file');
                }
            } catch (error) {
                console.error('Errore creazione authority file:', error);
                this.showAlertMessage(error.message || 'Errore creazione authority file', 'error');
            }
        },

        generateNCTNumber() {
            const now = new Date();
            const year = now.getFullYear().toString().slice(-2);
            const timestamp = now.getTime().toString().slice(-6);
            return year + timestamp;
        },

        // Navigazione gerarchica
        navigateToLevel(level, record = null) {
            if (level === 'detail' && record) {
                // Redirect to the view page for the record
                window.location.href = `/sites/${window.siteId}/iccd/${record.id}`;
                return;
            }

            this.currentLevel = level;
            this.selectedRecord = record;
            this.updateBreadcrumb();
        },

        updateBreadcrumb() {
            const breadcrumb = [];

            if (this.selectedRecord) {
                // Costruisce breadcrumb dalla gerarchia
                let current = this.selectedRecord;
                while (current) {
                    breadcrumb.unshift({
                        name: current.iccd_data?.OG?.OGT?.OGTD || current.schema_type,
                        record: current
                    });
                    current = current.parent;
                }
            }

            this.breadcrumb = breadcrumb;
        },

        // Sistema di notifiche
        showAlertMessage(message, type = 'info') {
            this.alertMessage = message;
            this.alertType = type;
            this.showAlert = true;

            // Auto-hide dopo 5 secondi
            setTimeout(() => {
                this.showAlert = false;
            }, 5000);
        },

        hideAlert() {
            this.showAlert = false;
        },

        // Utility
        getSchemaIcon(schemaType) {
            const icons = {
                'SI': '🌍',
                'CA': '🏛️',
                'MA': '🏛️',
                'SAS': '📐',
                'RA': '🏺',
                'NU': '💰',
                'TMA': '📊',
                'AT': '🦴'
            };
            return icons[schemaType] || '📋';
        },

        getSchemaName(schemaType) {
            return this.iccdWorkflow[schemaType]?.name || schemaType;
        },

        initializeWorkflow() {
            // Inizializzazione workflow specifiche se necessarie
            console.log('Sistema Gerarchico ICCD inizializzato');
        }
    };
}

// Export per uso globale
window.iccdHierarchicalSystem = iccdHierarchicalSystem;