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

        // UI
        statusMessage: 'Clicca per iniziare',
        transcript: '',
        response: '',
        messages: [],

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
            await this.connect();
        },

        /**
         * Close the voice assistant
         */
        close() {
            this.isOpen = false;
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
                    // Send init message
                    this.websocket.send(JSON.stringify({
                        type: 'init',
                        token: this.getAuthToken()
                    }));
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

                case 'audio_received':
                    // Audio chunk acknowledged
                    break;

                case 'pong':
                    // Keepalive response
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
         * Start listening for voice input
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

                this.audioContext = new AudioContext({ sampleRate: 16000 });

                this.mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm;codecs=opus'
                });

                this.mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0 && this.websocket?.readyState === WebSocket.OPEN) {
                        // Send audio chunk
                        this.websocket.send(event.data);
                    }
                };

                this.mediaRecorder.start(100); // Send chunks every 100ms
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
            if (this.mediaRecorder && this.isListening) {
                this.mediaRecorder.stop();
                this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
                this.mediaRecorder = null;
            }

            if (this.audioContext) {
                this.audioContext.close();
                this.audioContext = null;
            }

            this.isListening = false;
            this.statusMessage = this.isConnected ? 'Pronto' : 'Disconnesso';
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
        }
    }));
});
