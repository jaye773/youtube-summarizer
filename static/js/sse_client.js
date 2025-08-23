/**
 * SSE Client - Server-Sent Events connection handling with exponential backoff
 * Part of Module 4: Client-Side JavaScript for YouTube Summarizer Async Worker System
 */

class SSEClient {
    constructor(endpoint = '/events') {
        this.endpoint = endpoint;
        this.eventSource = null;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Maximum 30 seconds
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.isConnected = false;
        this.isReconnecting = false;
        this.eventHandlers = new Map();
        this.connectionId = this.generateConnectionId();
        
        // Bind methods to maintain context
        this.connect = this.connect.bind(this);
        this.disconnect = this.disconnect.bind(this);
        this.handleOpen = this.handleOpen.bind(this);
        this.handleError = this.handleError.bind(this);
        this.handleMessage = this.handleMessage.bind(this);
    }

    /**
     * Generate unique connection ID for tracking
     */
    generateConnectionId() {
        return `sse_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Connect to SSE endpoint with automatic retry logic
     */
    connect() {
        if (this.eventSource && this.eventSource.readyState === EventSource.OPEN) {
            console.log('🔗 SSE: Already connected');
            return;
        }

        if (this.isReconnecting) {
            console.log('🔄 SSE: Connection attempt already in progress');
            return;
        }

        try {
            console.log(`🚀 SSE: Connecting to ${this.endpoint}...`);
            this.disconnect(); // Clean up any existing connection
            
            // Add connection ID as query parameter for tracking
            const url = `${this.endpoint}?client_id=${this.connectionId}`;
            this.eventSource = new EventSource(url);
            
            this.setupEventHandlers();
        } catch (error) {
            console.error('❌ SSE: Failed to create EventSource:', error);
            this.handleReconnect();
        }
    }

    /**
     * Set up event handlers for EventSource
     */
    setupEventHandlers() {
        if (!this.eventSource) return;

        this.eventSource.addEventListener('open', this.handleOpen);
        this.eventSource.addEventListener('error', this.handleError);
        this.eventSource.addEventListener('message', this.handleMessage);

        // Register custom event handlers
        this.eventSource.addEventListener('summary_progress', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('📊 SSE: Progress update received:', data);
                
                // Update job tracker
                if (window.JobTracker) {
                    window.JobTracker.updateProgress(data);
                }
                
                // Trigger custom handlers
                this.triggerHandler('summary_progress', data);
            } catch (error) {
                console.error('❌ SSE: Error parsing progress event:', error);
            }
        });

        this.eventSource.addEventListener('summary_complete', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('✅ SSE: Summary completed:', data);
                
                // Update UI
                if (window.UIUpdater) {
                    window.UIUpdater.addCompletedSummary(data);
                }
                
                // Update job tracker
                if (window.JobTracker) {
                    window.JobTracker.completeJob(data.job_id, data);
                }
                
                // Trigger custom handlers
                this.triggerHandler('summary_complete', data);
            } catch (error) {
                console.error('❌ SSE: Error parsing completion event:', error);
            }
        });

        // System events
        this.eventSource.addEventListener('system', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('🔔 SSE: System event:', data);
                this.triggerHandler('system', data);
            } catch (error) {
                console.error('❌ SSE: Error parsing system event:', error);
            }
        });

        // Connection established event
        this.eventSource.addEventListener('connected', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('🔗 SSE: Connection acknowledged by server:', data);
                this.triggerHandler('connected', data);
            } catch (error) {
                console.error('❌ SSE: Error parsing connected event:', error);
            }
        });

        // Keep-alive pings
        this.eventSource.addEventListener('ping', (event) => {
            console.log('💓 SSE: Keep-alive ping received');
            this.triggerHandler('ping', { timestamp: Date.now() });
        });
    }

    /**
     * Handle successful connection
     */
    handleOpen(event) {
        console.log('✅ SSE: Connection opened successfully');
        this.isConnected = true;
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000; // Reset delay
        
        // Update connection status
        this.updateConnectionStatus(true);
        
        // Trigger connection event
        this.triggerHandler('connection_open', { 
            connectionId: this.connectionId,
            timestamp: Date.now()
        });
    }

    /**
     * Handle connection errors with exponential backoff retry
     */
    handleError(event) {
        console.error('❌ SSE: Connection error:', event);
        this.isConnected = false;
        
        // Update connection status
        this.updateConnectionStatus(false);
        
        if (this.eventSource) {
            if (this.eventSource.readyState === EventSource.CLOSED) {
                console.log('🔄 SSE: Connection closed by server');
                this.handleReconnect();
            } else if (this.eventSource.readyState === EventSource.CONNECTING) {
                console.log('🔄 SSE: Attempting to reconnect...');
            }
        }
        
        // Trigger error event
        this.triggerHandler('connection_error', { 
            readyState: this.eventSource?.readyState,
            timestamp: Date.now()
        });
    }

    /**
     * Handle generic messages
     */
    handleMessage(event) {
        console.log('📨 SSE: Generic message received:', event.data);
        try {
            const data = JSON.parse(event.data);
            this.triggerHandler('message', data);
        } catch (error) {
            // Not JSON, trigger as raw message
            this.triggerHandler('message', event.data);
        }
    }

    /**
     * Handle reconnection with exponential backoff
     */
    handleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('❌ SSE: Maximum reconnection attempts reached. Giving up.');
            this.triggerHandler('connection_failed', { 
                attempts: this.reconnectAttempts,
                maxAttempts: this.maxReconnectAttempts
            });
            return;
        }

        if (this.isReconnecting) {
            return; // Already trying to reconnect
        }

        this.isReconnecting = true;
        this.reconnectAttempts++;
        
        // Calculate exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 
            this.maxReconnectDelay
        );
        
        console.log(`🔄 SSE: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        // Trigger reconnect event
        this.triggerHandler('reconnecting', { 
            attempt: this.reconnectAttempts,
            delay: delay,
            maxAttempts: this.maxReconnectAttempts
        });
        
        setTimeout(() => {
            if (this.isReconnecting) {
                this.isReconnecting = false;
                this.connect();
            }
        }, delay);
    }

