// Initialize Alpine store for shared data BEFORE component definitions
document.addEventListener("alpine:init", () => {
    Alpine.store('unifiedDashboard', {
        activeTab: 'overview',
        sitesData: [],
        activities: [],
        giornaleSites: [],
        giornaleSiteStats: {},
        loading: {
            global: false,
            sites: false,
            giornaleSites: false,
            activities: false,
            moreActivities: false
        },
        overviewStats: {
            sites_count: 0,
            photos_count: 0,
            documents_count: 0,
            users_count: 0
        },
        giornaleStats: {
            siti_totali: 0,
            giornali_totali: 0,
            giornali_validati: 0,
            giornali_pendenti: 0
        },
        systemStatus: {
            database: {
                status: 'online',
                text: 'Online',
                class: 'text-green-600 dark:text-green-400',
                icon: 'fa-check-circle'
            },
            storage: {
                status: 'operational',
                text: 'Operativo',
                class: 'text-green-600 dark:text-green-400',
                icon: 'fa-check-circle'
            },
            backup: {
                status: 'recent',
                text: 'Recente',
                class: 'text-green-600 dark:text-green-400',
                icon: 'fa-check-circle'
            }
        },
        error: null,
        
        // Store methods
        setError(error) {
            this.error = error;
            console.error('Dashboard error:', error);
        },
        
        clearError() {
            this.error = null;
        },
        
        updateData(key, value) {
            this[key] = value;
        }
    });
});

