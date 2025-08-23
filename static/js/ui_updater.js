/**
 * UI Updater - Dynamic UI updates for async operations
 * Part of Module 4: Client-Side JavaScript for YouTube Summarizer Async Worker System
 */

class UIUpdater {
    constructor() {
        this.progressBars = new Map();
        this.toastQueue = [];
        this.isProcessingToasts = false;
        this.toastContainer = null;
        this.connectionStatusIndicator = null;
        
        // Configuration
        this.toastDuration = 5000;
        this.maxToasts = 5;
        this.animationDuration = 300;
        
        // Bind methods
        this.addProgressBar = this.addProgressBar.bind(this);
        this.updateProgressBar = this.updateProgressBar.bind(this);
        this.removeProgressBar = this.removeProgressBar.bind(this);
        this.showToast = this.showToast.bind(this);
        this.addCompletedSummary = this.addCompletedSummary.bind(this);
        
        // Initialize UI components
        this.initializeComponents();
    }

    /**
     * Initialize UI components
     */
    initializeComponents() {
        this.createToastContainer();
        this.initializeConnectionStatusIndicator();
        
        // Listen to job tracker events
        if (window.JobTracker) {
            window.JobTracker.addEventListener('job_added', this.handleJobAdded.bind(this));
            window.JobTracker.addEventListener('job_progress', this.handleJobProgress.bind(this));
            window.JobTracker.addEventListener('job_completed', this.handleJobCompleted.bind(this));
            window.JobTracker.addEventListener('job_failed', this.handleJobFailed.bind(this));
            window.JobTracker.addEventListener('stats_updated', this.handleStatsUpdated.bind(this));
        }
        
        console.log('🎨 UIUpdater: UI components initialized');
    }

    /**
     * Handle job added event
     */
    handleJobAdded({ jobId, job }) {
        this.addProgressBar(jobId, {
            title: job.title || 'Processing...',
            progress: job.progress || 0,
            status: job.status || 'pending'
        });
    }

    /**
     * Handle job progress event
     */
    handleJobProgress({ jobId, job, progressData }) {
        this.updateProgressBar(jobId, {
            progress: job.progress || 0,
            status: job.status || 'in_progress',
            message: job.message || progressData.message || 'Processing...'
        });
    }

    /**
     * Handle job completed event
     */
    handleJobCompleted({ jobId, job, completionData }) {
        // Remove progress bar after a delay
        setTimeout(() => {
            this.removeProgressBar(jobId);
        }, 2000);
        
        // Show completion toast
        this.showToast(
            `✅ Summary completed: ${job.title || 'Unknown video'}`,
            'success'
        );
        
        // Add to completed summaries if data is available
        if (completionData && completionData.summary) {
            this.addCompletedSummary(completionData);
        }
    }

    /**
     * Handle job failed event
     */
    handleJobFailed({ jobId, job, errorData }) {
        // Remove progress bar after a delay
        setTimeout(() => {
            this.removeProgressBar(jobId);
        }, 2000);
        
        // Show error toast
        this.showToast(
            `❌ Failed: ${job.title || 'Unknown video'} - ${job.error || 'Unknown error'}`,
            'error'
        );
    }

    /**
     * Handle stats updated event
     */
    handleStatsUpdated(stats) {
        this.updateConnectionStatus(stats);
    }

    /**
     * Add progress bar for a job
     */
    addProgressBar(jobId, { title, progress = 0, status = 'pending' }) {
        // Check if progress bar already exists
        if (this.progressBars.has(jobId)) {
            this.updateProgressBar(jobId, { progress, status });
            return;
        }

        const progressElement = this.createProgressBarElement(jobId, title, progress, status);
        this.progressBars.set(jobId, {
            element: progressElement,
            title,
            progress,
            status,
            createdAt: new Date()
        });

        // Insert progress bar into the UI
        this.insertProgressBar(progressElement);
        
        console.log(`📊 UIUpdater: Added progress bar for job ${jobId}`);
    }

    /**
     * Update existing progress bar
     */
    updateProgressBar(jobId, { progress, status, message }) {
        const progressData = this.progressBars.get(jobId);
        if (!progressData) {
            console.warn(`⚠️ UIUpdater: Cannot update unknown progress bar ${jobId}`);
            return;
        }

        const { element } = progressData;
        const progressBar = element.querySelector('.async-progress-bar');
        const progressText = element.querySelector('.async-progress-text');
        const progressMessage = element.querySelector('.async-progress-message');

        // Update progress bar
        if (progress !== undefined) {
            progressBar.style.width = `${Math.min(Math.max(progress, 0), 100)}%`;
            progressData.progress = progress;
        }

        // Update status
        if (status) {
            element.className = `async-progress-container ${status}`;
            progressData.status = status;
        }

        // Update text
        if (progressText && progress !== undefined) {
            progressText.textContent = `${Math.round(progress)}%`;
        }

        // Update message
        if (progressMessage && message) {
            progressMessage.textContent = message;
        }

        console.log(`📊 UIUpdater: Updated progress bar ${jobId} - ${progress}% (${status})`);
    }

