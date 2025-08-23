/**
 * SSE Manager - Handles Server-Sent Events for async summary processing
 * Provides EventSource integration, connection management, and fallback strategies
 */

class SSEManager {
    constructor() {
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.isConnected = false;
        this.subscribers = new Map();
        this.connectionTimeout = null;
        this.heartbeatInterval = null;
        this.lastHeartbeat = null;
        
        // Auto-connect on creation
        this.connect();
    }

    /**
     * Connect to SSE endpoint with automatic retry logic
     */
    connect() {
        try {
            // Clean up existing connection
            this.disconnect();
            
            console.log('🔗 Attempting SSE connection...');
            this.eventSource = new EventSource('/sse/summary-updates');
            
            // Connection opened
            this.eventSource.onopen = (event) => {
                console.log('✅ SSE connection established');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.reconnectDelay = 1000;
                this.notifySubscribers('connection', { status: 'connected' });
                
                // Start heartbeat monitoring
                this.startHeartbeat();
            };

            // Handle messages
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.warn('⚠️ Failed to parse SSE message:', error, event.data);
                }
            };

            // Handle connection errors
            this.eventSource.onerror = (event) => {
                console.warn('⚠️ SSE connection error:', event);
                this.isConnected = false;
                this.stopHeartbeat();
                
                if (this.eventSource.readyState === EventSource.CLOSED) {
                    this.notifySubscribers('connection', { status: 'disconnected' });
                    this.scheduleReconnect();
                }
            };

            // Set connection timeout
            this.connectionTimeout = setTimeout(() => {
                if (!this.isConnected) {
                    console.warn('⚠️ SSE connection timeout');
                    this.disconnect();
                    this.scheduleReconnect();
                }
            }, 10000); // 10 second timeout

        } catch (error) {
            console.error('❌ Failed to establish SSE connection:', error);
            this.scheduleReconnect();
        }
    }

    /**
     * Handle incoming SSE messages
     */
    handleMessage(data) {
        console.log('📨 SSE message received:', data);
        
        switch (data.type) {
            case 'heartbeat':
                this.lastHeartbeat = Date.now();
                break;
                
            case 'summary_started':
                this.notifySubscribers('summaryStarted', data);
                break;
                
            case 'summary_progress':
                this.notifySubscribers('summaryProgress', data);
                break;
                
            case 'summary_completed':
                this.notifySubscribers('summaryCompleted', data);
                break;
                
            case 'summary_failed':
                this.notifySubscribers('summaryFailed', data);
                break;
                
            case 'cache_updated':
                this.notifySubscribers('cacheUpdated', data);
                break;
                
            default:
                console.warn('⚠️ Unknown SSE message type:', data.type);
        }
    }

    /**
     * Subscribe to SSE events
     */
    subscribe(eventType, callback) {
        if (!this.subscribers.has(eventType)) {
            this.subscribers.set(eventType, new Set());
        }
        this.subscribers.get(eventType).add(callback);
        
        return () => this.unsubscribe(eventType, callback);
    }

    /**
     * Unsubscribe from SSE events
     */
    unsubscribe(eventType, callback) {
        if (this.subscribers.has(eventType)) {
            this.subscribers.get(eventType).delete(callback);
        }
    }

    /**
     * Notify all subscribers of an event
     */
    notifySubscribers(eventType, data) {
        if (this.subscribers.has(eventType)) {
            this.subscribers.get(eventType).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error('❌ Error in SSE subscriber callback:', error);
                }
            });
        }
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('❌ Max SSE reconnection attempts reached');
            this.notifySubscribers('connection', { status: 'failed' });
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`🔄 Scheduling SSE reconnection attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }

    /**
     * Start heartbeat monitoring
     */
    startHeartbeat() {
        this.lastHeartbeat = Date.now();
        this.heartbeatInterval = setInterval(() => {
            const now = Date.now();
            const timeSinceLastHeartbeat = now - this.lastHeartbeat;
            
            // If no heartbeat for 30 seconds, consider connection dead
            if (timeSinceLastHeartbeat > 30000) {
                console.warn('⚠️ SSE heartbeat timeout, reconnecting...');
                this.disconnect();
                this.scheduleReconnect();
            }
        }, 10000); // Check every 10 seconds
    }

    /**
     * Stop heartbeat monitoring
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    /**
     * Disconnect from SSE
     */
    disconnect() {
        if (this.connectionTimeout) {
            clearTimeout(this.connectionTimeout);
            this.connectionTimeout = null;
        }
        
        this.stopHeartbeat();
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        this.isConnected = false;
    }

    /**
     * Get connection status
     */
    getStatus() {
        return {
            isConnected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            readyState: this.eventSource?.readyState || EventSource.CLOSED
        };
    }

    /**
     * Force reconnection
     */
    forceReconnect() {
        console.log('🔄 Forcing SSE reconnection...');
        this.reconnectAttempts = 0;
        this.connect();
    }
}

// Export for ES6 modules or global usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SSEManager;
} else {
    window.SSEManager = SSEManager;
}