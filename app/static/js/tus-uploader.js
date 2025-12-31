/**
 * TUS Upload Client for FastZoom Archaeological System
 * Handles resumable file uploads with progress tracking
 */

class TusUploader {
    /**
     * @param {Object} config - Configuration object
     * @param {string} config.endpoint - TUS endpoint URL (e.g., '/api/v1/tus/uploads')
     * @param {Function} config.getAuthToken - Function that returns the auth token
     * @param {number} config.chunkSize - Chunk size in bytes (default: 5MB)
     * @param {number} config.retryDelays - Array of retry delays in ms
     */
    constructor(config) {
        this.endpoint = config.endpoint || '/api/v1/tus/uploads';
        this.getAuthToken = config.getAuthToken || (() => this.getTokenFromCookie());
        this.chunkSize = config.chunkSize || 5 * 1024 * 1024; // 5MB default
        this.retryDelays = config.retryDelays || [0, 1000, 3000, 5000, 10000];
        this.uploads = new Map(); // Track active uploads
    }

    /**
     * Get auth token from cookie
     */
    getTokenFromCookie() {
        const cookies = document.cookie.split(';');
        console.log('All cookies:', document.cookie);
        
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            console.log(`Checking cookie: ${name} = ${value}`);
            
            if (name === 'access_token') {
                let token = value;
                // Remove Bearer prefix if present
                if (token.startsWith('Bearer ')) {
                    token = token.substring(7);
                }
                // Handle URL-encoded Bearer prefix
                if (token.startsWith('Bearer%20')) {
                    token = token.substring(10);
                }
                console.log('Found token:', token.substring(0, 20) + '...');
                return token;
            }
        }
        
