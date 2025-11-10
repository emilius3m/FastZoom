/**
 * Centralized API Client for FastAPI Authentication
 * FastZoom Archaeological Site Management System
 *
 * This utility provides a centralized fetch wrapper that automatically includes credentials,
 * consistent error handling, and easy-to-use methods for HTTP operations.
 *
 * Key Features:
 * - Automatic inclusion of credentials (cookies) in all requests
 * - Consistent error handling and response processing
 * - Support for token refresh if needed in the future
 * - Easy-to-use methods for GET, POST, PUT, PATCH, DELETE operations
 * - Form data and file upload support
 * - Automatic 401 redirect to login page
 *
 * Usage Examples:
 *
 * // Basic GET request
 * const users = await api.get('/api/v1/admin/users');
 *
 * // POST request with data
 * const result = await api.post('/api/v1/admin/sites', {
 *     name: 'Nuovo Sito',
 *     code: 'NS001',
 *     location: 'Roma'
 * });
 *
 * // PUT request for updates
 * await api.put('/api/v1/admin/sites/123', { name: 'Sito Aggiornato' });
 *
 * // DELETE with optional body
 * await api.delete('/api/v1/admin/sites/123', {
 *     data: { admin_password: 'secret', confirm_delete: true }
 * });
 *
 * // Upload files
 * const formData = new FormData();
 * formData.append('file', fileInput.files[0]);
 * await api.upload('/api/v1/photos/upload', formData);
 */

