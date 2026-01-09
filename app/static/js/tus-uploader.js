/**
 * TUS Upload Client for FastZoom Archaeological System
 * Handles resumable file uploads with progress tracking
 * 
 * note: Authentication is handled automatically via HttpOnly cookies (credentials: 'include')
 */

class TusUploader {
    /**
     * @param {Object} config - Configuration object
     * @param {string} config.endpoint - TUS endpoint URL (e.g., '/api/v1/tus/uploads')
     * @param {number} config.chunkSize - Chunk size in bytes (default: 5MB)
     * @param {number} config.retryDelays - Array of retry delays in ms
     */
    constructor(config) {
        this.endpoint = config.endpoint || '/api/v1/tus/uploads';
        this.chunkSize = config.chunkSize || 5 * 1024 * 1024; // 5MB default
        this.retryDelays = config.retryDelays || [0, 1000, 3000, 5000, 10000];
        this.uploads = new Map(); // Track active uploads
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

            // Process the uploaded file (bridge to MinIO/DB)
            console.log('Upload complete, triggering processing...');
            const serverUploadId = uploadUrl.split('/').pop();
            const processResult = await this.processUpload(serverUploadId, metadata);

            // Success
            if (options.onSuccess) {
                options.onSuccess(uploadId, uploadUrl, processResult);
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
     * Process completed upload
     */
    async processUpload(uploadId, metadata) {
        // Extract site_id and other metadata
        const payload = {
            upload_id: uploadId,
            site_id: metadata.site_id, // Ensure this maps correctly from options.metadata
            archaeological_metadata: {
                ...metadata,
                site_id: undefined, // Remove from nested dict to avoid duplication
                filename: undefined,
                filetype: undefined,
                size: undefined
            }
        };

        const response = await fetch('/api/v1/photos/from-tus', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload),
            credentials: 'include'
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Processing failed: ${response.status} ${response.statusText} - ${errorText}`);
        }

        return await response.json();
    }

    /**
     * Create upload session
     */
    async createUpload(fileSize, metadata) {
        console.log('Creating upload with cookies (HttpOnly mode)');

        // Encode metadata as base64
        const encodedMetadata = Object.entries(metadata)
            .map(([key, value]) => {
                const encodedValue = btoa(String(value));
                return `${key} ${encodedValue}`;
            })
            .join(',');

        const headers = {
            'Upload-Length': String(fileSize),
            'Upload-Metadata': encodedMetadata,
            'Tus-Resumable': '1.0.0'
        };

        console.log('Request headers:', headers);

        const response = await fetch(this.endpoint, {
            method: 'POST',
            headers: headers,
            credentials: 'include'  // Send HttpOnly cookies automatically
        });

        console.log('Response status:', response.status);

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
        const response = await fetch(uploadUrl, {
            method: 'HEAD',
            headers: {
                'Tus-Resumable': '1.0.0'
            },
            credentials: 'include'  // Send HttpOnly cookies automatically
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
        const response = await fetch(uploadUrl, {
            method: 'PATCH',
            headers: {
                'Upload-Offset': String(offset),
                'Content-Type': 'application/offset+octet-stream',
                'Tus-Resumable': '1.0.0'
            },
            body: chunkData,
            credentials: 'include'  // Send HttpOnly cookies automatically
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
                    await fetch(controller.uploadUrl, {
                        method: 'DELETE',
                        headers: {
                            'Tus-Resumable': '1.0.0'
                        },
                        credentials: 'include'
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
            const progressUrl = `${controller.uploadUrl}/progress`;

            const response = await fetch(progressUrl, {
                credentials: 'include'
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
}
