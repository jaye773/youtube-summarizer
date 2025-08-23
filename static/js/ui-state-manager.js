/**
 * UI State Manager - Handles dynamic UI updates for async summary processing
 * Manages progress indicators, cache refresh, and real-time notifications
 */

class UIStateManager {
    constructor() {
        this.pendingSummaries = new Map(); // Track active summaries
        this.progressIndicators = new Map(); // Track progress UI elements
        this.notificationContainer = null;
        this.cacheRefreshCallbacks = new Set();
        this.initializeUI();
    }

    /**
     * Initialize UI components
     */
    initializeUI() {
        this.createNotificationContainer();
        this.createConnectionStatusIndicator();
    }

    /**
     * Create notification container for real-time updates
     */
    createNotificationContainer() {
        // Check if notification container already exists
        let container = document.getElementById('sse-notifications');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'sse-notifications';
            container.className = 'notification-container';
            container.innerHTML = `
                <style>
                    .notification-container {
                        position: fixed;
                        top: 20px;
                        right: 20px;
                        z-index: 1000;
                        max-width: 350px;
                    }
                    
                    .notification {
                        background: #fff;
                        border-radius: 8px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        margin-bottom: 10px;
                        padding: 16px;
                        border-left: 4px solid #8e44ad;
                        animation: slideIn 0.3s ease-out;
                        transition: opacity 0.3s ease-out, transform 0.3s ease-out;
                    }
                    
                    .notification.success { border-left-color: #27ae60; }
                    .notification.error { border-left-color: #e74c3c; }
                    .notification.info { border-left-color: #3498db; }
                    
                    .notification.fade-out {
                        opacity: 0;
                        transform: translateX(100%);
                    }
                    
                    .notification-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 8px;
                    }
                    
                    .notification-title {
                        font-weight: 600;
                        color: #2c3e50;
                        font-size: 14px;
                    }
                    
                    .notification-close {
                        background: none;
                        border: none;
                        font-size: 18px;
                        cursor: pointer;
                        color: #95a5a6;
                        padding: 0;
                        line-height: 1;
                    }
                    
                    .notification-close:hover {
                        color: #7f8c8d;
                    }
                    
                    .notification-body {
                        color: #5a6c7d;
                        font-size: 13px;
                        line-height: 1.4;
                    }
                    
                    @keyframes slideIn {
                        from {
                            transform: translateX(100%);
                            opacity: 0;
                        }
                        to {
                            transform: translateX(0);
                            opacity: 1;
                        }
                    }
                    
                    .connection-status {
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        padding: 8px 12px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: 500;
                        z-index: 999;
                        transition: all 0.3s ease;
                    }
                    
                    .connection-status.connected {
                        background-color: #d5f2d5;
                        color: #27ae60;
                        border: 1px solid #a8e6a8;
                    }
                    
                    .connection-status.disconnected {
                        background-color: #fdeaea;
                        color: #e74c3c;
                        border: 1px solid #f5b7b1;
                        animation: pulse 2s infinite;
                    }
                    
                    .connection-status.connecting {
                        background-color: #e8f4fd;
                        color: #3498db;
                        border: 1px solid #aed6f1;
                    }
                    
                    @keyframes pulse {
                        0%, 100% { opacity: 1; }
                        50% { opacity: 0.6; }
                    }
                    
                    .progress-notification {
                        background: #f8f9fa;
                        border-left-color: #3498db;
                    }
                    
                    .progress-bar {
                        width: 100%;
                        height: 6px;
                        background-color: #ecf0f1;
                        border-radius: 3px;
                        overflow: hidden;
                        margin-top: 8px;
                    }
                    
                    .progress-bar-fill {
                        height: 100%;
                        background-color: #3498db;
                        border-radius: 3px;
                        transition: width 0.3s ease;
                    }
                    
                    .progress-text {
                        font-size: 11px;
                        color: #7f8c8d;
                        margin-top: 4px;
                        text-align: center;
                    }
                </style>
            `;
            
            document.body.appendChild(container);
        }
        