class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    /**
     * Core request method that handles all API calls
     * @param {string} url - The API endpoint URL
     * @param {Object} options - Fetch options
     * @returns {Promise} - Parsed response data
     * @throws {Error} - With detailed error message
     */
    async request(url, options = {}) {
        // Default fetch options with credentials
        const fetchOptions = {
            credentials: 'include', // Always include cookies for authentication
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        };

        // Remove Content-Type for FormData (browser sets it automatically with boundary)
        if (options.body instanceof FormData) {
            delete fetchOptions.headers['Content-Type'];
        }

        // Full URL with base path
        const fullUrl = this.baseUrl + url;

        try {
            console.log(`API Request: ${fullUrl}`, fetchOptions);

            const response = await fetch(fullUrl, fetchOptions);

            console.log(`API Response: ${response.status}`, { ok: response.ok });

            // Handle successful responses
            if (response.ok) {
                // Check if response has content
                const contentType = response.headers.get('content-type');

                if (contentType && contentType.includes('application/json')) {
                    return await response.json();
                } else if (response.status === 204) {
                    // No content response
                    return null;
                } else {
                    // Return text for non-JSON responses
                    return await response.text();
                }
            }

            // Handle error responses
            let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            let errorText = '';

            try {
                errorText = await response.text();

                // Try to parse as JSON for structured error messages
                if (errorText) {
                    try {
                        const errorData = JSON.parse(errorText);
                        errorMessage = errorData.detail || errorData.message || errorMessage;
                    } catch (e) {
                        // If not JSON, use the text directly
                        errorMessage = `${errorMessage} - ${errorText}`;
                    }
                }
            } catch (e) {
                console.error('Error parsing error response:', e);
            }

            // Special handling for 401 Unauthorized - redirect to login
            if (response.status === 401) {
                console.warn('Authentication failed, redirecting to login...');
                window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
                throw new Error('Session expired, redirecting to login...');
            }

            // Special handling for 403 Forbidden
            if (response.status === 403) {
                throw new Error('Accesso negato: permessi insufficienti');
            }

            // Throw error with message
            throw new Error(errorMessage);

        } catch (error) {
            // Network errors or other fetch errors
            if (error instanceof TypeError) {
                console.error('Network error:', error);
                throw new Error('Errore di rete. Verifica la connessione.');
            }

            // Re-throw other errors
            throw error;
        }
    }

    /**
     * GET request method
     * @param {string} url - The API endpoint URL
     * @param {Object} params - Query parameters
     * @param {Object} options - Additional fetch options
     * @returns {Promise} - Response data
     */
    async get(url, params = {}, options = {}) {
        // Build query string from params
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        return this.request(fullUrl, {
            method: 'GET',
            ...options,
        });
    }

    /**
     * POST request method
     * @param {string} url - The API endpoint URL
     * @param {Object} data - Request body data
     * @param {Object} options - Additional fetch options
     * @returns {Promise} - Response data
     */
    async post(url, data = {}, options = {}) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data),
            ...options,
        });
    }

    /**
     * PUT request method
     * @param {string} url - The API endpoint URL
     * @param {Object} data - Request body data
     * @param {Object} options - Additional fetch options
     * @returns {Promise} - Response data
     */
    async put(url, data = {}, options = {}) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data),
            ...options,
        });
    }

    /**
     * PATCH request method
     * @param {string} url - The API endpoint URL
     * @param {Object} data - Request body data
     * @param {Object} options - Additional fetch options
     * @returns {Promise} - Response data
     */
    async patch(url, data = {}, options = {}) {
        return this.request(url, {
            method: 'PATCH',
            body: JSON.stringify(data),
            ...options,
        });
    }

    /**
     * DELETE request method with optional body
     * @param {string} url - The API endpoint URL
     * @param {Object} options - Additional fetch options (can include 'data' property)
     * @returns {Promise} - Response data
     *
     * Usage:
     * // Without body
     * await api.delete('/api/v1/admin/sites/123');
     *
     * // With body (password confirmation, etc.)
     * await api.delete('/api/v1/admin/sites/123', {
     *     data: { admin_password: 'secret', confirm_delete: true }
     * });
     */
    async delete(url, options = {}) {
        const requestOptions = { method: 'DELETE', ...options };

        // If 'data' is provided, convert it to JSON body
        if (options.data) {
            requestOptions.body = JSON.stringify(options.data);
            delete requestOptions.data;
        }

        return this.request(url, requestOptions);
    }

    /**
     * POST request with form data (multipart/form-data)
     * Used for file uploads
     * @param {string} url - The API endpoint URL
     * @param {FormData} formData - FormData object containing files and fields
     * @param {Object} options - Additional fetch options
     * @returns {Promise} - Response data
     *
     * Usage:
     * const formData = new FormData();
     * formData.append('file', fileInput.files[0]);
     * formData.append('site_id', '123');
     * await api.postForm('/api/v1/photos/upload', formData);
     */
    async postForm(url, formData, options = {}) {
        return this.request(url, {
            method: 'POST',
            body: formData,
            headers: {}, // Don't set Content-Type, browser will set it with boundary
            ...options,
        });
    }

    /**
     * Alias for postForm - more intuitive for file uploads
     * @param {string} url - The API endpoint URL
     * @param {FormData} formData - FormData object containing files and fields
     * @param {Object} options - Additional fetch options
     * @returns {Promise} - Response data
     */
    async upload(url, formData, options = {}) {
        return this.postForm(url, formData, options);
    }

    /**
     * Download a file from the server
     * @param {string} url - The API endpoint URL
     * @param {string} filename - Suggested filename for download
     * @returns {Promise<Blob>} - File blob
     *
     * Usage:
     * const blob = await api.download('/api/v1/export/sites', 'sites.csv');
     * // The file download will start automatically
     */
    async download(url, filename = 'download') {
        try {
            const response = await fetch(this.baseUrl + url, {
                method: 'GET',
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error(`Download failed: ${response.statusText}`);
            }

            const blob = await response.blob();

            // Create download link and trigger download
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);

            return blob;
        } catch (error) {
            console.error('Download error:', error);
            throw error;
        }
    }
}

// Create and export global instance
const api = new ApiClient();

// Make it available globally for Alpine.js components
window.api = api;

// Export for module systems (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ApiClient;
}
