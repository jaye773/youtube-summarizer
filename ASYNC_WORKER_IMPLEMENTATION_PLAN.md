# Async Worker Implementation Plan

## Overview
This document coordinates the parallel implementation of an asynchronous worker system for the YouTube Summarizer. Each module is designed to be developed independently without file conflicts.

## Architecture Summary
- **Worker System**: Background threads process summaries asynchronously
- **Job Queue**: Priority-based queue manages work distribution  
- **SSE Notifications**: Real-time updates to connected clients
- **Client Updates**: JavaScript modules for handling async events
- **Integration Layer**: Minimal changes to connect everything

## Module Assignments

### Module 1: Worker Core System
**Owner**: Backend Sub-Agent 1
**Files to Create** (No conflicts with existing files):
- `worker_manager.py` - Main worker thread management
- `job_queue.py` - Job queue and priority handling
- `job_models.py` - Job data models and enums

**Dependencies**: 
- Read-only access to existing `app.py` functions
- Import existing summary generation functions

**Key Implementation Points**:
```python
# job_models.py structure
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

class JobStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"

class JobPriority(Enum):
    HIGH = 1      # Single videos
    MEDIUM = 2    # Small playlists
    LOW = 3       # Large playlists

@dataclass
class ProcessingJob:
    job_id: str
    job_type: str  # "video", "playlist", "batch"
    priority: JobPriority
    data: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = None
    # ... other fields
```

**Integration Point**: Export `WorkerManager` class to be imported by app.py

---

### Module 2: State Management & Persistence
**Owner**: Backend Sub-Agent 2
**Files to Create**:
- `job_state.py` - Job state tracking and persistence
- `error_handler.py` - Error classification and retry logic
- `data/job_state.json` - Persistent storage (auto-created)

**Dependencies**:
- Import from `job_models.py` (Module 1)
- No modifications to existing files

**Key Implementation Points**:
```python
# job_state.py structure
class JobStateManager:
    def __init__(self, persistence_file: str = "data/job_state.json"):
        self.persistence_file = persistence_file
        self.state_cache = {}
        self.lock = threading.RLock()
    
    def update_job_progress(self, job_id: str, progress: float, status: JobStatus = None):
        # Thread-safe progress updates
        pass
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        # Return current job status
        pass
```

**Integration Point**: Export `JobStateManager` and `ErrorHandler` classes

---

### Module 3: SSE Implementation
**Owner**: Backend Sub-Agent 3
**Files to Create**:
- `sse_manager.py` - SSE connection management
- `templates/sse_test.html` - Testing interface

**Dependencies**:
- Import from `job_state.py` (Module 2)
- No modifications to existing files

**Key Implementation Points**:
```python
# sse_manager.py structure
class SSEConnection:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.queue = queue.Queue()
        self.created_at = datetime.now()
    
    def send_event(self, event_type: str, data: Dict[str, Any]):
        # Queue event for sending
        pass

class SSEManager:
    def __init__(self):
        self.connections: Dict[str, SSEConnection] = {}
        self.lock = threading.RLock()
    
    def add_connection(self, client_id: str) -> SSEConnection:
        # Register new SSE connection
        pass
    
    def broadcast_event(self, event_type: str, data: Dict[str, Any], filter_func=None):
        # Send event to multiple clients
        pass
```

**Integration Point**: Export `SSEManager` class and event formatting functions

---

### Module 4: Client-Side JavaScript
**Owner**: Frontend Sub-Agent
**Files to Create**:
- `static/js/sse_client.js` - SSE connection handling
- `static/js/job_tracker.js` - Job progress tracking
- `static/js/ui_updater.js` - UI update functions
- `static/css/async_ui.css` - Async UI styles

**Dependencies**:
- No backend dependencies
- Works with existing `index.html` structure

**Key Implementation Points**:
```javascript
// sse_client.js structure
class SSEClient {
    constructor(endpoint = '/events') {
        this.endpoint = endpoint;
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
    }
    
    connect() {
        this.eventSource = new EventSource(this.endpoint);
        this.setupEventHandlers();
    }
    
    setupEventHandlers() {
        this.eventSource.addEventListener('summary_progress', (e) => {
            const data = JSON.parse(e.data);
            JobTracker.updateProgress(data);
        });
        
        this.eventSource.addEventListener('summary_complete', (e) => {
            const data = JSON.parse(e.data);
            UIUpdater.addCompletedSummary(data);
        });
    }
}
```

**Integration Point**: Initialize in existing index.html with feature detection

---

### Module 5: Integration Layer
**Owner**: Integration Sub-Agent
**Files to Modify** (Minimal changes):
- `app.py` - Add new endpoints and initialization
- `templates/index.html` - Add script tags and UI elements

**Dependencies**:
- Import all modules 1-4
- Minimal modifications to preserve existing functionality

**Key Changes to app.py**:
```python
# At top of app.py
from worker_manager import WorkerManager
from job_state import JobStateManager
from sse_manager import SSEManager

# After existing globals
worker_manager = None
state_manager = None
sse_manager = None

def init_async_system():
    global worker_manager, state_manager, sse_manager
    if worker_manager is None:
        state_manager = JobStateManager()
        sse_manager = SSEManager()
        worker_manager = WorkerManager(state_manager, sse_manager)

# New endpoints (don't modify existing ones)
@app.route("/summarize_async", methods=["POST"])
def summarize_async():
    # Async version of summarize
    pass

@app.route("/jobs/<job_id>/status", methods=["GET"])
def get_job_status(job_id):
    # Get job status
    pass

@app.route("/events")
def sse_stream():
    # SSE endpoint
    pass

# In existing summarize() function, add optional async mode:
# if request.args.get('async') == 'true':
#     return redirect to async version
```

