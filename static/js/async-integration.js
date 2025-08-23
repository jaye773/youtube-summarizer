/**
 * Async Integration Layer - Orchestrates SSE, UI updates, and API fallbacks
 * Main integration point for async summary processing features
 */

class AsyncIntegration {
    constructor() {
        this.sseManager = null;
        this.uiStateManager = null;
        this.apiClient = null;
        this.initialized = false;
        this.fallbackPolling = new Map();
        this.gracefulDegradation = false;
        
        // Bind methods to maintain context
        this.handleConnectionChange = this.handleConnectionChange.bind(this);
        this.handleSummaryStarted = this.handleSummaryStarted.bind(this);
        this.handleSummaryProgress = this.handleSummaryProgress.bind(this);
        this.handleSummaryCompleted = this.handleSummaryCompleted.bind(this);
        this.handleSummaryFailed = this.handleSummaryFailed.bind(this);
        this.handleCacheUpdated = this.handleCacheUpdated.bind(this);
    }

    /**
     * Initialize the async integration system
     */
    async initialize() {
        if (this.initialized) {
            console.warn('⚠️ AsyncIntegration already initialized');
            return;
        }

        console.log('🚀 Initializing async integration system...');

        try {
            // Initialize components
            this.apiClient = new APIClient();
            this.uiStateManager = new UIStateManager();
            
            // Test API connectivity first
            const isHealthy = await this.apiClient.healthCheck();
            if (!isHealthy) {
                console.warn('⚠️ API health check failed, enabling graceful degradation');
                this.gracefulDegradation = true;
            }

            // Initialize SSE if API is healthy
            if (!this.gracefulDegradation) {
                this.sseManager = new SSEManager();
                this.setupSSEEventHandlers();
            } else {
                this.uiStateManager.showNotification(
                    'ℹ️ Limited Mode',
                    'Real-time updates unavailable. Using polling fallback.',
                    'info',
                    8000
                );
            }

            // Setup cache refresh integration
            this.setupCacheRefreshIntegration();

            this.initialized = true;
            console.log('✅ Async integration system initialized successfully');

        } catch (error) {
            console.error('❌ Failed to initialize async integration:', error);
            this.gracefulDegradation = true;
            this.initializeFallbackMode();
        }
    }

    /**
     * Setup SSE event handlers
     */
    setupSSEEventHandlers() {
        if (!this.sseManager) return;

        this.sseManager.subscribe('connection', this.handleConnectionChange);
        this.sseManager.subscribe('summaryStarted', this.handleSummaryStarted);
        this.sseManager.subscribe('summaryProgress', this.handleSummaryProgress);
        this.sseManager.subscribe('summaryCompleted', this.handleSummaryCompleted);
        this.sseManager.subscribe('summaryFailed', this.handleSummaryFailed);
        this.sseManager.subscribe('cacheUpdated', this.handleCacheUpdated);
    }

    /**
     * Setup cache refresh integration with existing pagination system
     */
    setupCacheRefreshIntegration() {
        this.uiStateManager.onCacheRefresh(async (data) => {
            console.log('🔄 Triggering cache refresh from SSE event');
            
            // Invalidate API client cache
            this.apiClient.invalidateCacheByPattern('get_cached_summaries');
            
            // Refresh current page if loadPaginatedSummaries exists globally
            if (typeof window.loadPaginatedSummaries === 'function') {
                try {
                    await window.loadPaginatedSummaries(window.currentPage, window.currentPageSize);
                    console.log('✅ Successfully refreshed pagination');
                } catch (error) {
                    console.warn('⚠️ Failed to refresh pagination:', error);
                }
            }

            // Update specific result card if we have the data
            if (data.video_id && data.summary) {
                this.uiStateManager.updateResultCard(data.video_id, data);
            }
        });
    }

    /**
     * Handle connection status changes
     */
    handleConnectionChange(data) {
        console.log('🔗 Connection status changed:', data.status);
        this.uiStateManager.updateConnectionStatus(data.status);

        if (data.status === 'disconnected' || data.status === 'failed') {
            this.activateFallbackMode();
        } else if (data.status === 'connected') {
            this.deactivateFallbackMode();
        }
    }

    /**
     * Handle summary started events
     */
    handleSummaryStarted(data) {
        this.uiStateManager.handleSummaryStarted(data);
    }

    /**
     * Handle summary progress events
     */
    handleSummaryProgress(data) {
        this.uiStateManager.handleSummaryProgress(data);
    }

    /**
     * Handle summary completed events
     */
    handleSummaryCompleted(data) {
        this.uiStateManager.handleSummaryCompleted(data);
        
        // Stop any fallback polling for this video
        if (this.fallbackPolling.has(data.video_id)) {
            this.fallbackPolling.get(data.video_id)();
            this.fallbackPolling.delete(data.video_id);
        }
    }

    /**
     * Handle summary failed events
     */
    handleSummaryFailed(data) {
        this.uiStateManager.handleSummaryFailed(data);
        
        // Stop any fallback polling for this video
        if (this.fallbackPolling.has(data.video_id)) {
            this.fallbackPolling.get(data.video_id)();
            this.fallbackPolling.delete(data.video_id);
        }
    }

