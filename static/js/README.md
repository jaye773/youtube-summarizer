# Client-Side Async Processing Scripts

This directory contains the JavaScript modules for implementing Server-Sent Events (SSE) and async processing support in the YouTube Summarizer application.

## Files Overview

### Core Modules

#### `sse-manager.js`
Manages EventSource connections for real-time server communication.
```javascript
const sseManager = new SSEManager();
sseManager.subscribe('summaryCompleted', (data) => {
    console.log('Summary completed:', data);
});
```

#### `ui-state-manager.js` 
Handles dynamic UI updates, notifications, and progress indicators.
```javascript
const uiManager = new UIStateManager();
uiManager.showNotification('Success', 'Operation completed', 'success');
```

#### `api-client.js`
Provides enhanced API communication with caching and retry logic.
```javascript
const apiClient = new APIClient();
const summaries = await apiClient.getCachedSummaries(1, 20);
```

#### `async-integration.js`
Main orchestration layer that coordinates all async processing features.
```javascript
// Auto-initialized globally as window.asyncIntegration
const status = asyncIntegration.getStatus();
```

## Usage Examples

### Basic Integration
The scripts are automatically loaded and initialized. No manual setup required.

```html
<!-- Scripts are loaded in this order in index.html -->
<script src="/static/js/sse-manager.js"></script>
<script src="/static/js/ui-state-manager.js"></script>
<script src="/static/js/api-client.js"></script>
<script src="/static/js/async-integration.js"></script>
```

### Accessing System Status
```javascript
// Check if async integration is ready
if (window.asyncIntegration && window.asyncIntegration.initialized) {
    console.log('Async processing available');
    
    // Get detailed status
    const status = window.asyncIntegration.getStatus();
    console.log('SSE connected:', status.sse?.isConnected);
    console.log('Pending summaries:', status.pendingSummaries);
}
```

### Manual API Calls
```javascript
// Search summaries with caching
const results = await window.asyncIntegration.apiClient.searchSummaries('keyword');

// Get cache statistics
const cacheStats = window.asyncIntegration.apiClient.getCacheStats();
console.log(`Cache: ${cacheStats.fresh} fresh, ${cacheStats.expired} expired`);

// Clear cache if needed
window.asyncIntegration.apiClient.clearCache();
```

### Custom Event Handling
```javascript
// Subscribe to summary events
window.asyncIntegration.sseManager.subscribe('summaryStarted', (data) => {
    console.log(`Started processing: ${data.title}`);
});

window.asyncIntegration.sseManager.subscribe('summaryProgress', (data) => {
    console.log(`Progress: ${data.progress}%`);
});
```

### Force Reconnection
```javascript
// Force SSE reconnection if needed
window.asyncIntegration.forceReconnect();
```

## Event Flow Diagram

```
User Action (Summarize) 
    ↓
Enhanced Summarize Function
    ↓
API Client → Server (/summarize)
    ↓
Server Returns Job IDs
    ↓
SSE Manager ← Server (progress updates)
    ↓
UI State Manager (notifications)
    ↓
Cache Refresh → Pagination Update
    ↓
User Sees Results
```

## Fallback Behavior

### When SSE is Unavailable
1. **Automatic Detection**: System detects connection failure
2. **Polling Activation**: Falls back to periodic API polling
3. **User Notification**: Informs user of degraded mode
4. **Full Functionality**: All features remain available

### When API is Unavailable
1. **Cached Responses**: Serves cached data when possible
2. **Retry Logic**: Automatic retries with exponential backoff
3. **User Feedback**: Clear error messages
4. **Graceful Degradation**: Core functionality preserved

## Error Handling

### Connection Errors
```javascript
// SSE connection status
window.asyncIntegration.sseManager.subscribe('connection', (data) => {
    if (data.status === 'disconnected') {
        console.log('SSE disconnected, using fallback polling');
    }
});
```

### API Errors
```javascript
try {
    const result = await window.asyncIntegration.enhancedSummarize(urls, model);
} catch (error) {
    console.error('Summarization failed:', error.message);
    // Error notification automatically shown by UI State Manager
}
```

## Configuration

### Timeout Settings
Default values can be modified in respective files:

```javascript
// sse-manager.js
maxReconnectAttempts: 5
reconnectDelay: 1000ms → 30000ms (exponential backoff)
heartbeatTimeout: 30000ms

// api-client.js  
maxRetries: 3
retryDelay: 1000ms (exponential backoff)
cacheExpiry: 300000ms (5 minutes)

// ui-state-manager.js
notificationDuration: 5000ms (auto-dismiss)
progressNotifications: persistent (until completion)
```

## Development Tips

### Console Commands
Available in browser console:
```javascript
// System status
asyncIntegration.getStatus()

// Cache management
asyncIntegration.apiClient.getCacheStats()
asyncIntegration.apiClient.clearCache()

// Force reconnection
asyncIntegration.forceReconnect()

// Manual cleanup
asyncIntegration.cleanup()
```

### Debugging SSE
```javascript
// Monitor SSE events
window.asyncIntegration.sseManager.subscribe('*', (data) => {
    console.log('SSE Event:', data);
});

// Check connection health
const sseStatus = window.asyncIntegration.sseManager.getStatus();
console.log('Ready State:', sseStatus.readyState);
console.log('Reconnect Attempts:', sseStatus.reconnectAttempts);
```

### Testing Fallback Mode
```javascript
// Simulate SSE failure
window.asyncIntegration.sseManager.disconnect();

// Check if polling activated
console.log('Fallback polling active:', 
    window.asyncIntegration.fallbackPolling.size > 0);
```

## Browser Compatibility

- **Modern browsers**: Full SSE support with real-time updates
- **Older browsers**: Automatic fallback to polling mode
- **All browsers**: Core functionality maintained

## Performance Notes

- Single SSE connection per browser tab
- Request deduplication prevents duplicate API calls
- Automatic cache cleanup prevents memory leaks
- Efficient polling intervals in fallback mode (5-10 seconds)

## File Dependencies

```
async-integration.js
    ├── sse-manager.js
    ├── ui-state-manager.js
    └── api-client.js

Load order is important - async-integration.js must be last.
```