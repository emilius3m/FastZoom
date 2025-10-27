/**
 * Sistema di Gestione Errori Avanzato
 * Implementa retry automatico con backoff esponenziale, logging e recovery paths
 */

class ErrorHandlingSystem {
    constructor() {
        this.retryQueues = new Map(); // Coda di retry per operazioni
        this.errorLog = []; // Log degli errori per debugging
        this.maxLogSize = 1000; // Massimo numero di errori in memoria
        this.isOnline = navigator.onLine;
        
        // Inizializza listener per stato di connessione
        this.initializeConnectionMonitoring();
        
        console.log('🛡️ Error Handling System initialized');
    }
    
    /**
     * Inizializza il monitoraggio dello stato di connessione
     */
    initializeConnectionMonitoring() {
        window.addEventListener('online', () => {
            this.isOnline = true;
            this.logInfo('Connection restored', 'Network connection is back online');
            // Riprova le operazioni in coda
            this.processRetryQueue();
        });
        
        window.addEventListener('offline', () => {
            this.isOnline = false;
            this.logError('Connection lost', 'Network connection is offline');
        });
    }
    
    /**
     * Esegue un'operazione con retry automatico e backoff esponenziale
     * @param {Function} operation - Funzione da eseguire (deve restituire Promise)
     * @param {Object} options - Opzioni di configurazione
     * @returns {Promise} Promise dell'operazione con retry
     */
    async executeWithRetry(operation, options = {}) {
        const config = {
            maxRetries: 3,
            baseDelay: 1000, // 1 secondo
            maxDelay: 30000, // 30 secondi
            backoffFactor: 2,
            retryCondition: null, // Funzione custom per determinare se retryare
            onRetry: null, // Callback ad ogni retry
            onSuccess: null, // Callback al successo
            onFinalError: null, // Callback all'errore finale
            operationId: this.generateOperationId(),
            ...options
        };
        
        this.logInfo('Operation started', `Starting operation ${config.operationId} with max ${config.maxRetries} retries`);
        
        let lastError = null;
        let attempt = 0;
        
        while (attempt <= config.maxRetries) {
            try {
                const result = await this.executeOperation(operation, config, attempt);
                
                // Successo - pulisci la coda e notifica
                this.retryQueues.delete(config.operationId);
                
                if (config.onSuccess) {
                    config.onSuccess(result, attempt);
                }
                
                this.logInfo('Operation succeeded', `Operation ${config.operationId} succeeded on attempt ${attempt + 1}`);
                return result;
                
            } catch (error) {
                lastError = error;
                attempt++;
                
                this.logError('Operation failed', `Operation ${config.operationId} failed on attempt ${attempt}: ${error.message}`, {
                    operationId: config.operationId,
                    attempt: attempt,
                    error: error,
                    willRetry: attempt <= config.maxRetries
                });
                
                // Verifica se si deve retryare
                if (attempt > config.maxRetries || !this.shouldRetry(error, config, attempt)) {
                    break;
                }
                
                // Calcola delay con backoff esponenziale
                const delay = this.calculateBackoffDelay(attempt - 1, config);
                
                // Notifica retry
                if (config.onRetry) {
                    config.onRetry(error, attempt, delay);
                }
                
                // Attendi prima del prossimo tentativo
                await this.delay(delay);
            }
        }
        
        // Tutti i retry falliti
        this.retryQueues.delete(config.operationId);
        
        if (config.onFinalError) {
            config.onFinalError(lastError, attempt - 1);
        }
        
        this.logError('Operation failed permanently', `Operation ${config.operationId} failed after ${attempt - 1} attempts`, {
            operationId: config.operationId,
            totalAttempts: attempt - 1,
            finalError: lastError
        });
        
        throw lastError;
    }
    
