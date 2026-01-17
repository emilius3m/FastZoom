/**
 * FastZoom Voice Assistant Component
 * 
 * Alpine.js component for managing voice assistant interactions.
 * Communicates with the Pipecat backend via WebSocket.
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('voiceAssistant', () => ({
        // State
        isOpen: false,
        isConnected: false,
        isListening: false,
        isProcessing: false,
        isSpeaking: false,

        // Session
        sessionId: null,
        websocket: null,

        // Audio
        mediaRecorder: null,
        audioContext: null,
        audioChunks: [],

        // Recording for download
        recordingChunks: [],
        hasRecording: false,

        // UI
        statusMessage: 'Clicca per iniziare',
        transcript: '',
        response: '',
        messages: [],

        // Confirmation flow (new)
        pendingCommand: null,
        showConfirmation: false,
        confirmationQuestion: '',

        // Commands help modal
        showCommandsHelp: false,

        // Config
        wsUrl: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/pipecat/stream`,

        /**
         * Initialize the voice assistant
         */
        init() {
            // Check for browser support
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                console.warn('Voice assistant: MediaDevices API not supported');
                this.statusMessage = 'Microfono non supportato';
            }

            // Listen for keyboard shortcut (Ctrl+Shift+V)
            document.addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.shiftKey && e.key === 'V') {
                    e.preventDefault();
                    this.toggle();
                }
            });

            // Auto-reopen if was active before page navigation
            if (sessionStorage.getItem('voiceAssistantActive') === 'true') {
                console.log('🎤 Voice assistant: auto-reconnecting after navigation');
                // Small delay to let the page fully load
                setTimeout(() => this.open(), 500);
            }
        },

        /**
         * Toggle the voice assistant panel
         */
        toggle() {
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        },

        /**
         * Open the voice assistant
         */
        async open() {
            this.isOpen = true;
            sessionStorage.setItem('voiceAssistantActive', 'true');
            await this.connect();
        },

        /**
         * Close the voice assistant
         */
        close() {
            this.isOpen = false;
            sessionStorage.removeItem('voiceAssistantActive');
            this.disconnect();
            this.stopListening();
        },

        /**
         * Connect to WebSocket
         */
        async connect() {
            if (this.isConnected) return;

            this.statusMessage = 'Connessione...';

            try {
                this.websocket = new WebSocket(this.wsUrl);

                this.websocket.onopen = () => {
                    // Extract site_id from current URL (supports /view/ and /sites/)
                    const siteIdMatch = window.location.pathname.match(/\/(?:view|sites)\/([a-f0-9-]+)/i);
                    const siteId = siteIdMatch ? siteIdMatch[1] : null;

                    // Send init message with site context
                    if (this.websocket.readyState === WebSocket.OPEN) {
                        this.websocket.send(JSON.stringify({
                            type: 'init',
                            token: this.getAuthToken(),
                            site_id: siteId
                        }));
                    } else {
                        console.warn('WebSocket open but not ready, retrying in 100ms');
                        setTimeout(() => {
                            if (this.websocket.readyState === WebSocket.OPEN) {
                                this.websocket.send(JSON.stringify({
                                    type: 'init',
                                    token: this.getAuthToken(),
                                    site_id: siteId
                                }));
                            }
                        }, 100);
                    }
                };

                this.websocket.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                };

                this.websocket.onerror = (error) => {
                    console.error('Voice assistant WebSocket error:', error);
                    this.statusMessage = 'Errore di connessione';
                    this.isConnected = false;
                };

                this.websocket.onclose = () => {
                    this.isConnected = false;
                    this.statusMessage = 'Disconnesso';
                };

            } catch (error) {
                console.error('Failed to connect to voice assistant:', error);
                this.statusMessage = 'Impossibile connettersi';
            }
        },

        /**
         * Disconnect from WebSocket
         */
        disconnect() {
            if (this.websocket) {
                if (this.websocket.readyState === WebSocket.OPEN) {
                    this.websocket.send(JSON.stringify({ type: 'close' }));
                }
                this.websocket.close();
                this.websocket = null;
            }
            this.isConnected = false;
            this.sessionId = null;
        },

        /**
         * Handle incoming WebSocket messages
         */
        handleMessage(data) {
            switch (data.type) {
                case 'ready':
                    this.isConnected = true;
                    this.sessionId = data.session_id;
                    this.statusMessage = data.message || 'Pronto';
                    break;

                case 'error':
                    console.error('Voice assistant error:', data.message);
                    this.statusMessage = data.message;
                    this.addMessage('system', data.message, 'error');
                    break;

                case 'transcript':
                    this.transcript = data.text;
                    if (data.is_final) {
                        this.addMessage('user', data.text);
                    }
                    break;

                case 'command':
                    // Voice command - execute action
                    console.log('🎤 Voice command:', data);
                    this.executeVoiceCommand(data);
                    break;

                case 'response':
                    this.response = data.text;
                    this.addMessage('assistant', data.text);
                    this.isProcessing = false;
                    break;

                case 'audio':
                    // Play TTS audio
                    this.playAudio(data.data);
                    break;

                case 'function':
                    this.handleFunctionResult(data);
                    break;

                // New structured voice command message types
                case 'command_plan':
                    // Structured command plan from backend
                    console.log('🎤 Command plan:', data.plan);
                    this.handleCommandPlan(data.plan);
                    break;

                case 'ask_confirmation':
                    // Confirmation required for write operation
                    console.log('🎤 Confirmation requested:', data);
                    this.showConfirmationDialog(data.command, data.question);
                    break;

                case 'command_result':
                    // Execution result with UI actions
                    console.log('🎤 Command result:', data.result);
                    this.handleCommandResult(data.result);
                    break;

                case 'partial_transcript':
                    // Streaming partial transcript
                    this.transcript = data.text;
                    break;

                case 'final_transcript':
                    // Final transcript
                    this.transcript = data.text;
                    this.addMessage('user', data.text);
                    break;

                case 'audio_received':
                    // Audio chunk acknowledged
                    break;

                case 'pong':
                    // Keepalive response
                    break;
            }
        },

        /**
         * Execute voice command action
         */
        executeVoiceCommand(data) {
            const { action, path, target, query } = data;
            console.log(`Executing: ${action}`, { path, target, query });

            switch (action) {
                case 'navigate':
                    // Direct path navigation
                    if (path) {
                        window.location.href = path;
                    }
                    break;

                case 'go_back':
                    window.history.back();
                    break;

                case 'create':
                    // Get current site_id
                    const siteIdMatch = window.location.pathname.match(/\/view\/([a-f0-9-]+)/i);
                    const currentSiteId = siteIdMatch ? siteIdMatch[1] : null;

                    // Map targets to pages and events
                    const createTargets = {
                        'giornale': { page: '/giornale', event: 'open-new-giornale-modal' },
                        'photo': { page: '/photos', event: 'open-photo-upload-modal' },
                        'us': { page: null, event: 'open-new-us-modal' }
                    };

                    const targetConfig = createTargets[target];
                    if (!targetConfig) break;

                    // Check if we're already on the right page
                    const onCorrectPage = !targetConfig.page || window.location.pathname.includes(targetConfig.page);

                    if (onCorrectPage) {
                        // Already on the page - just dispatch the event
                        console.log(`Dispatching: ${targetConfig.event}`);
                        window.dispatchEvent(new CustomEvent(targetConfig.event));
                        this.$dispatch(targetConfig.event);
                    } else if (currentSiteId && targetConfig.page) {
                        // Navigate to the page with openModal param
                        const targetUrl = `/view/${currentSiteId}${targetConfig.page}?openModal=true`;
                        console.log(`Navigating to: ${targetUrl}`);
                        window.location.href = targetUrl;
                    }
                    break;

                case 'search':
                    if (query) {
                        // Navigate to photos with search query (most common)
                        const siteMatch = window.location.pathname.match(/\/view\/([a-f0-9-]+)/i);
                        if (siteMatch) {
                            window.location.href = `/view/${siteMatch[1]}/photos?search=${encodeURIComponent(query)}`;
                        }
                    }
                    break;

                case 'help':
                    // Help is displayed via response text, no action needed
                    break;
            }
        },

        /**
         * Handle function call results
         */
        handleFunctionResult(data) {
            const result = data.result;

            if (result.action === 'navigate') {
                // Navigate to a page
                window.location.href = result.url;
            } else if (result.action === 'create_giornale') {
                // Open giornale creation modal
                this.$dispatch('open-giornale-modal', result.data);
            }

            // Add message about the action
            if (result.message) {
                this.addMessage('assistant', result.message);
            }
        },

        /**
         * Start listening for voice input - RAW PCM VERSION
         */
        async startListening() {
            if (!this.isConnected) {
                await this.connect();
            }

            if (this.isListening) return;

            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        channelCount: 1,
                        sampleRate: 16000,
                        echoCancellation: true,
                        noiseSuppression: true
                    }
                });

                // Use AudioContext to get Raw PCM data
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 16000
                });

                const source = this.audioContext.createMediaStreamSource(stream);
                // Buffer size 4096 = ~256ms chunks
                this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

                this.processor.onaudioprocess = (e) => {
                    if (this.websocket?.readyState !== WebSocket.OPEN || !this.isListening) return;

                    const inputData = e.inputBuffer.getChannelData(0);
                    // Convert Float32 to Int16
                    const buffer = new ArrayBuffer(inputData.length * 2);
                    const view = new DataView(buffer);
                    for (let i = 0; i < inputData.length; i++) {
                        let s = Math.max(-1, Math.min(1, inputData[i]));
                        s = s < 0 ? s * 0x8000 : s * 0x7FFF;
                        view.setInt16(i * 2, s, true); // Little endian
                    }
                    this.websocket.send(buffer);
                };

                source.connect(this.processor);
                this.processor.connect(this.audioContext.destination);

                // Keep references to cleanup
                this.mediaStream = stream;

                // Setup MediaRecorder for download capability
                try {
                    this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                    this.recordingChunks = [];
                    this.mediaRecorder.ondataavailable = (e) => {
                        if (e.data.size > 0) {
                            this.recordingChunks.push(e.data);
                        }
                    };
                    this.mediaRecorder.onstop = () => {
                        if (this.recordingChunks.length > 0) {
                            this.hasRecording = true;
                        }
                    };
                    this.mediaRecorder.start();
                } catch (recErr) {
                    console.warn('MediaRecorder not supported:', recErr);
                }

                this.isListening = true;
                this.statusMessage = 'Sto ascoltando...';

            } catch (error) {
                console.error('Failed to access microphone:', error);
                if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                    this.statusMessage = 'Permesso negato. Controlla il browser.';
                } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
                    this.statusMessage = 'Nessun microfono trovato.';
                } else {
                    this.statusMessage = `Errore Mic: ${error.message}`;
                }
            }
        },

        /**
         * Stop listening
         */
        stopListening() {
            if (this.isListening) {
                // Stop MediaRecorder first
                if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
                    this.mediaRecorder.stop();
                }

                if (this.processor) {
                    this.processor.disconnect();
                    this.processor = null;
                }
                if (this.mediaStream) {
                    this.mediaStream.getTracks().forEach(track => track.stop());
                    this.mediaStream = null;
                }
                if (this.audioContext) {
                    this.audioContext.close();
                    this.audioContext = null;
                }
            }

            this.isListening = false;
            this.statusMessage = this.isConnected ? 'Pronto' : 'Disconnesso';
        },

        /**
         * Download the recorded audio
         */
        downloadRecording() {
            if (this.recordingChunks.length === 0) {
                console.warn('No recording available');
                return;
            }

            const blob = new Blob(this.recordingChunks, { type: 'audio/webm' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            a.download = `voice_recording_${timestamp}.webm`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            console.log('Recording downloaded');
        },

        /**
         * Clear recording
         */
        clearRecording() {
            this.recordingChunks = [];
            this.hasRecording = false;
        },

        /**
         * Toggle listening state
         */
        toggleListening() {
            if (this.isListening) {
                this.stopListening();
            } else {
                this.startListening();
            }
        },

        /**
         * Send text input (for testing without microphone)
         */
        sendText(text) {
            if (!this.isConnected || !text.trim()) return;

            this.isProcessing = true;
            this.addMessage('user', text);

            this.websocket.send(JSON.stringify({
                type: 'text',
                text: text.trim()
            }));

            this.transcript = '';
        },

        /**
         * Play audio from base64 data
         */
        async playAudio(base64Data) {
            this.isSpeaking = true;

            try {
                const audioData = atob(base64Data);
                const arrayBuffer = new ArrayBuffer(audioData.length);
                const view = new Uint8Array(arrayBuffer);
                for (let i = 0; i < audioData.length; i++) {
                    view[i] = audioData.charCodeAt(i);
                }

                const audioContext = new AudioContext();
                const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                const source = audioContext.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(audioContext.destination);
                source.onended = () => {
                    this.isSpeaking = false;
                };
                source.start();

            } catch (error) {
                console.error('Failed to play audio:', error);
                this.isSpeaking = false;
            }
        },

        /**
         * Add message to conversation history
         */
        addMessage(role, text, type = 'message') {
            this.messages.push({
                id: Date.now(),
                role,
                text,
                type,
                timestamp: new Date().toLocaleTimeString()
            });

            // Scroll to bottom
            this.$nextTick(() => {
                const container = this.$refs.messagesContainer;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            });
        },

        /**
         * Clear conversation history
         */
        clearMessages() {
            this.messages = [];
        },

        /**
         * Get auth token from cookie
         */
        getAuthToken() {
            const cookies = document.cookie.split(';');
            for (const cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'access_token') {
                    return value;
                }
            }
            return null;
        },

        /**
         * Get status icon based on current state
         */
        get statusIcon() {
            if (this.isSpeaking) return '🔊';
            if (this.isProcessing) return '🤔';
            if (this.isListening) return '🎤';
            if (this.isConnected) return '✅';
            return '💤';
        },

        /**
         * Get status color based on current state
         */
        get statusColor() {
            if (this.isSpeaking) return 'text-blue-500';
            if (this.isProcessing) return 'text-yellow-500';
            if (this.isListening) return 'text-red-500';
            if (this.isConnected) return 'text-green-500';
            return 'text-gray-500';
        },

        // =====================================================================
        // NEW: Structured Voice Command Handlers
        // =====================================================================

        /**
         * Handle structured command plan from backend
         */
        handleCommandPlan(plan) {
            if (!plan || !plan.command) return;

            const command = plan.command;

            // Check if confirmation required
            if (command.requires_confirmation) {
                this.showConfirmationDialog(command, command.explain);
            } else {
                // Execute immediately
                this.executeStructuredCommand(command, false);
            }
        },

        /**
         * Show confirmation dialog for write operations
         */
        showConfirmationDialog(command, question) {
            this.pendingCommand = command;
            this.confirmationQuestion = question || command.explain || 'Confermare questa operazione?';
            this.showConfirmation = true;
            this.addMessage('assistant', `⚠️ ${this.confirmationQuestion}`, 'confirmation');
        },

        /**
         * Confirm pending command
         */
        confirmCommand() {
            if (this.pendingCommand) {
                this.executeStructuredCommand(this.pendingCommand, true);
            }
            this.cancelConfirmation();
        },

        /**
         * Cancel pending confirmation
         */
        cancelConfirmation() {
            this.pendingCommand = null;
            this.showConfirmation = false;
            this.confirmationQuestion = '';
        },

        /**
         * Execute structured command via backend
         */
        async executeStructuredCommand(command, confirmed) {
            this.isProcessing = true;

            try {
                const response = await fetch('/api/v1/voice/execute', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        command: command,
                        site_id: this.getCurrentSiteId(),
                        confirmed: confirmed
                    })
                });

                const result = await response.json();
                this.handleCommandResult(result);

            } catch (error) {
                console.error('Voice command execution error:', error);
                this.addMessage('system', `Errore: ${error.message}`, 'error');
            }

            this.isProcessing = false;
        },

        /**
         * Handle command execution result with UI actions
         */
        handleCommandResult(result) {
            if (!result) return;

            // Show result message
            if (result.message) {
                this.addMessage('assistant', result.message, result.success ? 'success' : 'error');
            }

            if (result.error) {
                this.addMessage('system', `❌ ${result.error}`, 'error');
            }

            // Execute UI actions
            if (result.ui_actions && Array.isArray(result.ui_actions)) {
                result.ui_actions.forEach(action => this.executeUIAction(action));
            }

            this.isProcessing = false;
        },

        /**
         * Execute a single UI action
         */
        executeUIAction(action) {
            if (!action || !action.action) return;

            console.log('🎤 Executing UI action:', action);

            switch (action.action) {
                case 'navigate':
                    if (action.url) {
                        window.location.href = action.url;
                    }
                    break;

                case 'focus':
                    if (action.selector) {
                        const element = document.querySelector(action.selector);
                        if (element) {
                            element.focus();
                            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    }
                    break;

                case 'set_field':
                    if (action.selector && action.value !== undefined) {
                        const element = document.querySelector(action.selector);
                        if (element) {
                            element.value = action.value;
                            // Trigger input event for x-model sync
                            element.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }
                    break;

                case 'toast':
                    this.showToast(action.message, action.level || 'info');
                    break;

                case 'open_modal':
                    if (action.modal_name) {
                        window.dispatchEvent(new CustomEvent(`open-${action.modal_name}-modal`, {
                            detail: action.modal_data
                        }));
                    }
                    break;

                case 'close_modal':
                    window.dispatchEvent(new CustomEvent('close-modal'));
                    break;
            }
        },

        /**
         * Show toast notification
         */
        showToast(message, level = 'info') {
            // Use Alpine's toast system if available
            if (window.Alpine && window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent('toast', {
                    detail: { message, level }
                }));
            }

            // Fallback: add to messages
            this.addMessage('system', message, level);
        },

        /**
         * Get current site ID from URL
         */
        getCurrentSiteId() {
            const match = window.location.pathname.match(/\/(?:view|sites)\/([a-f0-9-]+)/i);
            return match ? match[1] : null;
        }
    }));
});
