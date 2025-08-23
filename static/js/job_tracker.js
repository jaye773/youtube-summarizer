/**
 * Job Tracker - Track multiple async jobs and their progress
 * Part of Module 4: Client-Side JavaScript for YouTube Summarizer Async Worker System
 */

class JobTracker {
    constructor() {
        this.activeJobs = new Map();
        this.completedJobs = new Map();
        this.jobHistory = [];
        this.maxHistorySize = 100;
        this.eventHandlers = new Map();
        
        // Bind methods
        this.addJob = this.addJob.bind(this);
        this.updateProgress = this.updateProgress.bind(this);
        this.completeJob = this.completeJob.bind(this);
        this.failJob = this.failJob.bind(this);
        this.removeJob = this.removeJob.bind(this);
    }

    /**
     * Add a new job to track
     * @param {string} jobId - Unique job identifier
     * @param {Object} jobData - Job metadata
     */
    addJob(jobId, jobData = {}) {
        const job = {
            jobId,
            status: 'pending',
            progress: 0,
            createdAt: new Date(),
            updatedAt: new Date(),
            ...jobData
        };

        this.activeJobs.set(jobId, job);
        console.log('📋 JobTracker: Added job', jobId, job);
        
        this.triggerHandler('job_added', { jobId, job });
        this.updateStats();
        
        return job;
    }

    /**
     * Update job progress
     * @param {Object} progressData - Progress update data
     */
    updateProgress(progressData) {
        const { job_id: jobId, progress, status, message, ...otherData } = progressData;
        
        if (!jobId) {
            console.warn('⚠️ JobTracker: Progress update missing job_id:', progressData);
            return;
        }

        let job = this.activeJobs.get(jobId);
        if (!job) {
            // Create job if it doesn't exist (server-initiated job)
            job = this.addJob(jobId, {
                title: progressData.video_title || progressData.title || 'Unknown',
                type: progressData.job_type || 'video',
                url: progressData.video_url || progressData.url
            });
        }

        // Update job data
        job.progress = progress || job.progress;
        job.status = status || job.status;
        job.message = message || job.message;
        job.updatedAt = new Date();
        
        // Merge additional data
        Object.assign(job, otherData);

        console.log(`📊 JobTracker: Updated job ${jobId} - ${job.progress || 0}% (${job.status})`);
        
        this.triggerHandler('job_progress', { jobId, job, progressData });
        this.updateStats();
    }

    /**
     * Mark job as completed
     * @param {string} jobId - Job identifier
     * @param {Object} completionData - Completion data
     */
    completeJob(jobId, completionData = {}) {
        const job = this.activeJobs.get(jobId);
        if (!job) {
            console.warn(`⚠️ JobTracker: Cannot complete unknown job ${jobId}`);
            return;
        }

        // Update job with completion data
        job.status = 'completed';
        job.progress = 100;
        job.completedAt = new Date();
        job.updatedAt = new Date();
        
        // Merge completion data
        Object.assign(job, completionData);

        // Move to completed jobs
        this.completedJobs.set(jobId, job);
        this.activeJobs.delete(jobId);
        
        // Add to history
        this.addToHistory(job);

        console.log(`✅ JobTracker: Completed job ${jobId}:`, job.title || jobId);
        
        this.triggerHandler('job_completed', { jobId, job, completionData });
        this.updateStats();
        
        return job;
    }

    /**
     * Mark job as failed
     * @param {string} jobId - Job identifier
     * @param {Object} errorData - Error data
     */
    failJob(jobId, errorData = {}) {
        const job = this.activeJobs.get(jobId);
        if (!job) {
            console.warn(`⚠️ JobTracker: Cannot fail unknown job ${jobId}`);
            return;
        }

        // Update job with error data
        job.status = 'failed';
        job.failedAt = new Date();
        job.updatedAt = new Date();
        job.error = errorData.error || errorData.message || 'Unknown error';
        
        // Merge error data
        Object.assign(job, errorData);

        // Move to completed jobs (failed jobs are also "completed")
        this.completedJobs.set(jobId, job);
        this.activeJobs.delete(jobId);
        
        // Add to history
        this.addToHistory(job);

        console.error(`❌ JobTracker: Failed job ${jobId}:`, job.error);
        
        this.triggerHandler('job_failed', { jobId, job, errorData });
        this.updateStats();
        
        return job;
    }

    /**
     * Remove job from tracking
     * @param {string} jobId - Job identifier
     */
    removeJob(jobId) {
        const wasActive = this.activeJobs.delete(jobId);
        const wasCompleted = this.completedJobs.delete(jobId);
        
        if (wasActive || wasCompleted) {
            console.log(`🗑️ JobTracker: Removed job ${jobId}`);
            this.triggerHandler('job_removed', { jobId });
            this.updateStats();
            return true;
        }
        
        return false;
    }

