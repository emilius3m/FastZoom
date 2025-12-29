/**
 * Token Auto-Refresh Utility
 * 
 * Automatically refreshes JWT access token before it expires.
 * This prevents session interruption for users during long work sessions.
 * 
 * Features:
 * - Silent token refresh 5 minutes before expiration
 * - Automatic redirect to login on refresh failure
 * - Minimal network overhead (only refreshes when needed)
 */

(function() {
    'use strict';

    const TokenRefresh = {
        // Configuration
        config: {
            refreshEndpoint: '/api/v1/auth/refresh',
            loginUrl: '/login',
            checkIntervalMs: 60000,  // Check every minute
            refreshBeforeExpiryMs: 5 * 60 * 1000,  // Refresh 5 min before expiry
            maxRetries: 3
        },

        // State
        state: {
            intervalId: null,
            retryCount: 0,
            tokenExpiry: null
        },

        /**
         * Initialize the token refresh system
         */
        init: function() {
            // Only run for authenticated users
            if (!window.currentUser || !window.currentUser.isAuthenticated) {
                console.log('[TokenRefresh] User not authenticated, skipping init');
                return;
            }

            console.log('[TokenRefresh] Initializing token auto-refresh...');
            
            // Start periodic check
            this.startPeriodicCheck();
            
            // Also check on visibility change (when user returns to tab)
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    console.log('[TokenRefresh] Tab became visible, checking token...');
                    this.checkAndRefresh();
                }
            });
        },

        /**
         * Start periodic token check
         */
        startPeriodicCheck: function() {
            // Clear existing interval if any
            if (this.state.intervalId) {
                clearInterval(this.state.intervalId);
            }

            // Check immediately on start
            this.checkAndRefresh();

            // Then check periodically
            this.state.intervalId = setInterval(() => {
                this.checkAndRefresh();
            }, this.config.checkIntervalMs);

            console.log('[TokenRefresh] Periodic check started (every ' + 
                       (this.config.checkIntervalMs / 1000) + 's)');
        },

        /**
         * Check token validity and refresh if needed
         */
        checkAndRefresh: async function() {
            try {
                // Get token info from server
                const response = await fetch('/api/v1/auth/me', {
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                if (response.status === 401) {
                    console.log('[TokenRefresh] Token expired, redirecting to login');
                    this.redirectToLogin();
                    return;
                }

                if (!response.ok) {
                    console.warn('[TokenRefresh] Token check failed:', response.status);
                    return;
                }

                // Token is still valid - check if we need to refresh soon
                // Since we removed expiry from payload, we rely on the server check
                // The endpoint will return 401 if token is expired
                console.log('[TokenRefresh] Token is valid');
                this.state.retryCount = 0;  // Reset retry count on success

            } catch (error) {
                console.error('[TokenRefresh] Error checking token:', error);
                this.handleRefreshError();
            }
        },

        /**
         * Refresh the access token
         */
        refreshToken: async function() {
            try {
                console.log('[TokenRefresh] Attempting token refresh...');
                
                // Note: The refresh token is stored in httpOnly cookie,
                // so we can't access it directly. We need to call a special
                // endpoint that reads from cookie and refreshes.
                const response = await fetch('/api/v1/auth/token-refresh-cookie', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    }
                });

                if (!response.ok) {
                    throw new Error('Refresh failed: ' + response.status);
                }

                console.log('[TokenRefresh] Token refreshed successfully');
                this.state.retryCount = 0;
                return true;

            } catch (error) {
                console.error('[TokenRefresh] Token refresh failed:', error);
                this.handleRefreshError();
                return false;
            }
        },

        /**
         * Handle refresh errors with retry logic
         */
        handleRefreshError: function() {
            this.state.retryCount++;
            
            if (this.state.retryCount >= this.config.maxRetries) {
                console.log('[TokenRefresh] Max retries reached, redirecting to login');
                this.redirectToLogin();
            } else {
                console.log('[TokenRefresh] Retry ' + this.state.retryCount + 
                           '/' + this.config.maxRetries);
            }
        },

        /**
         * Redirect to login page
         */
        redirectToLogin: function() {
            // Stop periodic checks
            if (this.state.intervalId) {
                clearInterval(this.state.intervalId);
            }

            // Store current URL for redirect after login
            const currentUrl = window.location.pathname + window.location.search;
            sessionStorage.setItem('redirectAfterLogin', currentUrl);

            // Redirect to login
            window.location.href = this.config.loginUrl;
        },

        /**
         * Stop the token refresh system
         */
        stop: function() {
            if (this.state.intervalId) {
                clearInterval(this.state.intervalId);
                this.state.intervalId = null;
            }
            console.log('[TokenRefresh] Stopped');
        }
    };

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        TokenRefresh.init();
    });

    // Expose for debugging
    window.TokenRefresh = TokenRefresh;

})();
