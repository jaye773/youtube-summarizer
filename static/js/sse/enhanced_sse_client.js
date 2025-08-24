/**
 * Enhanced SSE Client with reliability features
 * - Exponential backoff reconnection
 * - Heartbeat handling
 * - Gzip decompression support
 * - Connection status monitoring
 * - Graceful error handling
 */

class EnhancedSSEClient {
    constructor(url = '/sse', options = {}) {
        this.url = url;
        this.options = {
            maxRetries: 10,
            baseDelay: 1000,
            maxDelay: 30000,
            heartbeatInterval: 30000,
            ...options
        };
        
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.reconnectTimer = null;
        this.lastHeartbeat = null;
        this.heartbeatTimer = null;
        this.isConnected = false;
        this.isReconnecting = false;
        
        this.eventHandlers = new Map();
        
        this.init();
    }

    init() {
        this.connect();
        this.setupHeartbeatMonitoring();
    }

    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.updateConnectionStatus('connecting');
        this.eventSource = new EventSource(this.url);
        
        this.eventSource.onopen = (event) => {
            console.log('SSE connection opened');
            this.isConnected = true;
            this.isReconnecting = false;
            this.reconnectAttempts = 0;
            this.lastHeartbeat = Date.now();
            this.updateConnectionStatus('connected');
            this.emit('connected', event);
        };

        this.eventSource.onmessage = (event) => {
            this.handleMessage(event);
        };

        this.eventSource.onerror = (event) => {
            console.warn('SSE connection error:', event);
            this.isConnected = false;
            
            if (event.target.readyState === EventSource.CLOSED) {
                this.updateConnectionStatus('disconnected');
                this.scheduleReconnect();
            }
            
            this.emit('error', event);
        };

        this.eventSource.onclose = (event) => {
            console.log('SSE connection closed');
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');
            this.emit('closed', event);
        };
    }

    handleMessage(event) {
        try {
            let data = event.data;
            
            // Handle gzip-compressed messages
            if (this.isGzipCompressed(data)) {
                data = this.decompressGzip(data);
            }

            const messageData = JSON.parse(data);
            
            // Handle heartbeat messages
            if (messageData.type === 'heartbeat') {
                this.lastHeartbeat = Date.now();
                console.debug('Heartbeat received');
                return;
            }

            // Emit custom event based on message type
            const eventType = messageData.type || 'message';
            this.emit(eventType, messageData);

        } catch (error) {
            console.error('Failed to parse SSE message:', error);
            this.emit('parseError', { error, data: event.data });
        }
    }

    isGzipCompressed(data) {
        // Simple heuristic: check for gzip magic number in base64
        return data.startsWith('H4sI') || data.startsWith('1f8b');
    }

    decompressGzip(compressedData) {
        try {
            // For browser compatibility, use pako library if available
            if (typeof pako !== 'undefined') {
                const binaryString = atob(compressedData);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                return pako.inflate(bytes, { to: 'string' });
            }
            
            // Fallback: assume data is not compressed
            return compressedData;
        } catch (error) {
            console.error('Failed to decompress gzip data:', error);
            return compressedData;
        }
    }

    scheduleReconnect() {
        if (this.isReconnecting || this.reconnectAttempts >= this.options.maxRetries) {
            if (this.reconnectAttempts >= this.options.maxRetries) {
                this.updateConnectionStatus('failed');
                this.emit('maxRetriesReached');
            }
            return;
        }

        this.isReconnecting = true;
        this.reconnectAttempts++;
        
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
        const delay = Math.min(
            this.options.baseDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.options.maxDelay
        );

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.options.maxRetries})`);
        this.updateConnectionStatus('reconnecting', { attempt: this.reconnectAttempts, delay });

        this.reconnectTimer = setTimeout(() => {
            this.connect();
        }, delay);
    }

    setupHeartbeatMonitoring() {
        this.heartbeatTimer = setInterval(() => {
            if (!this.isConnected || !this.lastHeartbeat) return;

            const timeSinceHeartbeat = Date.now() - this.lastHeartbeat;
            if (timeSinceHeartbeat > this.options.heartbeatInterval * 2) {
                console.warn('Heartbeat timeout, forcing reconnection');
                this.forceReconnect();
            }
        }, this.options.heartbeatInterval);
    }

    forceReconnect() {
        this.reconnectAttempts = 0;
        this.isReconnecting = false;
        this.connect();
    }

    updateConnectionStatus(status, details = {}) {
        const statusElement = document.getElementById('connection-status');
        if (!statusElement) return;

        statusElement.className = `connection-status ${status}`;
        
        const messages = {
            connecting: 'Connecting...',
            connected: 'Connected',
            disconnected: 'Disconnected',
            reconnecting: `Reconnecting... (${details.attempt}/${this.options.maxRetries})`,
            failed: 'Connection Failed'
        };

        statusElement.textContent = messages[status] || status;
        statusElement.title = JSON.stringify({ status, ...details, timestamp: new Date().toISOString() });
    }

    // Event handling
    on(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, []);
        }
        this.eventHandlers.get(eventType).push(handler);
    }

    off(eventType, handler) {
        const handlers = this.eventHandlers.get(eventType);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    emit(eventType, data) {
        const handlers = this.eventHandlers.get(eventType);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in event handler for ${eventType}:`, error);
                }
            });
        }
    }

    // Status getters
    getStatus() {
        return {
            isConnected: this.isConnected,
            isReconnecting: this.isReconnecting,
            reconnectAttempts: this.reconnectAttempts,
            lastHeartbeat: this.lastHeartbeat,
            readyState: this.eventSource?.readyState
        };
    }

    // Manual control
    disconnect() {
        console.log('Manually disconnecting SSE');
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        this.isConnected = false;
        this.isReconnecting = false;
        this.updateConnectionStatus('disconnected');
    }

    reconnect() {
        this.reconnectAttempts = 0;
        this.isReconnecting = false;
        this.connect();
    }
}

// Export for both ES6 modules and global usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EnhancedSSEClient;
} else {
    window.EnhancedSSEClient = EnhancedSSEClient;
}