    /**
     * Remove progress bar
     */
    removeProgressBar(jobId) {
        const progressData = this.progressBars.get(jobId);
        if (!progressData) {
            return;
        }

        const { element } = progressData;
        
        // Fade out animation
        element.style.transition = `opacity ${this.animationDuration}ms ease-out`;
        element.style.opacity = '0';

        setTimeout(() => {
            if (element.parentNode) {
                element.parentNode.removeChild(element);
            }
            this.progressBars.delete(jobId);
        }, this.animationDuration);

        console.log(`🗑️ UIUpdater: Removed progress bar for job ${jobId}`);
    }

    /**
     * Create progress bar element
     */
    createProgressBarElement(jobId, title, progress, status) {
        const container = document.createElement('div');
        container.className = `async-progress-container ${status}`;
        container.setAttribute('data-job-id', jobId);
        
        container.innerHTML = `
            <div class="async-progress-header">
                <span class="async-progress-title">${this.escapeHtml(title)}</span>
                <span class="async-progress-text">${Math.round(progress)}%</span>
            </div>
            <div class="async-progress-track">
                <div class="async-progress-bar" style="width: ${progress}%"></div>
            </div>
            <div class="async-progress-message">Initializing...</div>
        `;
        
        return container;
    }

    /**
     * Insert progress bar into UI
     */
    insertProgressBar(element) {
        let container = document.getElementById('async-progress-section');
        
        if (!container) {
            container = this.createProgressSection();
        }
        
        container.appendChild(element);
        
        // Show the section if it was hidden
        container.style.display = 'block';
    }