    /**
     * Get job by ID
     * @param {string} jobId - Job identifier
     * @returns {Object|null} Job data or null if not found
     */
    getJob(jobId) {
        return this.activeJobs.get(jobId) || this.completedJobs.get(jobId) || null;
    }

    /**
     * Get all active jobs
     * @returns {Array} Array of active job objects
     */
    getActiveJobs() {
        return Array.from(this.activeJobs.values());
    }

    /**
     * Get all completed jobs
     * @returns {Array} Array of completed job objects
     */
    getCompletedJobs() {
        return Array.from(this.completedJobs.values());
    }

    /**
     * Get jobs by status
     * @param {string} status - Job status to filter by
     * @returns {Array} Array of job objects with matching status
     */
    getJobsByStatus(status) {
        const jobs = [
            ...this.getActiveJobs(),
            ...this.getCompletedJobs()
        ];
        
        return jobs.filter(job => job.status === status);
    }

    /**
     * Clear completed jobs
     */
    clearCompleted() {
        const count = this.completedJobs.size;
        this.completedJobs.clear();
        console.log(`🧹 JobTracker: Cleared ${count} completed jobs`);
        
        this.triggerHandler('jobs_cleared', { count, type: 'completed' });
        this.updateStats();
    }

    /**
     * Clear all jobs
     */
    clearAll() {
        const activeCount = this.activeJobs.size;
        const completedCount = this.completedJobs.size;
        
        this.activeJobs.clear();
        this.completedJobs.clear();
        this.jobHistory = [];
        
        console.log(`🧹 JobTracker: Cleared all jobs (${activeCount} active, ${completedCount} completed)`);
        
        this.triggerHandler('jobs_cleared', { 
            count: activeCount + completedCount, 
            type: 'all',
            activeCount,
            completedCount
        });
        this.updateStats();
    }

    /**
     * Get job statistics
     * @returns {Object} Statistics object
     */
    getStats() {
        const activeJobs = this.getActiveJobs();
        const completedJobs = this.getCompletedJobs();
        const failedJobs = this.getJobsByStatus('failed');
        
        return {
            active: activeJobs.length,
            completed: completedJobs.length - failedJobs.length,
            failed: failedJobs.length,
            total: activeJobs.length + completedJobs.length,
            inProgress: activeJobs.filter(job => job.status === 'in_progress').length,
            pending: activeJobs.filter(job => job.status === 'pending').length,
            historySize: this.jobHistory.length
        };
    }

    /**
     * Add job to history
     * @param {Object} job - Job object
     */
    addToHistory(job) {
        this.jobHistory.unshift({
            ...job,
            historyAddedAt: new Date()
        });
        
        // Trim history if it gets too large
        if (this.jobHistory.length > this.maxHistorySize) {
            this.jobHistory = this.jobHistory.slice(0, this.maxHistorySize);
        }
    }

    /**
     * Get job history
     * @param {number} limit - Maximum number of history items to return
     * @returns {Array} Array of historical job objects
     */
    getHistory(limit = 20) {
        return this.jobHistory.slice(0, limit);
    }

    /**
     * Update statistics and trigger event
     */
    updateStats() {
        const stats = this.getStats();
        this.triggerHandler('stats_updated', stats);
    }

    /**
     * Add event handler
     * @param {string} eventType - Event type
     * @param {Function} handler - Event handler function
     */
    addEventListener(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, []);
        }
        this.eventHandlers.get(eventType).push(handler);
    }

    /**
     * Remove event handler
     * @param {string} eventType - Event type
     * @param {Function} handler - Event handler function
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
     * @param {string} eventType - Event type
     * @param {*} data - Event data
     */
    triggerHandler(eventType, data) {
        if (this.eventHandlers.has(eventType)) {
            this.eventHandlers.get(eventType).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`❌ JobTracker: Error in ${eventType} handler:`, error);
                }
            });
        }
    }

    /**
     * Export job data for debugging/analytics
     * @returns {Object} Export data
     */
    exportData() {
        return {
            activeJobs: Array.from(this.activeJobs.entries()),
            completedJobs: Array.from(this.completedJobs.entries()),
            jobHistory: this.jobHistory,
            stats: this.getStats(),
            timestamp: new Date().toISOString()
        };
    }

    /**
     * Import job data (useful for persistence)
     * @param {Object} data - Import data
     */
    importData(data) {
        try {
            if (data.activeJobs) {
                this.activeJobs = new Map(data.activeJobs);
            }
            if (data.completedJobs) {
                this.completedJobs = new Map(data.completedJobs);
            }
            if (data.jobHistory) {
                this.jobHistory = data.jobHistory;
            }
            
            console.log('📥 JobTracker: Imported data successfully');
            this.updateStats();
        } catch (error) {
            console.error('❌ JobTracker: Failed to import data:', error);
        }
    }
}

// Export for use by other modules
window.JobTracker = new JobTracker();

console.log('🎯 JobTracker: JobTracker loaded and ready');