document.addEventListener("alpine:init", () => {
    // Main Unified Dashboard Component
    Alpine.data("unifiedDashboard", () => ({
        activeTab: 'overview',
        loading: {
            global: false,
            sites: false,
            giornaleSites: false,
            activities: false,
            moreActivities: false
        },
        
        // Data storage
        sitesData: [],
        giornaleSites: [],
        overviewStats: {
            sites_count: 0,
            photos_count: 0,
            documents_count: 0,
            users_count: 0
        },
        giornaleStats: {
            siti_totali: 0,
            giornali_totali: 0,
            giornali_validati: 0,
            giornali_pendenti: 0
        },
        giornaleSiteStats: {},
        activities: [],
        recentActivities: [],
        activityFilter: 'all',
        hasMoreActivities: false,
        systemStatus: {
            database: {
                status: 'online',
                text: 'Online',
                class: 'text-green-600 dark:text-green-400',
                icon: 'fa-check-circle'
            },
            storage: {
                status: 'operational',
                text: 'Operativo',
                class: 'text-green-600 dark:text-green-400',
                icon: 'fa-check-circle'
            },
            backup: {
                status: 'recent',
                text: 'Recente',
                class: 'text-green-600 dark:text-green-400',
                icon: 'fa-check-circle'
            }
        },
        
        // Error handling
        error: null,
        retryCount: {
            sites: 0,
            activities: 0,
            documents: 0,
            giornale: 0,
            system: 0
        },
        maxRetries: 3,
        
        // Activity filters
        activityFilters: [
            { value: 'all', label: 'Tutto' },
            { value: 'sites', label: 'Siti' },
            { value: 'giornale', label: 'Giornale' },
            { value: 'documents', label: 'Documenti' },
            { value: 'photos', label: 'Fotografie' },
            { value: 'users', label: 'Utenti' }
        ],
        
        // Tab management
        tabs: ['overview', 'giornale', 'analytics'],
        
        // Initialize
        async init() {
            try {
                await this.loadInitialData();
                this.setupTabPersistence();
                this.setupKeyboardNavigation();
            } catch (error) {
                this.handleError(error, 'initialization');
            }
        },
        
        // Load initial data
        async loadInitialData() {
            this.loading.global = true;
            this.clearError();
            
            try {
                // Load data for all tabs in parallel
                await Promise.all([
                    this.loadOverviewData(),
                    this.loadGiornaleData(),
                    this.loadActivities(),
                    this.loadSystemStatus()
                ]);
            } catch (error) {
                this.handleError(error, 'initial_data_load');
                throw error; // Re-throw to handle in init()
            } finally {
                this.loading.global = false;
            }
        },
        
        // Tab switching
        switchTab(tabName) {
            if (!this.tabs.includes(tabName)) return;
            
            this.activeTab = tabName;
            this.persistTab(tabName);
            
            // Hide all tab contents
            document.querySelectorAll('.unified-tab-content').forEach(content => {
                content.classList.remove('active');
            });
            
            // Show selected tab content
            const selectedContent = document.getElementById(`${tabName}-content`);
            if (selectedContent) {
                selectedContent.classList.add('active');
            }
            
            // Load tab-specific data if needed
            this.loadTabSpecificData(tabName);
        },
        
        // Load tab-specific data
        async loadTabSpecificData(tabName) {
            switch(tabName) {
                case 'overview':
                    await this.refreshOverviewData();
                    break;
                case 'giornale':
                    await this.refreshGiornaleData();
                    break;
                case 'analytics':
                    await this.loadAnalyticsData();
                    break;
            }
        },
        
        // Overview data loading
        async loadOverviewData() {
            this.loading.sites = true;
            this.clearError();
            
            try {
                // Load sites data with retry mechanism
                const sitesResponse = await this.apiCallWithRetry(
                    '/api/unified/sites/list',
                    {
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        }
                    },
                    'sites'
                );
                
                if (sitesResponse) {
                    const sitesData = await sitesResponse.json();
                    this.sitesData = sitesData.sites || [];
                    this.overviewStats.sites_count = this.sitesData.length;
                    // Update store data
                    Alpine.store('unifiedDashboard').updateData('sitesData', this.sitesData);
                }
                
                // Load overview statistics
                await this.loadOverviewStats();
                
            } catch (error) {
                this.handleError(error, 'overview_data_load');
            } finally {
                this.loading.sites = false;
            }
        },
        
        async loadOverviewStats() {
            try {
                // Get stats from the page context if available
                const sitesCount = this.sitesData.length;
                const photosCount = document.querySelector('[data-photos-count]')?.dataset.photosCount || 0;
                const usersCount = document.querySelector('[data-users-count]')?.dataset.usersCount || 0;
                
                this.overviewStats = {
                    sites_count: sitesCount,
                    photos_count: parseInt(photosCount),
                    documents_count: 0, // Will be loaded from API
                    users_count: parseInt(usersCount)
                };
                
                // Load documents count with retry mechanism
                const docsResponse = await this.apiCallWithRetry(
                    '/api/unified/documents/count',
                    {
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        }
                    },
                    'documents'
                );
                
                if (docsResponse) {
                    const docsData = await docsResponse.json();
                    this.overviewStats.documents_count = docsData.count || 0;
                }
                
            } catch (error) {
                this.handleError(error, 'overview_stats_load');
            }
        },
        
        async refreshOverviewData() {
            await this.loadOverviewData();
            await this.loadActivities();
        },
        
        // Giornale data loading
        async loadGiornaleData() {
            this.loading.giornaleSites = true;
            
            try {
                // Load giornale statistics with retry mechanism
                const statsResponse = await this.apiCallWithRetry(
                    '/api/giornale-cantiere/stats/general',
                    {
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        }
                    },
                    'giornale'
                );
                
                if (statsResponse) {
                    this.giornaleStats = await statsResponse.json();
                }
                
                // Load sites for giornale
                this.giornaleSites = [...this.sitesData];
                
                // Load site-specific giornale stats
                await this.loadGiornaleSiteStats();
                
            } catch (error) {
                this.handleError(error, 'giornale_data_load');
            } finally {
                this.loading.giornaleSites = false;
            }
        },
        
        async loadGiornaleSiteStats() {
            try {
                for (const site of this.giornaleSites) {
                    try {
                        const response = await this.apiCall(
                            `/api/giornale-cantiere/stats/site/${site.id}`,
                            {
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': this.getCSRFToken()
                                }
                            }
                        );
                        
                        if (response && response.ok) {
                            const siteData = await response.json();
                            this.giornaleSiteStats[site.id] = {
                                total: siteData.total_giornali || 0,
                                validated: siteData.validated_giornali || 0
                            };
                        }
                    } catch (error) {
                        console.warn(`Failed to load stats for site ${site.id}:`, error);
                        // Continue with other sites even if one fails
                    }
                }
            } catch (error) {
                this.handleError(error, 'giornale_site_stats_load');
            }
        },
        
        async refreshGiornaleData() {
            await this.loadGiornaleData();
        },
        
        // Analytics data loading
        async loadAnalyticsData() {
            // Analytics data loading will be implemented as needed
            console.log('Loading analytics data...');
        },
        
        // Activities management
        async loadActivities() {
            this.loading.activities = true;
            
            try {
                const response = await this.apiCallWithRetry(
                    '/api/unified/activities/recent',
                    {
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        }
                    },
                    'activities'
                );
                
                if (response) {
                    const data = await response.json();
                    this.activities = data.activities || [];
                    this.recentActivities = this.activities.slice(0, 5);
                    this.hasMoreActivities = data.has_more || false;
                    // Update store data
                    Alpine.store('unifiedDashboard').updateData('activities', this.activities);
                } else {
                    // Mock activities for demo
                    this.activities = this.getMockActivities();
                    this.recentActivities = this.activities.slice(0, 5);
                }
            } catch (error) {
                this.handleError(error, 'activities_load');
                // Use mock data as fallback
                this.activities = this.getMockActivities();
                this.recentActivities = this.activities.slice(0, 5);
            } finally {
                this.loading.activities = false;
            }
        },

        // System status loading
        async loadSystemStatus() {
            try {
                const response = await this.apiCallWithRetry(
                    '/api/unified/system/status',
                    {
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        }
                    },
                    'system'
                );
                
                if (response) {
                    const statusData = await response.json();
                    this.systemStatus = statusData;
                    // Update store data
                    Alpine.store('unifiedDashboard').updateData('systemStatus', this.systemStatus);
                }
            } catch (error) {
                console.warn('Failed to load system status:', error);
                // Use default values if API fails
                this.systemStatus = {
                    database: {
                        status: 'unknown',
                        text: 'Sconosciuto',
                        class: 'text-gray-600 dark:text-gray-400',
                        icon: 'fa-question-circle'
                    },
                    storage: {
                        status: 'unknown',
                        text: 'Sconosciuto',
                        class: 'text-gray-600 dark:text-gray-400',
                        icon: 'fa-question-circle'
                    },
                    backup: {
                        status: 'unknown',
                        text: 'Sconosciuto',
                        class: 'text-gray-600 dark:text-gray-400',
                        icon: 'fa-question-circle'
                    }
                };
            }
        },

        async refreshSystemStatus() {
            await this.loadSystemStatus();
        },
        
        async refreshActivities() {
            await this.loadActivities();
        },
        
        async loadMoreActivities() {
            this.loading.moreActivities = true;
            
            try {
                // Implementation for loading more activities
                // This would typically include pagination parameters
                console.log('Loading more activities...');
                
                // Simulate loading delay
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                // Update hasMoreActivities flag
                this.hasMoreActivities = false;
                
            } catch (error) {
                console.error('Error loading more activities:', error);
            } finally {
                this.loading.moreActivities = false;
            }
        },
        
        // Activity filtering
        get filteredActivities() {
            if (this.activityFilter === 'all') {
                return this.activities;
            }
            return this.activities.filter(activity => activity.type === this.activityFilter);
        },
        
        setActivityFilter(filter) {
            this.activityFilter = filter;
        },
        
        // Navigation methods
        navigateToSite(siteId) {
            window.location.href = `/view/${siteId}/dashboard/`;
        },
        
        navigateToGiornaleSite(siteId) {
            window.location.href = `/giornale-cantiere/site/${siteId}`;
        },
        
        navigateToNewSite() {
            window.location.href = '/sites/create';
        },
        
        navigateToNewGiornale() {
            // Navigate to first available site for giornale creation
            if (this.giornaleSites.length > 0) {
                window.location.href = `/giornale-cantiere/site/${this.giornaleSites[0].id}`;
            } else {
                this.showError('Nessun sito disponibile per creare un giornale');
            }
        },
        
        navigateToUpload() {
            // Navigate to first available site for upload
            if (this.sitesData.length > 0) {
                window.location.href = `/view/${this.sitesData[0].id}/photos/`;
            } else {
                this.showError('Nessun sito disponibile per caricare documenti');
            }
        },
        
        navigateToSitesList() {
            window.location.href = '/sites';
        },
        
        navigateToDocuments() {
            if (this.sitesData.length > 0) {
                window.location.href = `/view/${this.sitesData[0].id}/documentation/`;
            } else {
                this.showError('Nessun sito disponibile');
            }
        },
        
        navigateToGiornaleOperators() {
            window.location.href = '/giornale-cantiere/operatori';
        },
        
        navigateToGiornaleReports() {
            window.location.href = '/giornale-cantiere/reports';
        },
        
        // Analytics methods
        generateReport(type) {
            console.log(`Generating ${type} report...`);
            // Implementation for report generation
        },
        
        exportAnalytics() {
            console.log('Exporting analytics data...');
            // Implementation for data export
        },
        
        // Utility methods
        formatNumber(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'K';
            }
            return num.toString();
        },
        
        formatTime(timestamp) {
            const date = new Date(timestamp);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);
            
            if (diffMins < 1) return 'Proprio ora';
            if (diffMins < 60) return `${diffMins} min fa`;
            if (diffHours < 24) return `${diffHours} ore fa`;
            if (diffDays < 7) return `${diffDays} giorni fa`;
            
            return date.toLocaleDateString('it-IT');
        },
        
        getTabLabel(tab) {
            const labels = {
                'overview': 'Panoramica',
                'giornale': 'Giornale di Cantiere',
                'analytics': 'Analisi'
            };
            return labels[tab] || tab;
        },
        
        getPreviousTab() {
            const currentIndex = this.tabs.indexOf(this.activeTab);
            const prevIndex = currentIndex > 0 ? currentIndex - 1 : this.tabs.length - 1;
            return this.tabs[prevIndex];
        },
        
        getNextTab() {
            const currentIndex = this.tabs.indexOf(this.activeTab);
            const nextIndex = currentIndex < this.tabs.length - 1 ? currentIndex + 1 : 0;
            return this.tabs[nextIndex];
        },
        
        getCSRFToken() {
            return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        },
        
        // API call with retry mechanism
        async apiCall(url, options = {}) {
            try {
                const response = await fetch(url, options);
                
                // Handle authentication errors
                if (response.status === 401) {
                    this.handleAuthError();
                    return null;
                }
                
                return response;
            } catch (error) {
                console.error(`API call failed for ${url}:`, error);
                throw error;
            }
        },
        
        // API call with retry mechanism
        async apiCallWithRetry(url, options = {}, callType = 'default') {
            let lastError;
            
            for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
                try {
                    const response = await this.apiCall(url, options);
                    
                    if (response && response.ok) {
                        // Reset retry count on success
                        this.retryCount[callType] = 0;
                        return response;
                    } else if (response && response.status >= 400 && response.status < 500) {
                        // Don't retry client errors (4xx)
                        return response;
                    }
                    
                    lastError = new Error(`HTTP ${response.status}: ${response.statusText}`);
                } catch (error) {
                    lastError = error;
                    
                    // Don't retry authentication errors
                    if (error.message.includes('401')) {
                        throw error;
                    }
                }
                
                // If not the last attempt, wait before retrying
                if (attempt < this.maxRetries) {
                    await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
                    this.retryCount[callType] = attempt;
                }
            }
            
            throw lastError;
        },
        
        // Handle authentication errors
        handleAuthError() {
            this.showError('Sessione scaduta. Reindirizzamento al login...');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
        },
        
        // Error handling
        handleError(error, context = 'unknown') {
            console.error(`Error in ${context}:`, error);
            
            let userMessage = 'Si è verificato un errore imprevisto.';
            
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                userMessage = 'Errore di connessione. Verifica la tua rete e riprova.';
            } else if (error.message.includes('401')) {
                userMessage = 'Sessione scaduta. Effettua nuovamente il login.';
                this.handleAuthError();
            } else if (error.message.includes('500')) {
                userMessage = 'Errore del server. Riprova più tardi.';
            } else if (error.message.includes('timeout')) {
                userMessage = 'Timeout del server. Riprova più tardi.';
            }
            
            this.setError(userMessage);
            Alpine.store('unifiedDashboard').setError(userMessage);
        },
        
        // Error display methods
        setError(message) {
            this.error = message;
        },
        
        clearError() {
            this.error = null;
            Alpine.store('unifiedDashboard').clearError();
        },
        
        showError(message) {
            this.setError(message);
            // Show toast notification if available
            if (window.showToast) {
                window.showToast(message, 'error');
            }
        },
        
        showSuccess(message) {
            this.clearError();
            // Show toast notification if available
            if (window.showToast) {
                window.showToast(message, 'success');
            }
        },
        
        // Tab persistence
        persistTab(tabName) {
            localStorage.setItem('unifiedDashboard_activeTab', tabName);
        },
        
        setupTabPersistence() {
            const savedTab = localStorage.getItem('unifiedDashboard_activeTab');
            if (savedTab && this.tabs.includes(savedTab)) {
                this.switchTab(savedTab);
            }
        },
        
        // Keyboard navigation
        setupKeyboardNavigation() {
            document.addEventListener('keydown', (e) => {
                // Ctrl/Cmd + number to switch tabs
                if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '3') {
                    e.preventDefault();
                    const tabIndex = parseInt(e.key) - 1;
                    if (tabIndex < this.tabs.length) {
                        this.switchTab(this.tabs[tabIndex]);
                    }
                }
                
                // Arrow keys for tab navigation
                if (e.altKey) {
                    if (e.key === 'ArrowLeft') {
                        e.preventDefault();
                        this.switchTab(this.getPreviousTab());
                    } else if (e.key === 'ArrowRight') {
                        e.preventDefault();
                        this.switchTab(this.getNextTab());
                    }
                }
            });
        },
        
        // Mock data for development
        getMockActivities() {
            return [
                {
                    id: 1,
                    type: 'sites',
                    title: 'Nuovo sito aggiunto',
                    description: 'Nuovo sito archeologico aggiunto al sistema',
                    timestamp: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
                    user: 'Mario Rossi',
                    site: 'Foro Romano'
                },
                {
                    id: 2,
                    type: 'giornale',
                    title: 'Giornale creato',
                    description: 'Nuovo giornale di cantiere creato',
                    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
                    user: 'Giulia Bianchi',
                    site: 'Scavo A'
                },
                {
                    id: 3,
                    type: 'photos',
                    title: 'Fotografie caricate',
                    description: 'Nuove fotografie caricate nel sistema',
                    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 4).toISOString(),
                    user: 'Paolo Verdi',
                    site: 'Area B'
                },
                {
                    id: 4,
                    type: 'documents',
                    title: 'Documento aggiornato',
                    description: 'Scheda ICCD RA-300 è stata aggiornata',
                    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(),
                    user: 'Laura Neri',
                    site: 'Settore C'
                },
                {
                    id: 5,
                    type: 'users',
                    title: 'Nuovo utente registrato',
                    description: 'Utente "Marco Gialli" si è registrato al sistema',
                    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
                    user: 'Sistema'
                }
            ];
        }
    }));
    
    // Site Selector Component
    Alpine.data("siteSelector", () => ({
        searchQuery: '',
        viewMode: 'grid',
        loading: false,
        sites: [],
        filteredSites: [],
        context: 'overview', // 'overview', 'giornale', 'analytics'
        
        async init() {
            await this.loadSites();
        },
        
        async loadSites() {
            this.loading = true;
            try {
                // Reuse sites data from parent component
                const parentData = Alpine.store('unifiedDashboard');
                this.sites = parentData?.sitesData || [];
                this.filteredSites = [...this.sites];
            } catch (error) {
                console.error('Error loading sites:', error);
                // Use parent component's error handling
                const parentData = Alpine.store('unifiedDashboard');
                if (parentData && parentData.handleError) {
                    parentData.handleError(error, 'site_selector_load');
                }
            } finally {
                this.loading = false;
            }
        },
        
        filterSites() {
            if (!this.searchQuery) {
                this.filteredSites = [...this.sites];
            } else {
                const query = this.searchQuery.toLowerCase();
                this.filteredSites = this.sites.filter(site => 
                    site.name.toLowerCase().includes(query) ||
                    site.code.toLowerCase().includes(query) ||
                    (site.location && site.location.toLowerCase().includes(query))
                );
            }
        },
        
        selectSite(site) {
            switch(this.context) {
                case 'overview':
                    window.location.href = `/view/${site.id}/dashboard/`;
                    break;
                case 'giornale':
                    window.location.href = `/giornale-cantiere/site/${site.id}`;
                    break;
                default:
                    window.location.href = `/view/${site.id}/dashboard/`;
            }
        },
        
        getSelectorTitle() {
            const titles = {
                'overview': 'Siti Archeologici',
                'giornale': 'Seleziona Sito per Giornale',
                'analytics': 'Analisi Siti'
            };
            return titles[this.context] || 'Siti';
        },
        
        getActionLabel() {
            const labels = {
                'overview': 'Apri Sito',
                'giornale': 'Apri Giornale',
                'analytics': 'Analizza'
            };
            return labels[this.context] || 'Apri';
        },
        
        getStatLabel(statType) {
            const labels = {
                'overview': {
                    'primary': 'Foto',
                    'secondary': 'Documenti'
                },
                'giornale': {
                    'primary': 'Giornali',
                    'secondary': 'Validati'
                },
                'analytics': {
                    'primary': 'Visite',
                    'secondary': 'Attività'
                }
            };
            return labels[this.context]?.[statType] || 'Dati';
        },
        
        getSiteStat(site, statType) {
            // Get stats from parent component or calculate
            const parentData = Alpine.store('unifiedDashboard');
            
            if (this.context === 'giornale') {
                return parentData?.giornaleSiteStats[site.id]?.[statType] || 0;
            }
            
            // Default stats for overview
            return Math.floor(Math.random() * 100); // Mock data
        },
        
        getPermissionBadgeClass(permission) {
            const classes = {
                'admin': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
                'write': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
                'read': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300'
            };
            return classes[permission] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
        }
    }));
    
    // Activity Feed Component
    Alpine.data("activityFeed", () => ({
        loading: false,
        activities: [],
        filteredActivities: [],
        activityFilter: 'all',
        hasMoreActivities: false,
        
        activityFilters: [
            { value: 'all', label: 'Tutto' },
            { value: 'sites', label: 'Siti' },
            { value: 'giornale', label: 'Giornale' },
            { value: 'documents', label: 'Documenti' },
            { value: 'photos', label: 'Fotografie' },
            { value: 'users', label: 'Utenti' }
        ],
        
        async init() {
            await this.loadActivities();
        },
        
        async loadActivities() {
            this.loading = true;
            try {
                // Reuse activities data from parent component
                const parentData = Alpine.store('unifiedDashboard');
                this.activities = parentData?.activities || [];
                this.updateFilteredActivities();
            } catch (error) {
                console.error('Error loading activities:', error);
                // Use parent component's error handling
                const parentData = Alpine.store('unifiedDashboard');
                if (parentData && parentData.handleError) {
                    parentData.handleError(error, 'activity_feed_load');
                }
            } finally {
                this.loading = false;
            }
        },
        
        updateFilteredActivities() {
            if (this.activityFilter === 'all') {
                this.filteredActivities = this.activities;
            } else {
                this.filteredActivities = this.activities.filter(activity => activity.type === this.activityFilter);
            }
        },
        
        setActivityFilter(filter) {
            this.activityFilter = filter;
            this.updateFilteredActivities();
        },
        
        async refreshActivities() {
            await this.loadActivities();
        },
        
        getActivityIcon(type) {
            const icons = {
                'sites': 'fa-map-marker-alt',
                'giornale': 'fa-book',
                'documents': 'fa-file-alt',
                'photos': 'fa-camera',
                'users': 'fa-user'
            };
            return icons[type] || 'fa-circle';
        },
        
        getActivityIconClass(type) {
            const classes = {
                'sites': 'bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-300',
                'giornale': 'bg-orange-100 text-orange-600 dark:bg-orange-900 dark:text-orange-300',
                'documents': 'bg-green-100 text-green-600 dark:bg-green-900 dark:text-green-300',
                'photos': 'bg-purple-100 text-purple-600 dark:bg-purple-900 dark:text-purple-300',
                'users': 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900 dark:text-yellow-300'
            };
            return classes[type] || 'bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300';
        },
        
        getActivityTypeLabel(type) {
            const labels = {
                'sites': 'Sito',
                'giornale': 'Giornale',
                'documents': 'Documento',
                'photos': 'Foto',
                'users': 'Utente'
            };
            return labels[type] || type;
        },
        
        getActivityTypeClass(type) {
            const classes = {
                'sites': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
                'giornale': 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
                'documents': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
                'photos': 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
                'users': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300'
            };
            return classes[type] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
        },
        
        formatTime(timestamp) {
            const date = new Date(timestamp);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);
            
            if (diffMins < 1) return 'Proprio ora';
            if (diffMins < 60) return `${diffMins} min fa`;
            if (diffHours < 24) return `${diffHours} ore fa`;
            if (diffDays < 7) return `${diffDays} giorni fa`;
            
            return date.toLocaleDateString('it-IT');
        },
        
        executeActivityAction(action, activity) {
            console.log('Executing action:', action, 'on activity:', activity);
            // Implementation for activity actions
        }
    }));
    
    // Context Actions Component
    Alpine.data("contextActions", () => ({
        activeTab: 'overview',
        showConfirmModal: false,
        confirmModalTitle: '',
        confirmModalMessage: '',
        pendingAction: null,
        
        init() {
            try {
                // Get active tab from parent component
                const parentData = Alpine.store('unifiedDashboard');
                this.activeTab = parentData?.activeTab || 'overview';
            } catch (error) {
                console.error('Error initializing context actions:', error);
                this.activeTab = 'overview'; // Fallback
            }
        },
        
        getContextTitle() {
            const titles = {
                'overview': 'Dashboard Panoramica',
                'giornale': 'Giornale di Cantiere',
                'analytics': 'Analisi e Report'
            };
            return titles[this.activeTab] || 'Dashboard';
        },
        
        getContextDescription() {
            const descriptions = {
                'overview': 'Gestione completa dei siti archeologici e attività',
                'giornale': 'Documentazione quotidiana delle attività di scavo',
                'analytics': 'Analisi dettagliata e report del sistema'
            };
            return descriptions[this.activeTab] || '';
        },
        
        getContextActions() {
            const actions = {
                'overview': [
                    {
                        id: 'refresh',
                        label: 'Aggiorna',
                        icon: 'fa-sync-alt',
                        class: 'bg-blue-600 text-white hover:bg-blue-700',
                        disabled: false
                    },
                    {
                        id: 'new-site',
                        label: 'Nuovo Sito',
                        icon: 'fa-plus',
                        class: 'bg-green-600 text-white hover:bg-green-700',
                        disabled: false
                    },
                    {
                        id: 'upload',
                        label: 'Carica Documenti',
                        icon: 'fa-upload',
                        class: 'bg-purple-600 text-white hover:bg-purple-700',
                        disabled: false
                    }
                ],
                'giornale': [
                    {
                        id: 'new-giornale',
                        label: 'Nuovo Giornale',
                        icon: 'fa-plus',
                        class: 'bg-orange-600 text-white hover:bg-orange-700',
                        disabled: false
                    },
                    {
                        id: 'operators',
                        label: 'Operatori',
                        icon: 'fa-users',
                        class: 'bg-blue-600 text-white hover:bg-blue-700',
                        disabled: false
                    },
                    {
                        id: 'reports',
                        label: 'Report',
                        icon: 'fa-chart-bar',
                        class: 'bg-indigo-600 text-white hover:bg-indigo-700',
                        disabled: false
                    }
                ],
                'analytics': [
                    {
                        id: 'generate-report',
                        label: 'Genera Report',
                        icon: 'fa-file-pdf',
                        class: 'bg-green-600 text-white hover:bg-green-700',
                        disabled: false
                    },
                    {
                        id: 'export-data',
                        label: 'Esporta Dati',
                        icon: 'fa-download',
                        class: 'bg-teal-600 text-white hover:bg-teal-700',
                        disabled: false
                    }
                ]
            };
            return actions[this.activeTab] || [];
        },
        
        getActionButtonClass(action) {
            return action.class || 'bg-gray-600 text-white hover:bg-gray-700';
        },
        
        executeContextAction(action) {
            switch(action.id) {
                case 'refresh':
                    this.refreshCurrentTab();
                    break;
                case 'new-site':
                    this.navigateToNewSite();
                    break;
                case 'new-giornale':
                    this.navigateToNewGiornale();
                    break;
                case 'operators':
                    this.navigateToOperators();
                    break;
                case 'reports':
                    this.navigateToReports();
                    break;
                case 'upload':
                    this.navigateToUpload();
                    break;
                case 'generate-report':
                    this.showGenerateReportModal();
                    break;
                case 'export-data':
                    this.exportData();
                    break;
                default:
                    console.log('Unknown action:', action);
            }
        },
        
        refreshCurrentTab() {
            const parentData = Alpine.store('unifiedDashboard');
            if (parentData) {
                parentData.refreshOverviewData();
            }
        },
        
        navigateToNewSite() {
            window.location.href = '/sites/create';
        },
        
        navigateToNewGiornale() {
            const parentData = Alpine.store('unifiedDashboard');
            if (parentData?.giornaleSites?.length > 0) {
                window.location.href = `/giornale-cantiere/site/${parentData.giornaleSites[0].id}`;
            } else {
                this.showError('Nessun sito disponibile per creare un giornale');
            }
        },
        
        navigateToOperators() {
            window.location.href = '/giornale-cantiere/operatori';
        },
        
        navigateToReports() {
            window.location.href = '/giornale-cantiere/reports';
        },
        
        navigateToUpload() {
            const parentData = Alpine.store('unifiedDashboard');
            if (parentData?.sitesData?.length > 0) {
                window.location.href = `/view/${parentData.sitesData[0].id}/photos/`;
            } else {
                this.showError('Nessun sito disponibile per caricare documenti');
            }
        },
        
        showGenerateReportModal() {
            this.confirmModalTitle = 'Genera Report';
            this.confirmModalMessage = 'Sei sicuro di voler generare un report dettagliato? Questa operazione potrebbe richiedere alcuni minuti.';
            this.pendingAction = 'generate-report';
            this.showConfirmModal = true;
        },
        
        exportData() {
            this.confirmModalTitle = 'Esporta Dati';
            this.confirmModalMessage = 'Sei sicuro di voler esportare tutti i dati del sistema? Verrà scaricato un file CSV con tutte le informazioni.';
            this.pendingAction = 'export-data';
            this.showConfirmModal = true;
        },
        
        confirmAction() {
            if (this.pendingAction === 'generate-report') {
                this.generateReport();
            } else if (this.pendingAction === 'export-data') {
                this.performDataExport();
            }
            
            this.showConfirmModal = false;
            this.pendingAction = null;
        },
        
        generateReport() {
            console.log('Generating report...');
            // Implementation for report generation
        },
        
        performDataExport() {
            console.log('Exporting data...');
            // Implementation for data export
        },
        
        showError(message) {
            console.error(message);
            // Use parent component's error handling if available
            const parentData = Alpine.store('unifiedDashboard');
            if (parentData && parentData.showError) {
                parentData.showError(message);
            }
        }
    }));
});