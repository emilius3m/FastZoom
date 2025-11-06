/**
 * Centralized API Client for FastAPI Authentication
 * 
 * This utility provides a centralized fetch wrapper that automatically includes credentials,
 * consistent error handling, and easy-to-use methods for HTTP operations.
 * 
 * Key Features:
 * - Automatic inclusion of credentials (cookies) in all requests
 * - Consistent error handling and response processing
 * - Support for token refresh if needed in the future
 * - Easy-to-use methods for GET, POST, PUT, DELETE operations
 * 
 * Usage:
 * // Basic GET request
 * const users = await api.get('/api/v1/admin/users');
 * 
 * // POST request with data
 * const result = await api.post('/api/v1/admin/users', userData);
 * 
 * // Custom options
 * const response = await api.get('/custom/endpoint', {
 *     headers: { 'Custom-Header': 'value' }
 * });
 */
class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    /**
     * Core request method that handles all API calls
     * @param {string} url - The API endpoint URL
     * @param {Object} options - Fetch options
     * @returns {Promise<Object>} - JSON response data
     */
    async request(url, options = {}) {
        // Ensure credentials are always included for authentication cookies
        const defaultOptions = {
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };

        // Merge default options with provided options
        const fetchOptions = { ...defaultOptions, ...options };

        try {
            console.log(`API Request: ${this.baseUrl + url}`, fetchOptions);
            
            const response = await fetch(this.baseUrl + url, fetchOptions);
            
            // Log response for debugging
            console.log(`API Response: ${response.status} ${response.statusText}`, {
                url: this.baseUrl + url,
                ok: response.ok,
                status: response.status
            });

            // Handle 401 Unauthorized errors (potential session expiry)
            if (response.status === 401) {
                console.warn('Unauthorized response received. Session may have expired.');
                // TODO: Implement token refresh logic if needed
                // For now, redirect to login page
                if (window.location.pathname !== '/login') {
                    window.location.href = '/login';
                }
                throw new Error('Authentication required. Please log in again.');
            }

            // Handle other HTTP errors
            if (!response.ok) {
                const errorText = await response.text();
                let errorMessage = `HTTP error! status: ${response.status}`;
                
                try {
                    const errorData = JSON.parse(errorText);
                    errorMessage = errorData.detail || errorData.message || errorMessage;
                } catch (e) {
                    // If JSON parsing fails, use the raw text
                    errorMessage = `${errorMessage} - ${errorText}`;
                }
                
                console.error('API Error:', {
                    url: this.baseUrl + url,
                    status: response.status,
                    statusText: response.statusText,
                    error: errorMessage
                });
                
                throw new Error(errorMessage);
            }

            // Parse and return JSON response
            const data = await response.json();
            console.log('API Response Data:', data);
            return data;
            
        } catch (error) {
            console.error('Network or parsing error:', {
                url: this.baseUrl + url,
                error: error.message
            });
            throw error;
        }
    }

    /**
     * GET request method
     * @param {string} url - The API endpoint URL
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async get(url, options = {}) {
        return this.request(url, { ...options, method: 'GET' });
    }

    /**
     * POST request method
     * @param {string} url - The API endpoint URL
     * @param {Object} data - Request body data
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async post(url, data, options = {}) {
        return this.request(url, {
            ...options,
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT request method
     * @param {string} url - The API endpoint URL
     * @param {Object} data - Request body data
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async put(url, data, options = {}) {
        return this.request(url, {
            ...options,
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE request method
     * @param {string} url - The API endpoint URL
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async delete(url, options = {}) {
        return this.request(url, { ...options, method: 'DELETE' });
    }

    /**
     * PATCH request method
     * @param {string} url - The API endpoint URL
     * @param {Object} data - Request body data
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async patch(url, data, options = {}) {
        return this.request(url, {
            ...options,
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    /**
     * POST form data method (for form submissions with FormData)
     * @param {string} url - The API endpoint URL
     * @param {FormData} formData - Form data object
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async postForm(url, formData, options = {}) {
        const formOptions = {
            credentials: 'include',
            method: 'POST',
            body: formData,
            // Don't set Content-Type header for FormData - browser sets it with boundary
            ...options
        };
        
        return this.request(url, formOptions);
    }

    /**
     * Upload form data (for file uploads)
     * @param {string} url - The API endpoint URL
     * @param {FormData} formData - Form data with files
     * @param {Object} options - Additional fetch options
     * @returns {Promise<Object>} - Response data
     */
    async upload(url, formData, options = {}) {
        const uploadOptions = {
            credentials: 'include',
            body: formData,
            // Don't set Content-Type header for FormData - browser sets it with boundary
            ...options
        };
        
        return this.request(url, uploadOptions);
    }
}

// Create a global instance for easy use throughout the application
const api = new ApiClient();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ApiClient, api };
}

// Global availability
if (typeof window !== 'undefined') {
    window.ApiClient = ApiClient;
    window.api = api;
}