**Key Changes to index.html**:
```html
<!-- Add to head section -->
<link rel="stylesheet" href="/static/css/async_ui.css">

<!-- Add to bottom of body -->
<div id="async-status-container"></div>

<!-- Add before closing body tag -->
<script src="/static/js/sse_client.js"></script>
<script src="/static/js/job_tracker.js"></script>
<script src="/static/js/ui_updater.js"></script>
<script>
// Feature detection and initialization
if (typeof EventSource !== 'undefined') {
    const sseClient = new SSEClient();
    sseClient.connect();
}
</script>
```

---

## Development Timeline

### Phase 1: Core Implementation (Parallel)
- **Module 1**: Worker Core System (2-3 hours)
- **Module 2**: State Management (2-3 hours)  
- **Module 3**: SSE Implementation (2-3 hours)
- **Module 4**: Client JavaScript (2-3 hours)

### Phase 2: Integration (Sequential)
- **Module 5**: Integration Layer (1-2 hours)
- Requires all modules 1-4 complete

### Phase 3: Testing (Parallel)
- Unit tests for each module
- Integration testing
- Performance testing

---

## Testing Strategy

### Module 1 Tests:
```python
# test_worker_manager.py
def test_job_submission():
    # Test job queue submission
    pass

def test_worker_processing():
    # Test worker thread execution
    pass

def test_priority_ordering():
    # Test priority queue ordering
    pass
```

### Module 2 Tests:
```python
# test_job_state.py
def test_state_persistence():
    # Test saving/loading state
    pass

def test_concurrent_updates():
    # Test thread safety
    pass
```

### Module 3 Tests:
```python
# test_sse_manager.py
def test_connection_management():
    # Test SSE connections
    pass

def test_event_broadcasting():
    # Test event distribution
    pass
```

### Module 4 Tests:
```javascript
// test_sse_client.js
describe('SSEClient', () => {
    it('should reconnect on failure', () => {
        // Test reconnection logic
    });
    
    it('should handle events correctly', () => {
        // Test event handling
    });
});
```

---

## Communication Protocol

### Worker → SSE Events:
```json
{
    "event": "summary_progress",
    "data": {
        "job_id": "abc123",
        "video_id": "xyz789",
        "progress": 0.5,
        "status": "processing",
        "message": "Getting transcript..."
    }
}

{
    "event": "summary_complete", 
    "data": {
        "job_id": "abc123",
        "video_id": "xyz789",
        "title": "Video Title",
        "summary": "Summary text...",
        "thumbnail_url": "https://...",
        "cached": false
    }
}
```

### Client → Server API:
```
POST /summarize_async
{
    "url": "youtube.com/watch?v=...",
    "model": "gpt-4o"
}
Response: {"job_id": "abc123", "status": "pending"}

GET /jobs/abc123/status
Response: {"job_id": "abc123", "status": "in_progress", "progress": 0.5}
```

---

## Environment Variables

Add to `.env`:
```
# Worker Configuration
WORKER_THREADS=3
WORKER_MAX_QUEUE_SIZE=100
WORKER_SHUTDOWN_TIMEOUT=30

# SSE Configuration  
SSE_HEARTBEAT_INTERVAL=30
SSE_MAX_CONNECTIONS=100
SSE_RECONNECT_DELAY=1000
```

---

## Rollback Plan

Each phase can be rolled back independently:

1. **Disable Workers**: Set `WORKER_THREADS=0`
2. **Disable SSE**: Remove `/events` endpoint
3. **Disable Client Updates**: Remove script tags from index.html
4. **Full Rollback**: Revert to previous git commit

---

## Success Criteria

### Module 1 (Worker Core):
- [ ] Workers process jobs from queue
- [ ] Priority ordering works correctly
- [ ] Jobs complete successfully

### Module 2 (State Management):
- [ ] State persists across restarts
- [ ] Concurrent updates are thread-safe
- [ ] Error retry logic works

### Module 3 (SSE):
- [ ] Clients receive real-time updates
- [ ] Connection management is stable
- [ ] Events broadcast correctly

### Module 4 (Client JS):
- [ ] SSE connection auto-reconnects
- [ ] UI updates on events
- [ ] Graceful fallback without SSE

### Module 5 (Integration):
- [ ] Async mode works alongside sync
- [ ] No breaking changes to existing flow
- [ ] All modules communicate correctly

---

## Notes for Sub-Agents

1. **Independence**: Each module can be developed and tested independently
2. **No Conflicts**: Each module creates new files (except Module 5)
3. **Clear Interfaces**: Well-defined integration points between modules
4. **Backward Compatible**: Existing functionality must continue working
5. **Error Handling**: Each module must handle its own errors gracefully
6. **Logging**: Use Python's logging module with appropriate levels
7. **Documentation**: Add docstrings to all classes and methods
8. **Type Hints**: Use type hints for better code clarity

---

## Contact Points

For questions about:
- **Worker Architecture**: See Module 1 spec
- **State Management**: See Module 2 spec
- **SSE Protocol**: See Module 3 spec
- **Client Updates**: See Module 4 spec
- **Integration**: See Module 5 spec

Each sub-agent should focus on their assigned module and ensure it works standalone before integration.