        this.notificationContainer = container;
    }

    /**
     * Create connection status indicator
     */
    createConnectionStatusIndicator() {
        let statusEl = document.getElementById('sse-connection-status');
        
        if (!statusEl) {
            statusEl = document.createElement('div');
            statusEl.id = 'sse-connection-status';
            statusEl.className = 'connection-status connecting';
            statusEl.innerHTML = '🔗 Connecting...';
            document.body.appendChild(statusEl);
        }
    }

    /**
     * Update connection status indicator
     */
    updateConnectionStatus(status) {
        const statusEl = document.getElementById('sse-connection-status');
        if (!statusEl) return;

        statusEl.className = `connection-status ${status}`;
        
        switch (status) {
            case 'connected':
                statusEl.innerHTML = '🟢 Live Updates';
                // Auto-hide after 3 seconds when connected
                setTimeout(() => {
                    statusEl.style.opacity = '0.7';
                }, 3000);
                break;
            case 'disconnected':
                statusEl.innerHTML = '🔴 Disconnected';
                statusEl.style.opacity = '1';
                break;
            case 'connecting':
                statusEl.innerHTML = '🟡 Connecting...';
                statusEl.style.opacity = '1';
                break;
            case 'failed':
                statusEl.innerHTML = '❌ Connection Failed';
                statusEl.style.opacity = '1';
                break;
        }
    }

    /**
     * Show notification
     */
    showNotification(title, message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        
        const notificationId = Date.now().toString();
        notification.dataset.id = notificationId;
        
        notification.innerHTML = `
            <div class="notification-header">
                <span class="notification-title">${title}</span>
                <button class="notification-close" onclick="this.closest('.notification').remove()">×</button>
            </div>
            <div class="notification-body">${message}</div>
        `;
        
        this.notificationContainer.appendChild(notification);
        
        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.removeNotification(notificationId);
            }, duration);
        }
        
        return notificationId;
    }

    /**
     * Remove notification
     */
    removeNotification(notificationId) {
        const notification = this.notificationContainer.querySelector(`[data-id="${notificationId}"]`);
        if (notification) {
            notification.classList.add('fade-out');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }
    }

    /**
     * Show progress notification for summary processing
     */
    showProgressNotification(videoId, title, progress = 0) {
        const existingNotification = this.notificationContainer.querySelector(`[data-video-id="${videoId}"]`);
        
        if (existingNotification) {
            // Update existing progress
            const progressBar = existingNotification.querySelector('.progress-bar-fill');
            const progressText = existingNotification.querySelector('.progress-text');
            
            if (progressBar) {
                progressBar.style.width = `${progress}%`;
            }
            if (progressText) {
                progressText.textContent = `${Math.round(progress)}% complete`;
            }
            return;
        }

        // Create new progress notification
        const notification = document.createElement('div');
        notification.className = 'notification progress-notification';
        notification.dataset.videoId = videoId;
        
        notification.innerHTML = `
            <div class="notification-header">
                <span class="notification-title">Processing Summary</span>
                <button class="notification-close" onclick="this.closest('.notification').remove()">×</button>
            </div>
            <div class="notification-body">
                <div style="margin-bottom: 8px; font-weight: 500;">${title}</div>
                <div class="progress-bar">
                    <div class="progress-bar-fill" style="width: ${progress}%"></div>
                </div>
                <div class="progress-text">${Math.round(progress)}% complete</div>
            </div>
        `;
        
        this.notificationContainer.appendChild(notification);
    }

    /**
     * Remove progress notification
     */
    removeProgressNotification(videoId) {
        const notification = this.notificationContainer.querySelector(`[data-video-id="${videoId}"]`);
        if (notification) {
            notification.classList.add('fade-out');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }
    }

    /**
     * Handle summary started event
     */
    handleSummaryStarted(data) {
        console.log('📝 Summary started:', data);
        
        this.pendingSummaries.set(data.video_id, {
            title: data.title || 'Processing video...',
            startTime: Date.now(),
            progress: 0
        });
        
        this.showProgressNotification(data.video_id, data.title || 'Processing video...', 0);
        this.showNotification(
            '🚀 Summary Started',
            `Started processing: ${data.title || 'Unknown video'}`,
            'info',
            3000
        );
    }

    /**
     * Handle summary progress event
     */
    handleSummaryProgress(data) {
        console.log('📊 Summary progress:', data);
        
        const summary = this.pendingSummaries.get(data.video_id);
        if (summary) {
            summary.progress = data.progress || 0;
            this.showProgressNotification(data.video_id, summary.title, summary.progress);
        }
    }

    /**
     * Handle summary completed event
     */
    handleSummaryCompleted(data) {
        console.log('✅ Summary completed:', data);
        
        this.pendingSummaries.delete(data.video_id);
        this.removeProgressNotification(data.video_id);
        
        this.showNotification(
            '✅ Summary Complete',
            `Successfully processed: ${data.title || 'Video'}`,
            'success',
            5000
        );
        
        // Trigger cache refresh
        this.triggerCacheRefresh(data);
    }

    /**
     * Handle summary failed event
     */
    handleSummaryFailed(data) {
        console.log('❌ Summary failed:', data);
        
        this.pendingSummaries.delete(data.video_id);
        this.removeProgressNotification(data.video_id);
        
        this.showNotification(
            '❌ Summary Failed',
            `Failed to process: ${data.title || 'Video'}. ${data.error || 'Unknown error'}`,
            'error',
            8000
        );
    }

    /**
     * Handle cache updated event
     */
    handleCacheUpdated(data) {
        console.log('🔄 Cache updated:', data);
        this.triggerCacheRefresh(data);
    }

    /**
     * Register cache refresh callback
     */
    onCacheRefresh(callback) {
        this.cacheRefreshCallbacks.add(callback);
        return () => this.cacheRefreshCallbacks.delete(callback);
    }

    /**
     * Trigger cache refresh callbacks
     */
    triggerCacheRefresh(data) {
        this.cacheRefreshCallbacks.forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error('❌ Error in cache refresh callback:', error);
            }
        });
    }

    /**
     * Update existing result card with new data
     */
    updateResultCard(videoId, summaryData) {
        const existingCard = document.querySelector(`.result-card[data-video-id='${videoId}']`);
        if (existingCard && summaryData.summary) {
            // Find the summary content and update it
            const summaryContent = existingCard.querySelector('pre');
            if (summaryContent) {
                summaryContent.textContent = summaryData.summary;
            }
            
            // Remove error styling if it exists
            existingCard.classList.remove('error-card');
            
            // Add subtle highlight animation
            existingCard.style.transition = 'background-color 0.5s ease';
            existingCard.style.backgroundColor = '#e8f5e8';
            setTimeout(() => {
                existingCard.style.backgroundColor = '';
            }, 2000);
        }
    }

    /**
     * Get pending summaries count
     */
    getPendingSummariesCount() {
        return this.pendingSummaries.size;
    }

    /**
     * Check if video is being processed
     */
    isVideoProcessing(videoId) {
        return this.pendingSummaries.has(videoId);
    }

    /**
     * Clean up resources
     */
    cleanup() {
        this.pendingSummaries.clear();
        this.cacheRefreshCallbacks.clear();
        
        // Remove notification container
        if (this.notificationContainer && this.notificationContainer.parentNode) {
            this.notificationContainer.parentNode.removeChild(this.notificationContainer);
        }
        
        // Remove connection status
        const statusEl = document.getElementById('sse-connection-status');
        if (statusEl && statusEl.parentNode) {
            statusEl.parentNode.removeChild(statusEl);
        }
    }
}

// Export for ES6 modules or global usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIStateManager;
} else {
    window.UIStateManager = UIStateManager;
}