    /**
     * Disconnect and clean up
     */
    disconnect() {
        console.log('🔌 SSE: Disconnecting...');
        
        if (this.eventSource) {
            this.eventSource.removeEventListener('open', this.handleOpen);
            this.eventSource.removeEventListener('error', this.handleError);
            this.eventSource.removeEventListener('message', this.handleMessage);
            this.eventSource.close();
            this.eventSource = null;
        }
        
        this.isConnected = false;
        this.isReconnecting = false;
        this.updateConnectionStatus(false);
        
        // Trigger disconnect event
        this.triggerHandler('connection_closed', { 
            timestamp: Date.now()
        });
    }

    /**
     * Force reconnection (useful for debugging)
     */
    forceReconnect() {
        console.log('🔄 SSE: Forcing reconnection...');
        this.reconnectAttempts = 0;
        this.disconnect();
        setTimeout(() => this.connect(), 100);
    }

    /**
     * Add custom event handler
     */
    addEventListener(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, []);
        }
        this.eventHandlers.get(eventType).push(handler);
    }

    /**
     * Remove custom event handler
     */
    removeEventListener(eventType, handler) {
        if (this.eventHandlers.has(eventType)) {
            const handlers = this.eventHandlers.get(eventType);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    /**
     * Trigger custom event handlers
     */
    triggerHandler(eventType, data) {
        if (this.eventHandlers.has(eventType)) {
            this.eventHandlers.get(eventType).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`❌ SSE: Error in ${eventType} handler:`, error);
                }
            });
        }
    }

    /**
     * Update connection status indicator
     */
    updateConnectionStatus(connected) {
        // Try to find existing status indicator
        let statusIndicator = document.getElementById('sse-connection-status');
        
        if (!statusIndicator) {
            statusIndicator = this.createConnectionStatusIndicator();
        }
        
        statusIndicator.className = connected ? 
            'sse-connection-status connected' : 
            'sse-connection-status disconnected';
        
        statusIndicator.title = connected ? 
            'Real-time updates: Connected' : 
            'Real-time updates: Disconnected';
        
        // Update text content
        const statusText = statusIndicator.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    /**
     * Create connection status indicator if it doesn't exist
     */
    createConnectionStatusIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'sse-connection-status';
        indicator.className = 'sse-connection-status disconnected';
        indicator.innerHTML = `
            <span class="status-dot">●</span>
            <span class="status-text">Disconnected</span>
        `;
        
        // Try to add to header, fallback to body
        const header = document.querySelector('.header');
        if (header) {
            header.appendChild(indicator);
        } else {
            document.body.appendChild(indicator);
        }
        
        return indicator;
    }

    /**
     * Get current connection state
     */
    getConnectionState() {
        return {
            isConnected: this.isConnected,
            isReconnecting: this.isReconnecting,
            reconnectAttempts: this.reconnectAttempts,
            connectionId: this.connectionId,
            readyState: this.eventSource?.readyState,
            endpoint: this.endpoint
        };
    }

    /**
     * Check if SSE is supported by the browser
     */
    static isSupported() {
        return typeof EventSource !== 'undefined';
    }
}

// Export for use by other modules
window.SSEClient = SSEClient;

// Auto-initialize if EventSource is supported
if (typeof window !== 'undefined' && SSEClient.isSupported()) {
    console.log('🎯 SSE: SSEClient loaded and ready');
} else {
    console.warn('⚠️ SSE: EventSource not supported in this browser');
}