    /**
     * Esegue l'operazione con timeout e gestione errori
     */
    async executeOperation(operation, config, attempt) {
        return new Promise(async (resolve, reject) => {
            try {
                // Verifica connessione
                if (!this.isOnline) {
                    throw new Error('Network connection is offline');
                }
                
                // Esegui operazione con timeout
                const timeout = config.timeout || 30000; // 30 secondi default
                const timeoutId = setTimeout(() => {
                    reject(new Error(`Operation timeout after ${timeout}ms`));
                }, timeout);
                
                try {
                    const result = await operation();
                    clearTimeout(timeoutId);
                    resolve(result);
                } catch (error) {
                    clearTimeout(timeoutId);
                    reject(error);
                }
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    /**
     * Determina se un'operazione deve essere retryata
     */
    shouldRetry(error, config, attempt) {
        // Usa condizione custom se fornita
        if (config.retryCondition && typeof config.retryCondition === 'function') {
            return config.retryCondition(error, attempt);
        }
        
        // Condizioni di retry predefinite
        if (error.name === 'AbortError') {
            return false; // Non retryare abort manuale
        }
        
        if (error.status === 401) {
            return false; // Non retryare errori di auth
        }
        
        if (error.status === 403) {
            return false; // Non retryare errori di permessi
        }
        
        if (error.status === 404) {
            return false; // Non retryare risorse non trovate
        }
        
        if (error.status === 422) {
            return false; // Non retryare errori di validazione
        }
        
        // Retry per errori di rete e server
        if (error.status >= 500 || error.status === 0 || !error.status) {
            return true;
        }
        
        // Retry per errori di timeout
        if (error.message && error.message.includes('timeout')) {
            return true;
        }
        
        return false;
    }
    
    /**
     * Calcola il delay con backoff esponenziale
     */
    calculateBackoffDelay(attempt, config) {
        // Backoff esponenziale con jitter
        const exponentialDelay = config.baseDelay * Math.pow(config.backoffFactor, attempt);
        const jitter = Math.random() * 0.1 * exponentialDelay; // ±10% jitter
        const delay = exponentialDelay + jitter;
        
        return Math.min(delay, config.maxDelay);
    }
    
    /**
     * Utility per delay
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    /**
     * Genera ID univoco per operazione
     */
    generateOperationId() {
        return 'op_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    /**
     * Aggiunge un'operazione alla coda di retry
     */
    addToRetryQueue(operationId, operation, options = {}) {
        this.retryQueues.set(operationId, {
            operation,
            options,
            timestamp: Date.now()
        });
        
        this.logInfo('Added to retry queue', `Operation ${operationId} queued for retry`);
    }
    
    /**
     * Processa la coda di retry quando la connessione è ripristinata
     */
    async processRetryQueue() {
        if (!this.isOnline || this.retryQueues.size === 0) {
            return;
        }
        
        this.logInfo('Processing retry queue', `Processing ${this.retryQueues.size} queued operations`);
        
        const retryPromises = [];
        
        for (const [operationId, queueItem] of this.retryQueues) {
            retryPromises.push(
                this.executeWithRetry(queueItem.operation, {
                    ...queueItem.options,
                    operationId
                }).catch(error => {
                    this.logError('Queued operation failed', `Queued operation ${operationId} failed: ${error.message}`);
                })
            );
        }
        
        try {
            await Promise.allSettled(retryPromises);
        } catch (error) {
            this.logError('Retry queue processing failed', error.message);
        }
    }
    
    /**
     * Metodi di logging
     */
    logError(message, details = null, context = {}) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            level: 'ERROR',
            message,
            details,
            context,
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        this.addToLog(logEntry);
        console.error('🛡️ ERROR:', message, details, context);
    }
    
    logWarning(message, details = null, context = {}) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            level: 'WARNING',
            message,
            details,
            context,
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        this.addToLog(logEntry);
        console.warn('⚠️ WARNING:', message, details, context);
    }
    
    logInfo(message, details = null, context = {}) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            level: 'INFO',
            message,
            details,
            context,
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        this.addToLog(logEntry);
        console.info('ℹ️ INFO:', message, details, context);
    }
    
    addToLog(logEntry) {
        this.errorLog.unshift(logEntry);
        
        // Mantieni solo gli ultimi N errori
        if (this.errorLog.length > this.maxLogSize) {
            this.errorLog = this.errorLog.slice(0, this.maxLogSize);
        }
        
        // Salva in localStorage per persistenza
        try {
            localStorage.setItem('errorHandlingSystem_log', JSON.stringify(this.errorLog.slice(0, 100)));
        } catch (error) {
            console.warn('Failed to save error log to localStorage:', error);
        }
    }
    
    /**
     * Recupera il log degli errori
     */
    getErrorLog(filter = {}) {
        let filteredLog = [...this.errorLog];
        
        if (filter.level) {
            filteredLog = filteredLog.filter(entry => entry.level === filter.level);
        }
        
        if (filter.since) {
            const since = new Date(filter.since);
            filteredLog = filteredLog.filter(entry => new Date(entry.timestamp) >= since);
        }
        
        if (filter.limit) {
            filteredLog = filteredLog.slice(0, filter.limit);
        }
        
        return filteredLog;
    }
    
    /**
     * Esporta il log per debugging
     */
    exportErrorLog() {
        const logData = {
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            url: window.location.href,
            log: this.errorLog
        };
        
        const blob = new Blob([JSON.stringify(logData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `error_log_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    
    /**
     * Pulisce il log degli errori
     */
    clearErrorLog() {
        this.errorLog = [];
        try {
            localStorage.removeItem('errorHandlingSystem_log');
        } catch (error) {
            console.warn('Failed to clear error log from localStorage:', error);
        }
    }
    
    /**
     * Analizza gli errori comuni e suggerisce soluzioni
     */
    analyzeErrors() {
        const errorAnalysis = {
            totalErrors: this.errorLog.length,
            errorTypes: {},
            commonErrors: [],
            networkErrors: 0,
            authErrors: 0,
            serverErrors: 0,
            timeRange: {
                oldest: null,
                newest: null
            }
        };
        
        this.errorLog.forEach(entry => {
            // Analisi tipi di errore
            if (entry.details && entry.details.error) {
                const errorType = entry.details.error.name || 'Unknown';
                errorAnalysis.errorTypes[errorType] = (errorAnalysis.errorTypes[errorType] || 0) + 1;
            }
            
            // Analisi categorie
            if (entry.details && entry.details.status) {
                const status = entry.details.status;
                if (status === 401 || status === 403) {
                    errorAnalysis.authErrors++;
                } else if (status >= 500) {
                    errorAnalysis.serverErrors++;
                } else if (status === 0 || status === 'NETWORK_ERROR') {
                    errorAnalysis.networkErrors++;
                }
            }
            
            // Range temporale
            const timestamp = new Date(entry.timestamp);
            if (!errorAnalysis.timeRange.oldest || timestamp < errorAnalysis.timeRange.oldest) {
                errorAnalysis.timeRange.oldest = timestamp;
            }
            if (!errorAnalysis.timeRange.newest || timestamp > errorAnalysis.timeRange.newest) {
                errorAnalysis.timeRange.newest = timestamp;
            }
        });
        
        // Errori più comuni
        Object.entries(errorAnalysis.errorTypes)
            .sort(([,a], [,b]) => b - a)
            .slice(0, 5)
            .forEach(([errorType, count]) => {
                errorAnalysis.commonErrors.push({ errorType, count });
            });
        
        return errorAnalysis;
    }
    
    /**
     * Fornisce suggerimenti per il recovery basati sull'analisi
     */
    getRecoverySuggestions(error) {
        const suggestions = [];
        
        if (!error) return suggestions;
        
        // Errori di rete
        if (error.status === 0 || error.message?.includes('network')) {
            suggestions.push({
                type: 'network',
                title: 'Problema di connessione',
                description: 'Verifica la tua connessione internet e riprova.',
                actions: [
                    { label: 'Controlla connessione', action: 'check-connection' },
                    { label: 'Riprova ora', action: 'retry-now' }
                ]
            });
        }
        
        // Errori di autenticazione
        if (error.status === 401) {
            suggestions.push({
                type: 'auth',
                title: 'Sessione scaduta',
                description: 'La tua sessione è scaduta. Effettua nuovamente il login.',
                actions: [
                    { label: 'Accedi', action: 'login' }
                ]
            });
        }
        
        // Errori di permessi
        if (error.status === 403) {
            suggestions.push({
                type: 'permission',
                title: 'Permessi insufficienti',
                description: 'Non hai i permessi necessari per questa operazione.',
                actions: [
                    { label: 'Contatta amministratore', action: 'contact-admin' }
                ]
            });
        }
        
        // Errori del server
        if (error.status >= 500) {
            suggestions.push({
                type: 'server',
                title: 'Errore del server',
                description: 'Il server ha riscontrato un problema. Riprova più tardi.',
                actions: [
                    { label: 'Riprova più tardi', action: 'retry-later' },
                    { label: 'Contatta supporto', action: 'contact-support' }
                ]
            });
        }
        
        // Timeout
        if (error.message?.includes('timeout')) {
            suggestions.push({
                type: 'timeout',
                title: 'Timeout della richiesta',
                description: 'La richiesta ha impiegato troppo tempo. Prova con una connessione più veloce.',
                actions: [
                    { label: 'Riprova', action: 'retry' },
                    { label: 'Riduci carico', action: 'reduce-load' }
                ]
            });
        }
        
        return suggestions;
    }
    
    /**
     * Distruzione e cleanup
     */
    destroy() {
        // Rimuovi event listeners
        window.removeEventListener('online', this.handleOnline);
        window.removeEventListener('offline', this.handleOffline);
        
        // Salva log finale
        this.logInfo('Error Handling System destroyed', 'System shutting down');
    }
}

// Inizializza globalmente
window.errorHandlingSystem = new ErrorHandlingSystem();

// Esponi metodi utili globalmente
window.retryWithBackoff = (operation, options) => {
    return window.errorHandlingSystem.executeWithRetry(operation, options);
};

window.logError = (message, details, context) => {
    return window.errorHandlingSystem.logError(message, details, context);
};

window.logWarning = (message, details, context) => {
    return window.errorHandlingSystem.logWarning(message, details, context);
};

window.logInfo = (message, details, context) => {
    return window.errorHandlingSystem.logInfo(message, details, context);
};

// Auto-inizializzazione quando il DOM è pronto
document.addEventListener('DOMContentLoaded', () => {
    console.log('🛡️ Error Handling System loaded and ready');
});