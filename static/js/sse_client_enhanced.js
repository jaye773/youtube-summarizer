/**
 * Enhanced SSE Client - Advanced Server-Sent Events connection handling
 * Part of Enhanced YouTube Summarizer Async Worker System
 * 
 * Features:
 * - Heartbeat monitoring with 30-second intervals
 * - Connection pooling awareness with IP-based limits
 * - Message decompression for gzip-compressed payloads
 * - Advanced exponential backoff reconnection (1s, 2s, 4s, 8s, 16s, max 30s)
 * - Connection health monitoring and metrics
 * - Graceful degradation and comprehensive error handling
 * - Performance monitoring and bandwidth optimization
 */

class EnhancedSSEClient {
    constructor(endpoint = '/events', options = {}) {
        this.endpoint = endpoint;
        this.options = {
            maxReconnectAttempts: 15,
            baseReconnectDelay: 1000,
            maxReconnectDelay: 30000,
            heartbeatTimeout: 45000, // 45 seconds timeout for heartbeat
            compressionSupport: true,
            metricsEnabled: true,
            debugMode: false,
            ...options
        };
        
        // Connection state
        this.eventSource = null;
        this.connectionId = this.generateConnectionId();
        this.isConnected = false;
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.connectionStartTime = null;
        
        // Heartbeat monitoring
        this.lastHeartbeat = null;
        this.heartbeatTimer = null;
        this.heartbeatMissed = 0;
        this.maxHeartbeatMissed = 3;
        
        // Event handling
        this.eventHandlers = new Map();
        this.messageQueue = [];
        this.processingQueue = false;
        
        // Metrics and monitoring
        this.metrics = this.initializeMetrics();
        this.healthStatus = 'unknown';
        this.bandwidthMonitor = new BandwidthMonitor();
        
        // Compression support
        this.compressionSupported = this.checkCompressionSupport();
        
        // Performance monitoring
        this.performanceObserver = new PerformanceMonitor();
        
        // Bind methods
        this.connect = this.connect.bind(this);
        this.disconnect = this.disconnect.bind(this);
        this.handleOpen = this.handleOpen.bind(this);
        this.handleError = this.handleError.bind(this);
        this.handleMessage = this.handleMessage.bind(this);
        
        this.log('Enhanced SSE Client initialized', this.options);
    }
    