    /**
     * Create progress section if it doesn't exist
     */
    createProgressSection() {
        const section = document.createElement('div');
        section.id = 'async-progress-section';
        section.className = 'async-progress-section';
        
        const title = document.createElement('h3');
        title.textContent = 'Processing Summaries';
        title.className = 'async-progress-section-title';
        section.appendChild(title);
        
        // Insert after summarize controls
        const summarizeControls = document.querySelector('.summarize-controls');
        if (summarizeControls && summarizeControls.parentNode) {
            summarizeControls.parentNode.insertBefore(section, summarizeControls.nextSibling);
        } else {
            // Fallback: add to container
            const container = document.querySelector('.container');
            if (container) {
                container.appendChild(section);
            }
        }
        
        return section;
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info', options = {}) {
        const toast = {
            id: `toast_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            message,
            type,
            duration: options.duration || this.toastDuration,
            createdAt: new Date()
        };

        this.toastQueue.push(toast);
        
        if (!this.isProcessingToasts) {
            this.processToastQueue();
        }
    }

    /**
     * Process toast queue
     */
    async processToastQueue() {
        if (this.isProcessingToasts || this.toastQueue.length === 0) {
            return;
        }

        this.isProcessingToasts = true;

        while (this.toastQueue.length > 0) {
            // Limit concurrent toasts
            const activeToasts = this.toastContainer.children.length;
            if (activeToasts >= this.maxToasts) {
                await this.waitForToastSpace();
            }

            const toast = this.toastQueue.shift();
            this.displayToast(toast);
        }

        this.isProcessingToasts = false;
    }

    /**
     * Display individual toast
     */
    displayToast({ id, message, type, duration }) {
        const toastElement = document.createElement('div');
        toastElement.className = `async-toast async-toast-${type}`;
        toastElement.setAttribute('data-toast-id', id);
        
        toastElement.innerHTML = `
            <div class="async-toast-content">
                <span class="async-toast-message">${this.escapeHtml(message)}</span>
                <button class="async-toast-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;

        this.toastContainer.appendChild(toastElement);

        // Animate in
        requestAnimationFrame(() => {
            toastElement.style.opacity = '1';
            toastElement.style.transform = 'translateX(0)';
        });

        // Auto-remove after duration
        setTimeout(() => {
            this.removeToast(toastElement);
        }, duration);

        console.log(`🔔 UIUpdater: Showed ${type} toast: ${message}`);
    }

    /**
     * Remove toast with animation
     */
    removeToast(toastElement) {
        if (!toastElement.parentNode) return;

        toastElement.style.opacity = '0';
        toastElement.style.transform = 'translateX(100%)';

        setTimeout(() => {
            if (toastElement.parentNode) {
                toastElement.parentNode.removeChild(toastElement);
            }
        }, this.animationDuration);
    }

    /**
     * Wait for toast space to become available
     */
    waitForToastSpace() {
        return new Promise((resolve) => {
            const checkSpace = () => {
                if (this.toastContainer.children.length < this.maxToasts) {
                    resolve();
                } else {
                    setTimeout(checkSpace, 100);
                }
            };
            checkSpace();
        });
    }

    /**
     * Create toast container
     */
    createToastContainer() {
        this.toastContainer = document.createElement('div');
        this.toastContainer.id = 'async-toast-container';
        this.toastContainer.className = 'async-toast-container';
        document.body.appendChild(this.toastContainer);
    }

    /**
     * Add completed summary to UI
     */
    addCompletedSummary(summaryData) {
        // This integrates with the existing displayResults function
        try {
            if (window.displayResults && typeof window.displayResults === 'function') {
                const newResultsContainer = document.getElementById('new-results');
                if (newResultsContainer) {
                    // Convert to expected format
                    const resultData = [{
                        type: 'video',
                        title: summaryData.title,
                        summary: summaryData.summary,
                        video_id: summaryData.video_id,
                        video_url: summaryData.video_url || summaryData.url,
                        thumbnail_url: summaryData.thumbnail_url,
                        error: summaryData.error
                    }];
                    
                    window.displayResults(resultData, newResultsContainer, true);
                    console.log('📝 UIUpdater: Added completed summary to UI');
                }
            }
            
            // Refresh cache if possible
            this.refreshSummaryCache();
            
        } catch (error) {
            console.error('❌ UIUpdater: Error adding completed summary:', error);
        }
    }

    /**
     * Refresh summary cache
     */
    refreshSummaryCache() {
        // Trigger cache refresh if functions are available
        if (window.loadPaginatedSummaries && typeof window.loadPaginatedSummaries === 'function') {
            // Small delay to allow backend to process
            setTimeout(() => {
                window.loadPaginatedSummaries(window.currentPage || 1, window.currentPageSize || 10);
            }, 1000);
        }
    }

    /**
     * Update connection status indicator
     */
    updateConnectionStatus(connected, stats = {}) {
        if (!this.connectionStatusIndicator) {
            this.createConnectionStatusIndicator();
        }

        const statusDot = this.connectionStatusIndicator.querySelector('.connection-status-dot');
        const statusText = this.connectionStatusIndicator.querySelector('.connection-status-text');
        const statusStats = this.connectionStatusIndicator.querySelector('.connection-status-stats');

        // Update connection status
        this.connectionStatusIndicator.className = connected ? 
            'async-connection-status connected' : 
            'async-connection-status disconnected';

        if (statusDot) {
            statusDot.className = connected ? 'connection-status-dot connected' : 'connection-status-dot disconnected';
        }

        if (statusText) {
            statusText.textContent = connected ? 'Connected' : 'Disconnected';
        }

        // Update stats if available
        if (statusStats && stats && typeof stats === 'object') {
            const { active = 0, completed = 0, failed = 0 } = stats;
            statusStats.textContent = active > 0 ? 
                `${active} active, ${completed} completed, ${failed} failed` : 
                '';
        }

        const title = connected ? 
            'Real-time updates: Connected' : 
            'Real-time updates: Disconnected';
        this.connectionStatusIndicator.title = title;
    }

    /**
     * Create connection status indicator
     */
    /**
     * Initialize connection status indicator (use existing one)
     */
    initializeConnectionStatusIndicator() {
        // Use the existing connection status indicator instead of creating a new one
        this.connectionStatusIndicator = document.getElementById('connection-status');
        
        if (!this.connectionStatusIndicator) {
            console.warn('🎨 UIUpdater: No existing connection status indicator found, creating fallback');
            // Fallback: create minimal indicator
            this.connectionStatusIndicator = document.createElement('div');
            this.connectionStatusIndicator.id = 'connection-status';
            this.connectionStatusIndicator.className = 'async-connection-status disconnected';
            this.connectionStatusIndicator.innerHTML = `
                <span class="connection-status-dot disconnected"></span>
                <span class="status-text">Disconnected</span>
            `;
            
            // Add to async-status-container if it exists
            const asyncContainer = document.getElementById('async-status-container');
            if (asyncContainer) {
                asyncContainer.appendChild(this.connectionStatusIndicator);
            }
        }
    }

    /**
     * Clear all progress bars
     */
    clearAllProgressBars() {
        const progressSection = document.getElementById('async-progress-section');
        if (progressSection) {
            progressSection.style.display = 'none';
            progressSection.innerHTML = '<h3 class="async-progress-section-title">Processing Summaries</h3>';
        }
        
        this.progressBars.clear();
        console.log('🧹 UIUpdater: Cleared all progress bars');
    }

    /**
     * Clear all toasts
     */
    clearAllToasts() {
        if (this.toastContainer) {
            Array.from(this.toastContainer.children).forEach(toast => {
                this.removeToast(toast);
            });
        }
        
        this.toastQueue = [];
        console.log('🧹 UIUpdater: Cleared all toasts');
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
     * Get UI state for debugging
     */
    getState() {
        return {
            progressBars: this.progressBars.size,
            activeToasts: this.toastContainer ? this.toastContainer.children.length : 0,
            queuedToasts: this.toastQueue.length,
            isProcessingToasts: this.isProcessingToasts
        };
    }
}

// Export for use by other modules
window.UIUpdater = new UIUpdater();

console.log('🎯 UIUpdater: UIUpdater loaded and ready');