        console.warn('No access_token cookie found');
        return null;
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        const token = this.getAuthToken();
        return token !== null && token !== undefined && token !== '';
    }

    /**
     * Upload a file with TUS protocol
     * @param {File} file - File to upload
     * @param {Object} options - Upload options
     * @param {Object} options.metadata - Additional metadata
     * @param {Function} options.onProgress - Progress callback (bytesUploaded, bytesTotal)
     * @param {Function} options.onSuccess - Success callback (uploadId, uploadUrl)
     * @param {Function} options.onError - Error callback (error)
     * @param {Function} options.onPause - Pause callback
     * @param {Function} options.onResume - Resume callback
     * @returns {Object} Upload controller with pause/resume/abort methods
     */
    async upload(file, options = {}) {
        const uploadId = this.generateUploadId();
        const metadata = {
            filename: file.name,
            filetype: file.type,
            size: file.size,
            ...options.metadata
        };

        const controller = {
            uploadId,
            file,
            offset: 0,
            uploadUrl: null,
            isPaused: false,
            isAborted: false,
            retryCount: 0,
            pause: () => this.pauseUpload(uploadId),
            resume: () => this.resumeUpload(uploadId),
            abort: () => this.abortUpload(uploadId),
            getProgress: () => this.getProgress(uploadId)
        };

        this.uploads.set(uploadId, controller);

        try {
            // Create upload session
            const uploadUrl = await this.createUpload(file.size, metadata);
            controller.uploadUrl = uploadUrl;

            // Start uploading chunks
            await this.uploadChunks(controller, options);

            // Success
            if (options.onSuccess) {
                options.onSuccess(uploadId, uploadUrl);
            }

            return controller;

        } catch (error) {
            if (options.onError) {
                options.onError(error);
            }
            throw error;
        }
    }

    /**
     * Create upload session
     */
    async createUpload(fileSize, metadata) {
        const token = await this.getAuthToken();
        
        if (!token) {
            throw new Error('No authentication token available. Please login first.');
        }
        
        console.log('Creating upload with token:', token.substring(0, 20) + '...');
        
        // Encode metadata as base64
        const encodedMetadata = Object.entries(metadata)
            .map(([key, value]) => {
                const encodedValue = btoa(String(value));
                return `${key} ${encodedValue}`;
            })
            .join(',');

        const headers = {
            'Authorization': `Bearer ${token}`,
            'Upload-Length': String(fileSize),
            'Upload-Metadata': encodedMetadata,
            'Tus-Resumable': '1.0.0'
        };
        
        console.log('Request headers:', headers);

        const response = await fetch(this.endpoint, {
            method: 'POST',
            headers: headers
        });

        console.log('Response status:', response.status);
        console.log('Response headers:', Object.fromEntries(response.headers.entries()));

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error response:', errorText);
            throw new Error(`Failed to create upload: ${response.status} ${response.statusText} - ${errorText}`);
        }

        const location = response.headers.get('Location');
        if (!location) {
            throw new Error('No Location header in response');
        }

        return location;
    }

    /**
     * Upload file chunks
     */
    async uploadChunks(controller, options) {
        const { file, uploadUrl } = controller;
        let offset = await this.getOffset(uploadUrl);
        controller.offset = offset;

        while (offset < file.size && !controller.isAborted) {
            if (controller.isPaused) {
                await this.sleep(100);
                continue;
            }

            try {
                const chunk = file.slice(offset, offset + this.chunkSize);
                const chunkData = await this.readChunk(chunk);

                offset = await this.uploadChunk(uploadUrl, chunkData, offset);
                controller.offset = offset;

                // Progress callback
                if (options.onProgress) {
                    options.onProgress(offset, file.size);
                }

                // Reset retry count on success
                controller.retryCount = 0;

            } catch (error) {
                // Retry logic
                if (controller.retryCount < this.retryDelays.length) {
                    const delay = this.retryDelays[controller.retryCount];
                    controller.retryCount++;
                    
                    console.warn(`Upload chunk failed, retrying in ${delay}ms...`, error);
                    await this.sleep(delay);
                    
                    // Re-check offset from server
                    offset = await this.getOffset(uploadUrl);
                    controller.offset = offset;
                } else {
                    throw error;
                }
            }
        }

        if (controller.isAborted) {
            throw new Error('Upload aborted');
        }
    }

    /**
     * Get current upload offset from server
     */
    async getOffset(uploadUrl) {
        const token = await this.getAuthToken();

        const response = await fetch(uploadUrl, {
            method: 'HEAD',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Tus-Resumable': '1.0.0'
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to get offset: ${response.statusText}`);
        }

        const offset = response.headers.get('Upload-Offset');
        return parseInt(offset, 10);
    }

    /**
     * Upload a single chunk
     */
    async uploadChunk(uploadUrl, chunkData, offset) {
        const token = await this.getAuthToken();

        const response = await fetch(uploadUrl, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Upload-Offset': String(offset),
                'Content-Type': 'application/offset+octet-stream',
                'Tus-Resumable': '1.0.0'
            },
            body: chunkData
        });

        if (!response.ok) {
            throw new Error(`Failed to upload chunk: ${response.statusText}`);
        }

        const newOffset = response.headers.get('Upload-Offset');
        return parseInt(newOffset, 10);
    }

    /**
     * Read chunk as ArrayBuffer
     */
    readChunk(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsArrayBuffer(blob);
        });
    }

    /**
     * Pause upload
     */
    pauseUpload(uploadId) {
        const controller = this.uploads.get(uploadId);
        if (controller) {
            controller.isPaused = true;
        }
    }

    /**
     * Resume upload
     */
    resumeUpload(uploadId) {
        const controller = this.uploads.get(uploadId);
        if (controller) {
            controller.isPaused = false;
        }
    }

    /**
     * Abort upload
     */
    async abortUpload(uploadId) {
        const controller = this.uploads.get(uploadId);
        if (controller) {
            controller.isAborted = true;
            
            // Delete upload on server
            if (controller.uploadUrl) {
                try {
                    const token = await this.getAuthToken();
                    await fetch(controller.uploadUrl, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${token}`,
                            'Tus-Resumable': '1.0.0'
                        }
                    });
                } catch (error) {
                    console.error('Failed to delete upload:', error);
                }
            }

            this.uploads.delete(uploadId);
        }
    }

    /**
     * Get upload progress
     */
    async getProgress(uploadId) {
        const controller = this.uploads.get(uploadId);
        if (!controller || !controller.uploadUrl) {
            return null;
        }

        try {
            const token = await this.getAuthToken();
            const progressUrl = `${controller.uploadUrl}/progress`;
            
            const response = await fetch(progressUrl, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                throw new Error(`Failed to get progress: ${response.statusText}`);
            }

            return await response.json();

        } catch (error) {
            console.error('Failed to get progress:', error);
            return {
                offset: controller.offset,
                upload_length: controller.file.size,
                progress_percent: (controller.offset / controller.file.size) * 100
            };
        }
    }

    /**
     * Generate unique upload ID
     */
    generateUploadId() {
        return `upload_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Sleep utility
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TusUploader;
}        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TusUploader;
}