    /**
     * Generate unique connection ID with enhanced entropy
     */
    generateConnectionId() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substr(2, 12);
        const performance = typeof window.performance !== 'undefined' ? 
            window.performance.now().toString(36).substr(2, 6) : '';
        return `sse_${timestamp}_${random}${performance}`;
    }
    
    /**
     * Initialize metrics collection
     */
    initializeMetrics() {
        return {
            connectionsAttempted: 0,
            connectionsSuccessful: 0,
            messagesReceived: 0,
            messagesProcessed: 0,
            messagesDropped: 0,
            bytesReceived: 0,
            bytesDecompressed: 0,
            heartbeatsReceived: 0,
            reconnections: 0,
            errors: [],
            compressionRatio: 0,
            averageLatency: 0,
            connectionUptime: 0,
            lastMetricsReset: Date.now()
        };
    }
    
    /**
     * Check if compression is supported
     */
    checkCompressionSupport() {
        try {
            // Check for CompressionStream API or other compression support
            return typeof CompressionStream !== 'undefined' || 
                   typeof window.pako !== 'undefined' ||
                   this.options.compressionSupport;
        } catch (e) {
            return false;
        }
    }
    
    /**
     * Connect with enhanced connection management
     */
    async connect() {
        if (this.eventSource && this.eventSource.readyState === EventSource.OPEN) {
            this.log('Already connected');
            return;
        }
        
        if (this.isReconnecting) {
            this.log('Connection attempt already in progress');
            return;
        }
        
        this.metrics.connectionsAttempted++;
        this.connectionStartTime = Date.now();
        
        try {
            this.log('Connecting to enhanced SSE endpoint...');
            await this.disconnect(); // Clean up existing connection
            
            // Build connection URL with enhanced parameters
            const url = this.buildConnectionURL();
            this.eventSource = new EventSource(url);
            
            this.setupEventHandlers();
            this.startHeartbeatMonitoring();
            
        } catch (error) {
            this.logError('Failed to create EventSource', error);
            this.handleConnectionFailure(error);
        }
    }
    
    /**
     * Build connection URL with advanced parameters
     */
    buildConnectionURL() {
        const params = new URLSearchParams({
            client_id: this.connectionId,
            compression: this.compressionSupported ? 'gzip' : 'none',
            heartbeat: 'enabled',
            metrics: this.options.metricsEnabled ? 'enabled' : 'disabled',
            version: '2.0'
        });
        
        return `${this.endpoint}?${params.toString()}`;
    }
    
    /**
     * Setup comprehensive event handlers
     */
    setupEventHandlers() {
        if (!this.eventSource) return;
        
        // Core EventSource events
        this.eventSource.addEventListener('open', this.handleOpen);
        this.eventSource.addEventListener('error', this.handleError);
        this.eventSource.addEventListener('message', this.handleMessage);
        
        // Enhanced SSE events
        this.setupEnhancedEventHandlers();
    }
    
    /**
     * Setup enhanced event handlers for new features
     */
    setupEnhancedEventHandlers() {
        // Connection established
        this.eventSource.addEventListener('connected', (event) => {
            try {
                const data = this.parseEventData(event.data);
                this.log('Enhanced connection established', data);
                
                // Store server configuration
                this.serverConfig = {
                    compressionEnabled: data.compression_enabled,
                    heartbeatInterval: data.heartbeat_interval,
                    maxConnections: data.max_connections
                };
                
                this.triggerHandler('enhanced_connected', data);
            } catch (error) {
                this.logError('Error parsing connected event', error);
            }
        });
        
        // Enhanced heartbeat handling
        this.eventSource.addEventListener('heartbeat', (event) => {
            try {
                const data = this.parseEventData(event.data);
                this.handleHeartbeat(data);
            } catch (error) {
                this.logError('Error parsing heartbeat', error);
            }
        });
        
        // Progress events with enhanced data
        this.eventSource.addEventListener('summary_progress', (event) => {
            try {
                const data = this.parseEventData(event.data);
                this.log('Enhanced progress update', data);
                
                this.metrics.messagesReceived++;
                this.updateBandwidthMetrics(event.data);
                
                // Enhanced progress handling with ETA
                if (window.JobTracker) {
                    window.JobTracker.updateProgress(data);
                }
                
                this.triggerHandler('summary_progress', data);
            } catch (error) {
                this.logError('Error parsing progress event', error);
                this.metrics.messagesDropped++;
            }
        });
        
        // Summary completion with enhanced metadata
        this.eventSource.addEventListener('summary_complete', (event) => {
            try {
                const data = this.parseEventData(event.data);
                this.log('Enhanced summary completed', data);
                
                this.metrics.messagesReceived++;
                this.updateBandwidthMetrics(event.data);
                
                if (window.UIUpdater) {
                    window.UIUpdater.addCompletedSummary(data);
                }
                
                if (window.JobTracker) {
                    window.JobTracker.completeJob(data.job_id, data);
                }
                
                this.triggerHandler('summary_complete', data);
            } catch (error) {
                this.logError('Error parsing completion event', error);
                this.metrics.messagesDropped++;
            }
        });
        
        // Enhanced system events
        this.eventSource.addEventListener('system', (event) => {
            try {
                const data = this.parseEventData(event.data);
                this.log('Enhanced system event', data);
                
                // Handle different system event categories
                this.handleSystemEvent(data);
                
                this.triggerHandler('system', data);
            } catch (error) {
                this.logError('Error parsing system event', error);
            }
        });
        
        // Health status events
        this.eventSource.addEventListener('health_status', (event) => {
            try {
                const data = this.parseEventData(event.data);
                this.updateHealthStatus(data);
                this.triggerHandler('health_status', data);
            } catch (error) {
                this.logError('Error parsing health status', error);
            }
        });
    }
    
    /**
     * Parse event data with decompression support
     */
    parseEventData(rawData) {
        try {
            const data = JSON.parse(rawData);
            
            // Check if data is compressed
            if (data.compressed && data.data) {
                return this.decompressMessage(data);
            }
            
            return data;
        } catch (error) {
            this.logError('Failed to parse event data', error);
            throw error;
        }
    }
    
    /**
     * Decompress gzip-compressed messages
     */
    decompressMessage(compressedData) {
        try {
            const { data: base64Data, original_size } = compressedData;
            
            // Decode base64
            const compressedBytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
            
            // Decompress (requires pako library or native compression API)
            let decompressedBytes;
            if (typeof window.pako !== 'undefined') {
                decompressedBytes = window.pako.inflate(compressedBytes);
            } else if (typeof DecompressionStream !== 'undefined') {
                // Use native API if available
                decompressedBytes = this.nativeDecompress(compressedBytes);
            } else {
                throw new Error('No decompression library available');
            }
            
            // Convert to string and parse JSON
            const decompressedString = new TextDecoder().decode(decompressedBytes);
            const originalData = JSON.parse(decompressedString);
            
            // Update metrics
            this.metrics.bytesReceived += compressedBytes.length;
            this.metrics.bytesDecompressed += decompressedString.length;
            this.metrics.compressionRatio = this.metrics.bytesReceived / this.metrics.bytesDecompressed;
            
            this.log('Message decompressed', {
                original_size,
                compressed_size: compressedBytes.length,
                compression_ratio: compressedBytes.length / original_size
            });
            
            return originalData;
            
        } catch (error) {
            this.logError('Failed to decompress message', error);
            throw error;
        }
    }
    
    /**
     * Handle successful connection with enhanced setup
     */
    handleOpen(event) {
        this.log('Enhanced connection opened successfully');
        
        this.isConnected = true;
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.metrics.connectionsSuccessful++;
        this.healthStatus = 'healthy';
        
        // Calculate connection time
        if (this.connectionStartTime) {
            const connectionTime = Date.now() - this.connectionStartTime;
            this.performanceObserver.recordConnectionTime(connectionTime);
        }
        
        // Update UI
        this.updateConnectionStatus(true);
        this.showConnectionNotification('Connected to enhanced real-time updates', 'success');
        
        // Start heartbeat monitoring
        this.resetHeartbeatTimer();
        
        // Trigger enhanced connection event
        this.triggerHandler('enhanced_connection_open', {
            connectionId: this.connectionId,
            timestamp: Date.now(),
            compressionSupported: this.compressionSupported,
            metrics: this.getMetricsSummary()
        });
    }
    
    /**
     * Handle connection errors with advanced error classification
     */
    handleError(event) {
        this.logError('Enhanced connection error', event);
        
        const errorInfo = this.classifyConnectionError(event);
        this.metrics.errors.push({
            timestamp: Date.now(),
            type: errorInfo.type,
            severity: errorInfo.severity,
            readyState: this.eventSource?.readyState
        });
        
        this.isConnected = false;
        this.healthStatus = 'error';
        this.updateConnectionStatus(false);
        
        // Handle different error scenarios
        if (this.eventSource) {
            if (this.eventSource.readyState === EventSource.CLOSED) {
                this.log('Connection closed by server - attempting reconnection');
                this.handleReconnection(errorInfo);
            } else if (this.eventSource.readyState === EventSource.CONNECTING) {
                this.log('Connection attempt in progress...');
            }
        }
        
        // Show user-friendly error notification
        this.showConnectionNotification(errorInfo.userMessage, 'error');
        
        // Trigger enhanced error event
        this.triggerHandler('enhanced_connection_error', {
            error: errorInfo,
            readyState: this.eventSource?.readyState,
            timestamp: Date.now(),
            willReconnect: this.shouldAttemptReconnection()
        });
    }
    
    /**
     * Classify connection errors for better handling
     */
    classifyConnectionError(event) {
        const readyState = this.eventSource?.readyState;
        
        if (readyState === EventSource.CLOSED) {
            return {
                type: 'connection_closed',
                severity: 'medium',
                userMessage: 'Connection lost - reconnecting...',
                shouldReconnect: true
            };
        }
        
        if (this.reconnectAttempts > this.options.maxReconnectAttempts / 2) {
            return {
                type: 'persistent_failure',
                severity: 'high',
                userMessage: 'Connection issues detected - please refresh if problems persist',
                shouldReconnect: true
            };
        }
        
        return {
            type: 'network_error',
            severity: 'low',
            userMessage: 'Network issue - reconnecting...',
            shouldReconnect: true
        };
    }
    
    /**
     * Handle heartbeat events with advanced monitoring
     */
    handleHeartbeat(data) {
        const now = Date.now();
        const latency = data.timestamp ? now - new Date(data.timestamp).getTime() : 0;
        
        this.lastHeartbeat = now;
        this.heartbeatMissed = 0;
        this.metrics.heartbeatsReceived++;
        
        // Update latency metrics
        if (latency > 0) {
            this.metrics.averageLatency = (this.metrics.averageLatency + latency) / 2;
            this.performanceObserver.recordLatency(latency);
        }
        
        // Update health status
        this.healthStatus = 'healthy';
        this.resetHeartbeatTimer();
        
        this.log('Heartbeat received', {
            latency,
            server_metrics: data.metrics,
            connection_count: data.connection_count
        });
        
        // Update connection uptime
        if (this.connectionStartTime) {
            this.metrics.connectionUptime = now - this.connectionStartTime;
        }
        
        this.triggerHandler('heartbeat', {
            ...data,
            client_latency: latency,
            client_metrics: this.getMetricsSummary()
        });
    }
    
    /**
     * Start heartbeat monitoring system
     */
    startHeartbeatMonitoring() {
        this.resetHeartbeatTimer();
    }
    
    /**
     * Reset heartbeat timer
     */
    resetHeartbeatTimer() {
        if (this.heartbeatTimer) {
            clearTimeout(this.heartbeatTimer);
        }
        
        this.heartbeatTimer = setTimeout(() => {
            this.handleHeartbeatTimeout();
        }, this.options.heartbeatTimeout);
    }
    
    /**
     * Handle heartbeat timeout with escalating responses
     */
    handleHeartbeatTimeout() {
        this.heartbeatMissed++;
        this.log(`Heartbeat timeout (${this.heartbeatMissed}/${this.maxHeartbeatMissed})`);
        
        if (this.heartbeatMissed >= this.maxHeartbeatMissed) {
            this.log('Multiple heartbeats missed - forcing reconnection');
            this.healthStatus = 'degraded';
            this.forceReconnect();
        } else {
            // Set a shorter timeout for next heartbeat check
            this.heartbeatTimer = setTimeout(() => {
                this.handleHeartbeatTimeout();
            }, this.options.heartbeatTimeout / 2);
        }
    }
    
    /**
     * Handle reconnection with advanced exponential backoff
     */
    handleReconnection(errorInfo) {
        if (!this.shouldAttemptReconnection()) {
            this.log('Maximum reconnection attempts reached - giving up');
            this.triggerHandler('connection_failed', {
                attempts: this.reconnectAttempts,
                maxAttempts: this.options.maxReconnectAttempts,
                finalError: errorInfo
            });
            return;
        }
        
        if (this.isReconnecting) {
            return;
        }
        
        this.isReconnecting = true;
        this.reconnectAttempts++;
        this.metrics.reconnections++;
        
        // Enhanced exponential backoff with jitter
        const baseDelay = this.options.baseReconnectDelay;
        const exponentialDelay = Math.min(
            baseDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.options.maxReconnectDelay
        );
        
        // Add jitter to prevent thundering herd
        const jitter = Math.random() * 0.3 * exponentialDelay;
        const totalDelay = exponentialDelay + jitter;
        
        this.log(`Reconnecting in ${Math.round(totalDelay)}ms (attempt ${this.reconnectAttempts}/${this.options.maxReconnectAttempts})`);
        
        // Update connection status with countdown
        this.showReconnectionCountdown(Math.round(totalDelay / 1000));
        
        // Trigger reconnection event
        this.triggerHandler('reconnecting', {
            attempt: this.reconnectAttempts,
            delay: totalDelay,
            maxAttempts: this.options.maxReconnectAttempts,
            errorInfo: errorInfo
        });
        
        setTimeout(() => {
            if (this.isReconnecting) {
                this.isReconnecting = false;
                this.connect();
            }
        }, totalDelay);
    }
    
    /**
     * Check if reconnection should be attempted
     */
    shouldAttemptReconnection() {
        return this.reconnectAttempts < this.options.maxReconnectAttempts;
    }
    
    /**
     * Handle system events with categorization
     */
    handleSystemEvent(data) {
        const { category, level, message } = data;
        
        switch (category) {
            case 'capacity':
                this.handleCapacityEvent(data);
                break;
            case 'performance':
                this.handlePerformanceEvent(data);
                break;
            case 'maintenance':
                this.handleMaintenanceEvent(data);
                break;
            default:
                this.log('System event', data);
        }
        
        // Show notification for important system events
        if (level === 'warning' || level === 'error') {
            this.showSystemNotification(message, level);
        }
    }
    
    /**
     * Handle capacity-related system events
     */
    handleCapacityEvent(data) {
        if (data.level === 'warning') {
            this.log('System approaching capacity limits', data);
            this.showConnectionNotification('System busy - you may experience delays', 'warning');
        }
    }
    
    /**
     * Handle performance-related system events
     */
    handlePerformanceEvent(data) {
        this.performanceObserver.recordSystemPerformance(data);
    }
    
    /**
     * Update bandwidth metrics
     */
    updateBandwidthMetrics(rawData) {
        const bytes = new Blob([rawData]).size;
        this.bandwidthMonitor.recordBytes(bytes);
        this.metrics.bytesReceived += bytes;
    }
    
    /**
     * Update health status
     */
    updateHealthStatus(statusData) {
        this.healthStatus = statusData.status;
        
        if (statusData.recommendations) {
            statusData.recommendations.forEach(rec => {
                this.log('Health recommendation', rec);
            });
        }
    }
    
    /**
     * Enhanced connection status indicator
     */
    updateConnectionStatus(connected) {
        let statusIndicator = document.getElementById('enhanced-sse-status');
        
        if (!statusIndicator) {
            statusIndicator = this.createEnhancedStatusIndicator();
        }
        
        const statusClass = this.getStatusClass(connected);
        const statusText = this.getStatusText(connected);
        const statusDetails = this.getStatusDetails();
        
        statusIndicator.className = `enhanced-sse-status ${statusClass}`;
        statusIndicator.title = `Real-time connection: ${statusText}\\n${statusDetails}`;
        
        // Update indicator content
        const dot = statusIndicator.querySelector('.status-dot');
        const text = statusIndicator.querySelector('.status-text');
        const metrics = statusIndicator.querySelector('.status-metrics');
        
        if (dot) dot.className = `status-dot ${statusClass}`;
        if (text) text.textContent = statusText;
        if (metrics) metrics.textContent = this.getMetricsText();
    }
    
    /**
     * Create enhanced status indicator
     */
    createEnhancedStatusIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'enhanced-sse-status';
        indicator.className = 'enhanced-sse-status disconnected';
        indicator.innerHTML = `
            <div class="status-main">
                <span class="status-dot">●</span>
                <span class="status-text">Connecting...</span>
            </div>
            <div class="status-metrics">Initializing...</div>
            <div class="status-actions">
                <button class="reconnect-btn" onclick="window.enhancedSSE?.forceReconnect()">Reconnect</button>
                <button class="metrics-btn" onclick="window.enhancedSSE?.showMetrics()">Metrics</button>
            </div>
        `;
        
        // Add theme-aware class based on current theme
        const currentTheme = this.getCurrentTheme();
        indicator.classList.add(`theme-${currentTheme}`);
        
        // Add to header or body
        const header = document.querySelector('.header') || document.body;
        header.appendChild(indicator);
        
        return indicator;
    }
    
    /**
     * Get status class based on connection state
     */
    getStatusClass(connected) {
        if (!connected) return 'disconnected';
        
        switch (this.healthStatus) {
            case 'healthy': return 'connected';
            case 'degraded': return 'warning';
            case 'error': return 'error';
            default: return 'connecting';
        }
    }
    
    /**
     * Get status text
     */
    getStatusText(connected) {
        if (!connected) {
            return this.isReconnecting ? 'Reconnecting...' : 'Disconnected';
        }
        
        switch (this.healthStatus) {
            case 'healthy': return 'Connected';
            case 'degraded': return 'Degraded';
            case 'error': return 'Error';
            default: return 'Connecting';
        }
    }
    
    /**
     * Get detailed status information
     */
    getStatusDetails() {
        const uptime = this.metrics.connectionUptime ? 
            `Uptime: ${Math.round(this.metrics.connectionUptime / 1000)}s` : '';
        const latency = this.metrics.averageLatency ? 
            `Latency: ${Math.round(this.metrics.averageLatency)}ms` : '';
        const compression = this.metrics.compressionRatio ? 
            `Compression: ${Math.round((1 - this.metrics.compressionRatio) * 100)}%` : '';
        
        return [uptime, latency, compression].filter(Boolean).join(' | ');
    }
    
    /**
     * Get metrics text for status indicator
     */
    getMetricsText() {
        if (!this.isConnected) return 'Disconnected';
        
        const msgs = this.metrics.messagesReceived;
        const bandwidth = this.bandwidthMonitor.getCurrentBandwidth();
        
        return `${msgs} msgs | ${this.formatBytes(bandwidth)}/s`;
    }
    
    /**
     * Show connection notification
     */
    showConnectionNotification(message, type = 'info') {
        // Implementation depends on notification system
        if (window.showToast) {
            window.showToast(message, type);
        } else if (window.UIUpdater && window.UIUpdater.showToast) {
            window.UIUpdater.showToast(message, type);
        } else {
            // Create theme-aware notification
            this.createThemeAwareNotification(message, type);
        }
    }
    
    /**
     * Create theme-aware notification
     */
    createThemeAwareNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `enhanced-notification enhanced-notification-${type}`;
        
        // Add theme-aware classes
        const currentTheme = this.getCurrentTheme();
        notification.classList.add(`theme-${currentTheme}`);
        
        notification.innerHTML = `
            <span class="notification-message">${this.escapeHtml(message)}</span>
            <button class="notification-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        // Add to toast container or body
        const container = document.getElementById('async-toast-container') || document.body;
        container.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
    
    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    /**
     * Show reconnection countdown
     */
    showReconnectionCountdown(seconds) {
        let countdown = seconds;
        const updateCountdown = () => {
            this.updateConnectionStatus(false);
            const text = document.querySelector('#enhanced-sse-status .status-text');
            if (text && countdown > 0) {
                text.textContent = `Reconnecting in ${countdown}s`;
                countdown--;
                setTimeout(updateCountdown, 1000);
            }
        };
        updateCountdown();
    }
    
    /**
     * Get comprehensive metrics summary
     */
    getMetricsSummary() {
        return {
            ...this.metrics,
            healthStatus: this.healthStatus,
            connectionId: this.connectionId,
            compressionSupported: this.compressionSupported,
            bandwidthCurrent: this.bandwidthMonitor.getCurrentBandwidth(),
            bandwidthAverage: this.bandwidthMonitor.getAverageBandwidth()
        };
    }
    
    /**
     * Show detailed metrics
     */
    showMetrics() {
        const metrics = this.getMetricsSummary();
        console.table(metrics);
        
        // Could also show in a modal or dedicated UI
        if (window.showMetricsModal) {
            window.showMetricsModal(metrics);
        }
    }
    
    /**
     * Force reconnection
     */
    forceReconnect() {
        this.log('Forcing reconnection...');
        this.reconnectAttempts = 0;
        this.disconnect();
        setTimeout(() => this.connect(), 100);
    }
    
    /**
     * Gracefully disconnect
     */
    async disconnect() {
        this.log('Disconnecting enhanced SSE client...');
        
        // Clear timers
        if (this.heartbeatTimer) {
            clearTimeout(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
        
        // Close EventSource
        if (this.eventSource) {
            this.eventSource.removeEventListener('open', this.handleOpen);
            this.eventSource.removeEventListener('error', this.handleError);
            this.eventSource.removeEventListener('message', this.handleMessage);
            this.eventSource.close();
            this.eventSource = null;
        }
        
        // Update state
        this.isConnected = false;
        this.isReconnecting = false;
        this.healthStatus = 'disconnected';
        this.updateConnectionStatus(false);
        
        // Trigger disconnect event
        this.triggerHandler('enhanced_connection_closed', {
            timestamp: Date.now(),
            metrics: this.getMetricsSummary()
        });
    }
    
    /**
     * Add event handler
     */
    addEventListener(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, []);
        }
        this.eventHandlers.get(eventType).push(handler);
    }
    
    /**
     * Remove event handler
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
     * Trigger event handlers
     */
    triggerHandler(eventType, data) {
        if (this.eventHandlers.has(eventType)) {
            this.eventHandlers.get(eventType).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    this.logError(`Error in ${eventType} handler`, error);
                }
            });
        }
    }
    
    /**
     * Enhanced logging
     */
    log(message, data = null) {
        if (this.options.debugMode) {
            const timestamp = new Date().toISOString();
            console.log(`[${timestamp}] Enhanced SSE:`, message, data || '');
        }
    }
    
    /**
     * Get current theme
     */
    getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || 'light';
    }
    
    /**
     * Update theme-dependent elements
     */
    updateDynamicElements(theme) {
        // Update status indicator classes to be theme-aware
        const statusIndicator = document.getElementById('enhanced-sse-status');
        if (statusIndicator) {
            // Remove any theme-specific classes and let CSS handle theming
            statusIndicator.classList.remove('theme-light', 'theme-dark');
            statusIndicator.classList.add(`theme-${theme}`);
        }
        
        // Update any dynamically created toast notifications
        document.querySelectorAll('.enhanced-toast').forEach(toast => {
            toast.classList.remove('theme-light', 'theme-dark');
            toast.classList.add(`theme-${theme}`);
        });
    }
    
    /**
     * Error logging
     */
    logError(message, error) {
        console.error('Enhanced SSE Error:', message, error);
    }
    
    /**
     * Format bytes for display
     */
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
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
            healthStatus: this.healthStatus,
            readyState: this.eventSource?.readyState,
            endpoint: this.endpoint,
            metrics: this.getMetricsSummary(),
            serverConfig: this.serverConfig
        };
    }
    
    /**
     * Check if enhanced SSE is supported
     */
    static isSupported() {
        return typeof EventSource !== 'undefined';
    }
}

/**
 * Bandwidth monitoring utility
 */
class BandwidthMonitor {
    constructor() {
        this.samples = [];
        this.maxSamples = 60; // Keep 1 minute of samples
        this.sampleInterval = 1000; // 1 second intervals
        this.currentBytes = 0;
        this.lastSampleTime = Date.now();
    }
    
    recordBytes(bytes) {
        this.currentBytes += bytes;
        
        const now = Date.now();
        if (now - this.lastSampleTime >= this.sampleInterval) {
            this.takeSample();
            this.lastSampleTime = now;
        }
    }
    
    takeSample() {
        this.samples.push({
            timestamp: Date.now(),
            bytes: this.currentBytes
        });
        
        // Keep only recent samples
        if (this.samples.length > this.maxSamples) {
            this.samples.shift();
        }
        
        this.currentBytes = 0;
    }
    
    getCurrentBandwidth() {
        if (this.samples.length < 2) return 0;
        
        const latest = this.samples[this.samples.length - 1];
        const previous = this.samples[this.samples.length - 2];
        
        const timeDiff = (latest.timestamp - previous.timestamp) / 1000;
        return timeDiff > 0 ? latest.bytes / timeDiff : 0;
    }
    
    getAverageBandwidth() {
        if (this.samples.length < 2) return 0;
        
        const totalBytes = this.samples.reduce((sum, sample) => sum + sample.bytes, 0);
        const timeSpan = (this.samples[this.samples.length - 1].timestamp - this.samples[0].timestamp) / 1000;
        
        return timeSpan > 0 ? totalBytes / timeSpan : 0;
    }
}

/**
 * Performance monitoring utility
 */
class PerformanceMonitor {
    constructor() {
        this.connectionTimes = [];
        this.latencies = [];
        this.systemPerformance = [];
        this.maxSamples = 100;
    }
    
    recordConnectionTime(time) {
        this.connectionTimes.push({
            timestamp: Date.now(),
            duration: time
        });
        
        if (this.connectionTimes.length > this.maxSamples) {
            this.connectionTimes.shift();
        }
    }
    
    recordLatency(latency) {
        this.latencies.push({
            timestamp: Date.now(),
            latency: latency
        });
        
        if (this.latencies.length > this.maxSamples) {
            this.latencies.shift();
        }
    }
    
    recordSystemPerformance(perfData) {
        this.systemPerformance.push({
            timestamp: Date.now(),
            ...perfData
        });
        
        if (this.systemPerformance.length > this.maxSamples) {
            this.systemPerformance.shift();
        }
    }
    
    getAverageConnectionTime() {
        if (this.connectionTimes.length === 0) return 0;
        const total = this.connectionTimes.reduce((sum, record) => sum + record.duration, 0);
        return total / this.connectionTimes.length;
    }
    
    getAverageLatency() {
        if (this.latencies.length === 0) return 0;
        const total = this.latencies.reduce((sum, record) => sum + record.latency, 0);
        return total / this.latencies.length;
    }
}

// Export for use by other modules
window.EnhancedSSEClient = EnhancedSSEClient;
window.BandwidthMonitor = BandwidthMonitor;
window.PerformanceMonitor = PerformanceMonitor;

// Auto-initialize if supported
if (typeof window !== 'undefined' && EnhancedSSEClient.isSupported()) {
    console.log('Enhanced SSE Client loaded and ready');
    
    // Listen for theme changes to update dynamic elements
    document.addEventListener('theme-changed', (event) => {
        const { currentEffectiveTheme } = event.detail;
        if (window.enhancedSSE && typeof window.enhancedSSE.updateDynamicElements === 'function') {
            window.enhancedSSE.updateDynamicElements(currentEffectiveTheme);
        }
    });
} else {
    console.warn('Enhanced SSE: EventSource not supported in this browser');
}