    /**
     * Handle cache updated events
     */
    handleCacheUpdated(data) {
        this.uiStateManager.handleCacheUpdated(data);
    }

    /**
     * Activate fallback polling mode
     */
    activateFallbackMode() {
        console.log('🔄 Activating fallback polling mode');
        
        // Get currently pending summaries
        const pendingVideoIds = Array.from(this.uiStateManager.pendingSummaries.keys());
        
        if (pendingVideoIds.length > 0) {
            const cleanup = this.apiClient.startPolling(
                pendingVideoIds,
                (videoId, summaryData) => {
                    if (summaryData && summaryData.summary) {
                        // Simulate SSE completion event
                        this.handleSummaryCompleted({
                            video_id: videoId,
                            title: summaryData.title,
                            summary: summaryData.summary
                        });
                    }
                },
                10000 // Poll every 10 seconds in fallback mode
            );

            // Store cleanup functions
            pendingVideoIds.forEach(videoId => {
                this.fallbackPolling.set(videoId, cleanup);
            });
        }
    }

    /**
     * Deactivate fallback polling mode
     */
    deactivateFallbackMode() {
        console.log('✅ Deactivating fallback polling mode');
        
        // Stop all polling
        this.fallbackPolling.forEach(cleanup => cleanup());
        this.fallbackPolling.clear();
    }

    /**
     * Initialize fallback-only mode
     */
    initializeFallbackMode() {
        console.log('🔄 Initializing fallback-only mode');
        this.uiStateManager.updateConnectionStatus('failed');
    }

    /**
     * Enhanced summarize function with async support
     */
    async enhancedSummarize(urls, model) {
        try {
            // Show immediate feedback
            this.uiStateManager.showNotification(
                '🚀 Processing Started',
                `Submitted ${urls.length} URL(s) for processing`,
                'info',
                3000
            );

            // Submit to server (now returns immediately with job IDs)
            const response = await this.apiClient.submitSummarization(urls, model);
            
            if (response.job_ids && response.job_ids.length > 0) {
                // SSE will handle progress updates
                console.log('✅ Jobs submitted successfully:', response.job_ids);
                
                // If SSE is not available, start fallback polling
                if (this.gracefulDegradation || !this.sseManager || !this.sseManager.isConnected) {
                    this.activateFallbackPolling(response.job_ids);
                }
                
                return response;
            } else {
                // Fallback to synchronous processing
                console.log('🔄 Falling back to synchronous processing');
                return response;
            }

        } catch (error) {
            this.uiStateManager.showNotification(
                '❌ Processing Failed',
                `Failed to submit URLs: ${error.message}`,
                'error',
                8000
            );
            throw error;
        }
    }

    /**
     * Start fallback polling for specific job IDs
     */
    activateFallbackPolling(jobIds) {
        console.log('🔄 Starting fallback polling for jobs:', jobIds);
        
        jobIds.forEach(jobId => {
            const cleanup = this.apiClient.startPolling(
                [jobId],
                (id, data) => {
                    if (data && data.status === 'completed') {
                        this.handleSummaryCompleted(data);
                    } else if (data && data.status === 'failed') {
                        this.handleSummaryFailed(data);
                    }
                },
                5000 // Poll every 5 seconds
            );
            
            this.fallbackPolling.set(jobId, cleanup);
        });
    }

    /**
     * Enhanced delete function with real-time updates
     */
    async enhancedDelete(videoId) {
        try {
            const result = await this.apiClient.deleteSummary(videoId);
            
            this.uiStateManager.showNotification(
                '✅ Summary Deleted',
                'Summary has been successfully removed',
                'success',
                3000
            );
            
            return result;

        } catch (error) {
            this.uiStateManager.showNotification(
                '❌ Delete Failed',
                `Failed to delete summary: ${error.message}`,
                'error',
                5000
            );
            throw error;
        }
    }

    /**
     * Get system status
     */
    getStatus() {
        return {
            initialized: this.initialized,
            gracefulDegradation: this.gracefulDegradation,
            sse: this.sseManager ? this.sseManager.getStatus() : null,
            pendingSummaries: this.uiStateManager ? this.uiStateManager.getPendingSummariesCount() : 0,
            cacheStats: this.apiClient ? this.apiClient.getCacheStats() : null,
            fallbackPolling: this.fallbackPolling.size
        };
    }

    /**
     * Force reconnection of SSE
     */
    forceReconnect() {
        if (this.sseManager) {
            this.sseManager.forceReconnect();
        }
    }

    /**
     * Clean up resources
     */
    cleanup() {
        console.log('🧹 Cleaning up async integration system');
        
        // Stop all fallback polling
        this.fallbackPolling.forEach(cleanup => cleanup());
        this.fallbackPolling.clear();
        
        // Cleanup components
        if (this.sseManager) {
            this.sseManager.disconnect();
        }
        
        if (this.uiStateManager) {
            this.uiStateManager.cleanup();
        }
        
        if (this.apiClient) {
            this.apiClient.clearCache();
        }
        
        this.initialized = false;
    }
}

// Create global instance
window.asyncIntegration = new AsyncIntegration();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.asyncIntegration.initialize();
    });
} else {
    // DOM is already ready
    window.asyncIntegration.initialize();
}

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AsyncIntegration;
}