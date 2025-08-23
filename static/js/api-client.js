/**
 * API Client - Handles direct API calls with fallback mechanisms
 * Provides cache refresh strategy and handles API failures gracefully
 */

class APIClient {
    constructor() {
        this.baseUrl = window.location.origin;
        this.requestQueue = new Map();
        this.retryAttempts = new Map();
        this.maxRetries = 3;
        this.retryDelay = 1000;
        this.cache = new Map();
        this.cacheExpiry = 5 * 60 * 1000; // 5 minutes
    }

    /**
     * Make API request with retry logic and caching
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const cacheKey = `${options.method || 'GET'}_${url}_${JSON.stringify(options.body || {})}`;
        
        // Check cache for GET requests
        if ((!options.method || options.method === 'GET') && this.cache.has(cacheKey)) {
            const cached = this.cache.get(cacheKey);
            if (Date.now() - cached.timestamp < this.cacheExpiry) {
                console.log('📦 Using cached response for:', endpoint);
                return cached.data;
            }
            this.cache.delete(cacheKey);
        }

        // Prevent duplicate requests
        if (this.requestQueue.has(cacheKey)) {
            console.log('⏳ Request already in progress for:', endpoint);
            return this.requestQueue.get(cacheKey);
        }

        const requestPromise = this._makeRequest(url, options, cacheKey);
        this.requestQueue.set(cacheKey, requestPromise);

        try {
            const result = await requestPromise;
            this.requestQueue.delete(cacheKey);
            
            // Cache GET requests
            if (!options.method || options.method === 'GET') {
                this.cache.set(cacheKey, {
                    data: result,
                    timestamp: Date.now()
                });
            }
            
            return result;
        } catch (error) {
            this.requestQueue.delete(cacheKey);
            throw error;
        }
    }

    /**
     * Internal method to make request with retries
     */
    async _makeRequest(url, options, cacheKey) {
        const maxRetries = this.maxRetries;
        let lastError = null;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                const response = await fetch(url, {
                    headers: {
                        'Content-Type': 'application/json',
                        ...options.headers
                    },
                    ...options
                });

                // Handle non-JSON responses
                const contentType = response.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    const text = await response.text();
                    console.error('❌ Non-JSON response:', text);
                    throw new Error('Server returned non-JSON response');
                }

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
                }

                // Reset retry count on success
                this.retryAttempts.delete(cacheKey);
                return data;

            } catch (error) {
                lastError = error;
                console.warn(`⚠️ API request attempt ${attempt + 1}/${maxRetries + 1} failed:`, error.message);

                // Don't retry on certain error types
                if (error.message.includes('400') || error.message.includes('401') || error.message.includes('403')) {
                    break;
                }

                // Wait before retry (except on last attempt)
                if (attempt < maxRetries) {
                    const delay = this.retryDelay * Math.pow(2, attempt); // Exponential backoff
                    await this._sleep(delay);
                }
            }
        }

        // Track failed attempts
        this.retryAttempts.set(cacheKey, (this.retryAttempts.get(cacheKey) || 0) + 1);
        throw lastError || new Error('Max retries exceeded');
    }

    /**
     * Fetch cached summaries with pagination
     */
    async getCachedSummaries(page = 1, perPage = 10) {
        return this.request(`/get_cached_summaries?page=${page}&per_page=${perPage}`);
    }

    /**
     * Search summaries
     */
    async searchSummaries(query) {
        return this.request(`/search_summaries?q=${encodeURIComponent(query)}`);
    }

    /**
     * Get API status and available models
     */
    async getAPIStatus() {
        return this.request('/api_status');
    }

    /**
     * Submit URLs for summarization (async processing)
     */
    async submitSummarization(urls, model) {
        return this.request('/summarize', {
            method: 'POST',
            body: JSON.stringify({ urls, model })
        });
    }

    /**
     * Get specific summary by video ID
     */
    async getSummary(videoId) {
        return this.request(`/summary/${videoId}`);
    }

    /**
     * Delete summary
     */
    async deleteSummary(videoId) {
        const result = await this.request('/delete_summary', {
            method: 'DELETE',
            body: JSON.stringify({ video_id: videoId })
        });
        
        // Invalidate related cache entries
        this.invalidateCacheByPattern('get_cached_summaries');
        this.invalidateCacheByPattern('search_summaries');
        
        return result;
    }

    /**
     * Generate speech for text
     */
    async generateSpeech(text) {
        // Don't cache speech requests - they return binary data
        const url = `${this.baseUrl}/speak`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text })
        });

        if (!response.ok) {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to generate speech');
            }
            throw new Error('Failed to generate speech');
        }

        return response.blob();
    }

    /**
     * Refresh cache for specific endpoints
     */
    invalidateCache(endpoint) {
        const keysToDelete = [];
        for (const [key] of this.cache) {
            if (key.includes(endpoint)) {
                keysToDelete.push(key);
            }
        }
        keysToDelete.forEach(key => this.cache.delete(key));
    }

    /**
     * Invalidate cache entries matching a pattern
     */
    invalidateCacheByPattern(pattern) {
        const keysToDelete = [];
        for (const [key] of this.cache) {
            if (key.includes(pattern)) {
                keysToDelete.push(key);
            }
        }
        keysToDelete.forEach(key => this.cache.delete(key));
        console.log(`🗑️ Invalidated ${keysToDelete.length} cache entries matching: ${pattern}`);
    }

    /**
     * Clear all cache
     */
    clearCache() {
        const cacheSize = this.cache.size;
        this.cache.clear();
        console.log(`🗑️ Cleared ${cacheSize} cache entries`);
    }

    /**
     * Get cache statistics
     */
    getCacheStats() {
        const now = Date.now();
        const expired = Array.from(this.cache.values())
            .filter(entry => now - entry.timestamp >= this.cacheExpiry).length;
        
        return {
            total: this.cache.size,
            expired: expired,
            fresh: this.cache.size - expired
        };
    }

    /**
     * Clean expired cache entries
     */
    cleanExpiredCache() {
        const now = Date.now();
        const keysToDelete = [];
        
        for (const [key, entry] of this.cache) {
            if (now - entry.timestamp >= this.cacheExpiry) {
                keysToDelete.push(key);
            }
        }
        
        keysToDelete.forEach(key => this.cache.delete(key));
        
        if (keysToDelete.length > 0) {
            console.log(`🧹 Cleaned ${keysToDelete.length} expired cache entries`);
        }
        
        return keysToDelete.length;
    }

    /**
     * Handle SSE connection failure fallback
     */
    async checkSummaryStatus(videoId) {
        try {
            const summary = await this.getSummary(videoId);
            return summary;
        } catch (error) {
            console.warn(`⚠️ Could not check status for video ${videoId}:`, error);
            return null;
        }
    }

    /**
     * Polling fallback for when SSE is unavailable
     */
    startPolling(videoIds, callback, interval = 5000) {
        const pollFunction = async () => {
            try {
                const results = await Promise.allSettled(
                    videoIds.map(id => this.checkSummaryStatus(id))
                );
                
                results.forEach((result, index) => {
                    if (result.status === 'fulfilled' && result.value) {
                        callback(videoIds[index], result.value);
                    }
                });
                
            } catch (error) {
                console.warn('⚠️ Polling error:', error);
            }
        };

        // Initial poll
        pollFunction();
        
        // Set up interval
        const intervalId = setInterval(pollFunction, interval);
        
        // Return cleanup function
        return () => {
            clearInterval(intervalId);
        };
    }

    /**
     * Utility method to sleep/wait
     */
    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Health check endpoint
     */
    async healthCheck() {
        try {
            const response = await fetch(`${this.baseUrl}/health`, { 
                method: 'GET',
                timeout: 5000 
            });
            return response.ok;
        } catch (error) {
            console.warn('⚠️ Health check failed:', error);
            return false;
        }
    }
}

// Export for ES6 modules or global usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = APIClient;
} else {
    window.APIClient = APIClient;
}