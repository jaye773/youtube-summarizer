# YouTube Summarizer Worker Thread Migration Plan

## Overview

This document outlines a comprehensive 4-phase migration plan to transform the YouTube Summarizer from synchronous processing to an asynchronous worker thread system with Server-Sent Events (SSE) notifications, while maintaining complete backward compatibility and zero-downtime deployment.

## Current Architecture Analysis

### Existing System
- **Frontend**: Single-page HTML application with inline JavaScript
- **Backend**: Flask application with synchronous `/summarize` endpoint
- **Processing**: Direct API calls to Google Gemini/OpenAI in request thread
- **Caching**: File-based summary cache with JSON storage
- **TTS**: Google Cloud Text-to-Speech with audio file caching
- **Authentication**: Optional login system with session management

### Key Components
- `app.py`: Main Flask application (1841 lines)
- `templates/index.html`: Frontend with embedded JavaScript (895 lines)
- `voice_config.py`: TTS voice configuration and caching
- Summary processing in `/summarize` endpoint (lines 1069-1290)
- Frontend polling via periodic cache refresh

## Phase 1: Add Worker Thread Infrastructure (Non-Breaking)

### Goals
- ✅ Add worker thread system alongside existing synchronous flow
- ✅ Maintain 100% backward compatibility
- ✅ Zero impact on current users
- ✅ Foundation for async processing

### Implementation Steps

#### 1.1 Create Job Management System

```python
# jobs.py - New file
import uuid
import json
import time
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from enum import Enum

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Job:
    id: str
    type: str
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: int = 0
    total_items: int = 1
    current_item: str = ""
    results: List[Dict] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self):
        return asdict(self)

class JobManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.jobs_file = os.path.join(data_dir, "jobs.json")
        self.jobs: Dict[str, Job] = {}
        self.lock = threading.RLock()
        self.load_jobs()
    
    def create_job(self, job_type: str, metadata: Dict = None) -> str:
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            type=job_type,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            results=[],
            metadata=metadata or {}
        )
        
        with self.lock:
            self.jobs[job_id] = job
            self.save_jobs()
        
        return job_id
    
    def update_job(self, job_id: str, **updates) -> bool:
        with self.lock:
            if job_id not in self.jobs:
                return False
            
            job = self.jobs[job_id]
            for key, value in updates.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            
            self.save_jobs()
            return True
    
    def get_job(self, job_id: str) -> Optional[Job]:
        with self.lock:
            return self.jobs.get(job_id)
    
    def load_jobs(self):
        try:
            if os.path.exists(self.jobs_file):
                with open(self.jobs_file, 'r') as f:
                    data = json.load(f)
                    for job_data in data:
                        job = Job(**job_data)
                        job.status = JobStatus(job.status)
                        self.jobs[job.id] = job
        except Exception as e:
            print(f"Warning: Could not load jobs: {e}")
            self.jobs = {}
    
    def save_jobs(self):
        try:
            job_data = [job.to_dict() for job in self.jobs.values()]
            with open(self.jobs_file, 'w') as f:
                json.dump(job_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save jobs: {e}")
```

#### 1.2 Create Worker Thread System

```python
# workers.py - New file
import threading
import queue
import time
from typing import Callable, Dict, Any
from jobs import JobManager, JobStatus
from app import generate_summary, get_transcript, get_video_details, get_videos_from_playlist

class WorkerPool:
    def __init__(self, job_manager: JobManager, num_workers: int = 2):
        self.job_manager = job_manager
        self.num_workers = num_workers
        self.workers = []
        self.task_queue = queue.Queue()
        self.shutdown_event = threading.Event()
        
        # Start worker threads
        for i in range(num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"SummarizerWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
    
    def submit_job(self, job_id: str, job_type: str, task_data: Dict[str, Any]):
        """Submit a job to the worker pool."""
        self.task_queue.put({
            'job_id': job_id,
            'job_type': job_type,
            'task_data': task_data
        })
    
    def _worker_loop(self):
        """Main worker loop - processes jobs from queue."""
        while not self.shutdown_event.is_set():
            try:
                # Get task with timeout to allow checking shutdown
                task = self.task_queue.get(timeout=1.0)
                self._process_task(task)
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Worker error: {e}")
    
    def _process_task(self, task: Dict[str, Any]):
        """Process a single task."""
        job_id = task['job_id']
        job_type = task['job_type']
        task_data = task['task_data']
        
        # Update job status to running
        self.job_manager.update_job(
            job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat()
        )
        
        try:
            if job_type == 'summarize':
                self._process_summarize_job(job_id, task_data)
            else:
                raise ValueError(f"Unknown job type: {job_type}")
                
        except Exception as e:
            self.job_manager.update_job(
                job_id,
                status=JobStatus.FAILED,
                error=str(e),
                completed_at=datetime.now(timezone.utc).isoformat()
            )
    
    def _process_summarize_job(self, job_id: str, task_data: Dict[str, Any]):
        """Process a summarization job - mirrors existing synchronous logic."""
        urls = task_data.get('urls', [])
        model_key = task_data.get('model', 'gemini-2.5-flash')
        
        # Update total items count
        self.job_manager.update_job(job_id, total_items=len(urls))
        
        results = []
        for i, url in enumerate(urls):
            # Update progress
            self.job_manager.update_job(
                job_id,
                progress=i,
                current_item=url
            )
            
            # Process URL (using existing logic from app.py)
            try:
                result = self._process_single_url(url, model_key)
                results.append(result)
            except Exception as e:
                results.append({
                    "type": "error",
                    "url": url,
                    "error": str(e)
                })
        
        # Mark job as completed
        self.job_manager.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=len(urls),
            results=results,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _process_single_url(self, url: str, model_key: str) -> Dict[str, Any]:
        """Process a single URL - extracted from existing app.py logic."""
        # This would contain the exact same logic as the current synchronous processing
        # Just extracted into a separate method
        pass  # Implementation mirrors app.py lines 1091-1274
    
    def shutdown(self):
        """Shutdown the worker pool gracefully."""
        self.shutdown_event.set()
        for worker in self.workers:
            worker.join(timeout=5.0)
```

#### 1.3 Update Flask Application

```python
# Add to app.py
from jobs import JobManager, JobStatus
from workers import WorkerPool

# Initialize job system (add after line 175)
job_manager = JobManager(DATA_DIR)
worker_pool = WorkerPool(job_manager, num_workers=2)

# Add new async endpoint (preserve existing /summarize)
@app.route("/summarize_async", methods=["POST"])
@require_auth
def summarize_async():
    """Async version of summarize - creates job and returns immediately."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
        
        urls = data.get("urls", [])
        if not urls:
            return jsonify({"error": "No URLs provided"}), 400
        
        model_key = data.get("model", DEFAULT_MODEL)
        if model_key not in AVAILABLE_MODELS:
            available_models = list(AVAILABLE_MODELS.keys())
            return jsonify({
                "error": f"Unsupported model: {model_key}. Available models: {available_models}"
            }), 400
        
        # Create job
        job_id = job_manager.create_job(
            job_type="summarize",
            metadata={
                "urls": urls,
                "model": model_key,
                "user_session": session.get("user_id", "anonymous")
            }
        )
        
        # Submit to worker pool
        worker_pool.submit_job(job_id, "summarize", {
            "urls": urls,
            "model": model_key
        })
        
        return jsonify({
            "job_id": job_id,
            "status": "accepted",
            "message": "Job submitted for processing"
        }), 202
        
    except Exception as e:
        app.logger.error(f"Error in async summarize: {e}")
        return jsonify({
            "error": "Failed to submit job",
            "message": str(e)
        }), 500

@app.route("/jobs/<job_id>", methods=["GET"])
@require_auth
def get_job_status(job_id: str):
    """Get status of a job."""
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify(job.to_dict())

@app.route("/jobs/<job_id>/cancel", methods=["POST"])
@require_auth
def cancel_job(job_id: str):
    """Cancel a running job."""
    success = job_manager.update_job(job_id, status=JobStatus.CANCELLED)
    if not success:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify({"message": "Job cancelled"})
```

#### 1.4 Add Configuration Flag

```python
# Add to app.py configuration section (after line 282)
ASYNC_PROCESSING_ENABLED = os.environ.get("ASYNC_PROCESSING_ENABLED", "false").lower() == "true"
```

### Testing Strategy for Phase 1

#### 1.4.1 Unit Tests
```bash
# Test job management
python -m pytest tests/test_jobs.py -v

# Test worker pool
python -m pytest tests/test_workers.py -v
```

#### 1.4.2 Integration Tests
```bash
# Test async endpoint alongside existing synchronous endpoint
curl -X POST http://localhost:5001/summarize_async \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.youtube.com/watch?v=test"], "model": "gemini-2.5-flash"}'

# Verify job status endpoint
curl http://localhost:5001/jobs/{job_id}
```

#### 1.4.3 Compatibility Tests
```bash
# Verify existing synchronous endpoint still works
curl -X POST http://localhost:5001/summarize \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.youtube.com/watch?v=test"]}'
```

### Rollback Procedure Phase 1
- **Issue Detection**: Monitor error rates, response times, memory usage
- **Quick Rollback**: Set `ASYNC_PROCESSING_ENABLED=false` environment variable
- **Complete Rollback**: Remove new files (jobs.py, workers.py) and revert app.py
- **Verification**: Confirm all existing functionality works normally

---

## Phase 2: Implement SSE Notifications (Backward Compatible)

### Goals  
- ✅ Add Server-Sent Events for real-time updates
- ✅ Maintain existing polling-based system
- ✅ Progressive enhancement for modern clients
- ✅ Fallback gracefully for older browsers

### Implementation Steps

#### 2.1 Add SSE Endpoint

```python
# Add to app.py
import json
from flask import Response, stream_template

@app.route("/jobs/<job_id>/stream")
@require_auth
def stream_job_progress(job_id: str):
    """Stream job progress via Server-Sent Events."""
    def event_stream():
        job = job_manager.get_job(job_id)
        if not job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return
        
        last_status = None
        last_progress = None
        
        # Send initial status
        yield f"data: {json.dumps(job.to_dict())}\n\n"
        
        # Poll for updates (every 1 second)
        while True:
            job = job_manager.get_job(job_id)
            if not job:
                break
            
            # Send updates only when something changes
            if (job.status != last_status or 
                job.progress != last_progress):
                yield f"data: {json.dumps(job.to_dict())}\n\n"
                last_status = job.status
                last_progress = job.progress
            
            # Stop streaming when job is complete/failed/cancelled
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break
            
            time.sleep(1)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        }
    )

@app.route("/sse_test")
@require_auth 
def sse_test_page():
    """Test page for SSE functionality."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>SSE Test</title></head>
    <body>
        <div id="status">Waiting for events...</div>
        <script>
        const eventSource = new EventSource('/jobs/test-job-id/stream');
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            document.getElementById('status').textContent = JSON.stringify(data, null, 2);
        };
        eventSource.onerror = function(event) {
            document.getElementById('status').textContent = 'Error: ' + event;
        };
        </script>
    </body>
    </html>
    """
```

#### 2.2 Update Frontend - Add SSE Support with Fallback

```javascript
// Add to templates/index.html <script> section (after line 892)

// SSE-enabled job tracking with polling fallback
class JobTracker {
    constructor(jobId, onUpdate, onComplete) {
        this.jobId = jobId;
        this.onUpdate = onUpdate;
        this.onComplete = onComplete;
        this.eventSource = null;
        this.pollInterval = null;
        this.useSSE = this.detectSSESupport();
        
        this.start();
    }
    
    detectSSESupport() {
        // Check for EventSource support and feature flag
        return typeof(EventSource) !== "undefined" && 
               localStorage.getItem('sse_enabled') !== 'false';
    }
    
    start() {
        if (this.useSSE) {
            this.startSSE();
        } else {
            this.startPolling();
        }
    }
    
    startSSE() {
        console.log('Starting SSE for job:', this.jobId);
        this.eventSource = new EventSource(`/jobs/${this.jobId}/stream`);
        
        this.eventSource.onmessage = (event) => {
            try {
                const jobData = JSON.parse(event.data);
                this.handleUpdate(jobData);
            } catch (e) {
                console.error('Failed to parse SSE data:', e);
                this.fallbackToPolling();
            }
        };
        
        this.eventSource.onerror = (event) => {
            console.warn('SSE error, falling back to polling:', event);
            this.fallbackToPolling();
        };
        
        // Timeout fallback after 30 seconds
        setTimeout(() => {
            if (this.eventSource && this.eventSource.readyState === EventSource.CONNECTING) {
                console.warn('SSE connection timeout, falling back to polling');
                this.fallbackToPolling();
            }
        }, 30000);
    }
    
    startPolling() {
        console.log('Starting polling for job:', this.jobId);
        this.pollInterval = setInterval(() => {
            this.pollJobStatus();
        }, 2000); // Poll every 2 seconds
        
        // Initial poll
        this.pollJobStatus();
    }
    
    async pollJobStatus() {
        try {
            const response = await fetch(`/jobs/${this.jobId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const jobData = await response.json();
            this.handleUpdate(jobData);
            
        } catch (error) {
            console.error('Polling error:', error);
            // Continue polling unless it's a 404 (job not found)
            if (error.message.includes('404')) {
                this.stop();
                this.onComplete({ error: 'Job not found' });
            }
        }
    }
    
    handleUpdate(jobData) {
        // Call update handler
        this.onUpdate(jobData);
        
        // Check if job is complete
        if (['completed', 'failed', 'cancelled'].includes(jobData.status)) {
            this.stop();
            this.onComplete(jobData);
        }
    }
    
    fallbackToPolling() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.useSSE = false;
        localStorage.setItem('sse_enabled', 'false'); // Remember preference
        this.startPolling();
    }
    
    stop() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }
}

// Enhanced async summarize function
async function summarizeAsync() {
    if (currentAudioPlayer.state !== 'stopped') {
        player.pause();
        resetAudioPlayerUI();
    }
    
    const urls = linksTextarea.value.split('\n').filter(url => url.trim() !== '');
    if (urls.length === 0) {
        alert('Please paste at least one YouTube link.');
        return;
    }
    
    // Check if async processing is enabled
    const useAsync = localStorage.getItem('async_enabled') === 'true';
    
    if (!useAsync) {
        // Fall back to synchronous processing
        return summarizeSync();
    }
    
    summarizeBtn.disabled = true;
    summarizeBtn.textContent = 'Starting...';
    loader.style.display = 'block';
    
    try {
        const selectedModel = document.getElementById('model-select').value;
        const response = await fetch('/summarize_async', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                urls: urls,
                model: selectedModel
            }),
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to start job');
        }
        
        const jobInfo = await response.json();
        const jobId = jobInfo.job_id;
        
        // Create progress display
        const progressContainer = createProgressDisplay(jobId);
        document.getElementById('new-results').appendChild(progressContainer);
        
        // Start tracking job
        const tracker = new JobTracker(
            jobId,
            (jobData) => updateJobProgress(jobId, jobData),
            (jobData) => handleJobComplete(jobId, jobData)
        );
        
        // Store tracker for cleanup
        progressContainer.tracker = tracker;
        
    } catch (error) {
        console.error('Error starting async job:', error);
        alert(`Failed to start processing: ${error.message}`);
        summarizeBtn.disabled = false;
        summarizeBtn.textContent = 'Summarize Links';
        loader.style.display = 'none';
    }
}

function createProgressDisplay(jobId) {
    const container = document.createElement('div');
    container.className = 'job-progress';
    container.id = `job-${jobId}`;
    container.innerHTML = `
        <div class="progress-header">
            <h3>Processing URLs...</h3>
            <button class="cancel-btn" onclick="cancelJob('${jobId}')">Cancel</button>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div class="progress-status">Initializing...</div>
        <div class="current-item"></div>
    `;
    return container;
}

function updateJobProgress(jobId, jobData) {
    const container = document.getElementById(`job-${jobId}`);
    if (!container) return;
    
    const progressFill = container.querySelector('.progress-fill');
    const statusEl = container.querySelector('.progress-status');
    const currentItemEl = container.querySelector('.current-item');
    
    // Update progress bar
    const progressPercent = jobData.total_items > 0 
        ? (jobData.progress / jobData.total_items) * 100 
        : 0;
    progressFill.style.width = `${progressPercent}%`;
    
    // Update status
    statusEl.textContent = `${jobData.status} - ${jobData.progress}/${jobData.total_items}`;
    
    // Update current item
    if (jobData.current_item) {
        currentItemEl.textContent = `Processing: ${jobData.current_item}`;
    }
}

function handleJobComplete(jobId, jobData) {
    const container = document.getElementById(`job-${jobId}`);
    if (!container) return;
    
    // Clean up tracker
    if (container.tracker) {
        container.tracker.stop();
    }
    
    if (jobData.status === 'completed' && jobData.results) {
        // Display results
        const newResultsContainer = document.getElementById('new-results');
        displayResults(jobData.results, newResultsContainer, true);
        
        // Remove progress display
        container.remove();
        
        // Refresh pagination
        loadPaginatedSummaries(currentPage, currentPageSize);
        
    } else if (jobData.status === 'failed') {
        container.querySelector('.progress-status').textContent = `Failed: ${jobData.error}`;
        container.classList.add('error');
    }
    
    // Re-enable summarize button
    summarizeBtn.disabled = false;
    summarizeBtn.textContent = 'Summarize Links';
    loader.style.display = 'none';
    linksTextarea.value = '';
}

async function cancelJob(jobId) {
    try {
        await fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
        const container = document.getElementById(`job-${jobId}`);
        if (container && container.tracker) {
            container.tracker.stop();
        }
    } catch (error) {
        console.error('Failed to cancel job:', error);
    }
}

// Add feature detection and progressive enhancement
document.addEventListener('DOMContentLoaded', () => {
    // Check if async processing should be enabled
    fetch('/api_status')
        .then(r => r.json())
        .then(status => {
            if (status.async_processing_enabled) {
                localStorage.setItem('async_enabled', 'true');
                // Add UI toggle for users to disable if needed
                addAsyncToggle();
            }
        })
        .catch(e => console.warn('Could not check async status:', e));
});

function addAsyncToggle() {
    // Add toggle in settings or header for users to enable/disable async mode
    const toggle = document.createElement('label');
    toggle.innerHTML = `
        <input type="checkbox" id="async-toggle" 
               ${localStorage.getItem('async_enabled') === 'true' ? 'checked' : ''}> 
        Real-time processing
    `;
    
    toggle.querySelector('input').addEventListener('change', (e) => {
        localStorage.setItem('async_enabled', e.target.checked ? 'true' : 'false');
    });
    
    document.querySelector('.header').appendChild(toggle);
}

// Update existing event listener to use new async function
// summarizeBtn.addEventListener('click', summarizeAsync);
```

#### 2.3 Add CSS for Progress Display

```css
/* Add to templates/index.html <style> section */
.job-progress {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 20px;
    margin: 20px 0;
}

.progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
}

.progress-header h3 {
    margin: 0;
    color: #495057;
}

.cancel-btn {
    background-color: #dc3545;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
}

.cancel-btn:hover {
    background-color: #c82333;
}

.progress-bar {
    width: 100%;
    height: 20px;
    background-color: #e9ecef;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 10px;
}

.progress-bar .progress-fill {
    height: 100%;
    background-color: #8e44ad;
    transition: width 0.3s ease;
}

.progress-status {
    font-weight: bold;
    color: #495057;
    margin-bottom: 5px;
}

.current-item {
    font-size: 14px;
    color: #6c757d;
    word-break: break-all;
}

.job-progress.error {
    border-color: #dc3545;
    background-color: #f8d7da;
}

.job-progress.error .progress-status {
    color: #721c24;
}
```

### Testing Strategy for Phase 2

#### 2.4.1 SSE Functionality Tests
```javascript
// Manual test in browser console
const eventSource = new EventSource('/jobs/test-job-id/stream');
eventSource.onmessage = (e) => console.log('SSE:', JSON.parse(e.data));
eventSource.onerror = (e) => console.log('SSE Error:', e);
```

#### 2.4.2 Fallback Tests
```javascript
// Test polling fallback
localStorage.setItem('sse_enabled', 'false');
// Then test job tracking
```

#### 2.4.3 Cross-browser Tests
- Chrome (SSE supported)
- Safari (SSE supported)  
- Firefox (SSE supported)
- IE11/Edge Legacy (polling fallback)

### Rollback Procedure Phase 2
- **Issue Detection**: SSE connection failures, high server load, browser compatibility issues
- **Quick Fix**: Disable SSE via localStorage flag (`sse_enabled=false`)
- **Server Rollback**: Remove SSE endpoints, revert to Phase 1 state
- **Validation**: Confirm polling fallback works for all users

---

## Phase 3: Migrate Client to SSE with Fallback

### Goals
- ✅ Make SSE the default for real-time updates  
- ✅ Maintain robust polling fallback
- ✅ Optimize user experience
- ✅ Provide user control over connection method

### Implementation Steps

#### 3.1 Enhanced Feature Detection

```javascript
// Add advanced SSE feature detection
class ConnectionManager {
    constructor() {
        this.sseSupported = typeof(EventSource) !== "undefined";
        this.sseEnabled = this.detectSSEPreference();
        this.connectionQuality = 'unknown';
        this.failureCount = 0;
        this.maxFailures = 3;
        
        this.detectConnectionQuality();
    }
    
    detectSSEPreference() {
        const userPreference = localStorage.getItem('connection_method');
        
        // Check user preference first
        if (userPreference) {
            return userPreference === 'sse';
        }
        
        // Auto-detect based on browser and network
        if (!this.sseSupported) {
            return false;
        }
        
        // Check for mobile browsers that might have issues
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
            navigator.userAgent
        );
        
        // Default to SSE for desktop, polling for mobile (can be overridden)
        return !isMobile;
    }
    
    async detectConnectionQuality() {
        try {
            const startTime = performance.now();
            await fetch('/api_status');
            const latency = performance.now() - startTime;
            
            if (latency < 100) {
                this.connectionQuality = 'excellent';
            } else if (latency < 300) {
                this.connectionQuality = 'good';
            } else if (latency < 1000) {
                this.connectionQuality = 'fair';
            } else {
                this.connectionQuality = 'poor';
            }
            
            console.log(`Connection quality: ${this.connectionQuality} (${latency}ms)`);
            
        } catch (error) {
            this.connectionQuality = 'poor';
        }
    }
    
    shouldUseSSE() {
        return this.sseSupported && 
               this.sseEnabled && 
               this.failureCount < this.maxFailures &&
               this.connectionQuality !== 'poor';
    }
    
    recordFailure() {
        this.failureCount++;
        if (this.failureCount >= this.maxFailures) {
            console.warn('SSE failed too many times, switching to polling');
            localStorage.setItem('connection_method', 'polling');
        }
    }
    
    recordSuccess() {
        this.failureCount = 0;
    }
    
    setPreference(method) {
        localStorage.setItem('connection_method', method);
        this.sseEnabled = (method === 'sse');
        this.failureCount = 0; // Reset failures when user explicitly changes
    }
}

const connectionManager = new ConnectionManager();
```

#### 3.2 Enhanced Job Tracker with Smart Fallback

```javascript
// Enhanced JobTracker with better error handling and user feedback
class EnhancedJobTracker {
    constructor(jobId, onUpdate, onComplete, onError) {
        this.jobId = jobId;
        this.onUpdate = onUpdate;
        this.onComplete = onComplete;
        this.onError = onError;
        
        this.eventSource = null;
        this.pollInterval = null;
        this.connectionMethod = null;
        this.startTime = Date.now();
        this.lastUpdateTime = Date.now();
        
        // Heartbeat detection
        this.heartbeatInterval = null;
        this.heartbeatMissed = 0;
        this.maxMissedHeartbeats = 3;
        
        this.start();
    }
    
    start() {
        if (connectionManager.shouldUseSSE()) {
            this.startSSE();
        } else {
            this.startPolling();
        }
    }
    
    startSSE() {
        this.connectionMethod = 'sse';
        console.log(`Starting SSE for job ${this.jobId}`);
        
        try {
            this.eventSource = new EventSource(`/jobs/${this.jobId}/stream`);
            
            this.eventSource.onopen = () => {
                console.log('SSE connection opened');
                connectionManager.recordSuccess();
                this.showConnectionStatus('Connected via real-time stream');
                this.startHeartbeat();
            };
            
            this.eventSource.onmessage = (event) => {
                this.lastUpdateTime = Date.now();
                this.heartbeatMissed = 0;
                
                try {
                    const jobData = JSON.parse(event.data);
                    
                    // Handle special messages
                    if (jobData.type === 'heartbeat') {
                        return;
                    }
                    
                    if (jobData.error) {
                        this.onError(jobData.error);
                        return;
                    }
                    
                    this.handleUpdate(jobData);
                    
                } catch (e) {
                    console.error('Failed to parse SSE data:', e);
                    this.fallbackToPolling('Invalid data received');
                }
            };
            
            this.eventSource.onerror = (event) => {
                console.warn('SSE error:', event);
                connectionManager.recordFailure();
                
                // Check if this is a temporary network issue
                if (this.eventSource.readyState === EventSource.CLOSED) {
                    this.fallbackToPolling('Connection lost');
                } else {
                    // Connection might recover, wait a moment
                    setTimeout(() => {
                        if (this.eventSource && this.eventSource.readyState === EventSource.CLOSED) {
                            this.fallbackToPolling('Connection failed to recover');
                        }
                    }, 5000);
                }
            };
            
            // Connection timeout
            setTimeout(() => {
                if (this.eventSource && this.eventSource.readyState === EventSource.CONNECTING) {
                    console.warn('SSE connection timeout');
                    this.fallbackToPolling('Connection timeout');
                }
            }, 15000);
            
        } catch (error) {
            console.error('Failed to create SSE connection:', error);
            this.fallbackToPolling('Failed to establish connection');
        }
    }
    
    startHeartbeat() {
        // Monitor for missed heartbeats to detect stale connections
        this.heartbeatInterval = setInterval(() => {
            const timeSinceLastUpdate = Date.now() - this.lastUpdateTime;
            
            if (timeSinceLastUpdate > 30000) { // 30 seconds without any message
                this.heartbeatMissed++;
                
                if (this.heartbeatMissed >= this.maxMissedHeartbeats) {
                    console.warn('SSE connection appears stale, falling back to polling');
                    this.fallbackToPolling('Connection stale');
                }
            }
        }, 10000); // Check every 10 seconds
    }
    
    startPolling() {
        this.connectionMethod = 'polling';
        console.log(`Starting polling for job ${this.jobId}`);
        
        this.showConnectionStatus('Connected via periodic updates');
        
        // Adaptive polling interval based on connection quality
        let pollInterval = 2000; // Default 2 seconds
        
        if (connectionManager.connectionQuality === 'excellent') {
            pollInterval = 1000;
        } else if (connectionManager.connectionQuality === 'poor') {
            pollInterval = 5000;
        }
        
        this.pollInterval = setInterval(() => {
            this.pollJobStatus();
        }, pollInterval);
        
        // Initial poll
        this.pollJobStatus();
    }
    
    async pollJobStatus() {
        try {
            const response = await fetch(`/jobs/${this.jobId}`, {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            });
            
            if (!response.ok) {
                if (response.status === 404) {
                    this.onError('Job not found');
                    return;
                } else {
                    throw new Error(`HTTP ${response.status}`);
                }
            }
            
            const jobData = await response.json();
            this.handleUpdate(jobData);
            
        } catch (error) {
            console.error('Polling error:', error);
            this.showConnectionStatus(`Connection error: ${error.message}`);
            
            // Don't stop polling for temporary errors
            // The interval will continue and hopefully recover
        }
    }
    
    handleUpdate(jobData) {
        this.onUpdate(jobData);
        
        // Check if job is complete
        if (['completed', 'failed', 'cancelled'].includes(jobData.status)) {
            this.stop();
            this.onComplete(jobData);
        }
    }
    
    fallbackToPolling(reason) {
        console.log(`Falling back to polling: ${reason}`);
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
        
        connectionManager.recordFailure();
        this.startPolling();
    }
    
    showConnectionStatus(message) {
        // Show connection status to user
        const jobContainer = document.getElementById(`job-${this.jobId}`);
        if (jobContainer) {
            let statusEl = jobContainer.querySelector('.connection-status');
            if (!statusEl) {
                statusEl = document.createElement('div');
                statusEl.className = 'connection-status';
                jobContainer.querySelector('.progress-header').appendChild(statusEl);
            }
            statusEl.textContent = message;
            statusEl.className = `connection-status ${this.connectionMethod}`;
        }
    }
    
    stop() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
}
```

#### 3.3 User Settings for Connection Method

```javascript
// Add connection method settings to existing settings page or create inline toggle
function createConnectionSettings() {
    const settingsHTML = `
        <div class="connection-settings">
            <h4>Connection Method</h4>
            <label>
                <input type="radio" name="connection-method" value="auto" 
                       ${!localStorage.getItem('connection_method') ? 'checked' : ''}>
                Auto (Recommended)
            </label>
            <label>
                <input type="radio" name="connection-method" value="sse"
                       ${localStorage.getItem('connection_method') === 'sse' ? 'checked' : ''}>
                Real-time (faster updates)
            </label>
            <label>
                <input type="radio" name="connection-method" value="polling"
                       ${localStorage.getItem('connection_method') === 'polling' ? 'checked' : ''}>
                Periodic (more compatible)
            </label>
            <small>Real-time provides instant updates but may not work on all networks. 
                   Periodic works everywhere but updates every few seconds.</small>
        </div>
    `;
    
    // Add event listeners
    document.querySelectorAll('input[name="connection-method"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'auto') {
                localStorage.removeItem('connection_method');
            } else {
                localStorage.setItem('connection_method', e.target.value);
            }
            connectionManager.setPreference(e.target.value);
        });
    });
}

// Add to existing settings page or create inline toggle
document.addEventListener('DOMContentLoaded', () => {
    createConnectionSettings();
});
```

#### 3.4 Enhanced Backend SSE with Heartbeat

```python
# Update SSE endpoint in app.py with heartbeat support
@app.route("/jobs/<job_id>/stream")
@require_auth
def stream_job_progress(job_id: str):
    """Stream job progress via Server-Sent Events with heartbeat."""
    def event_stream():
        job = job_manager.get_job(job_id)
        if not job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return
        
        last_status = None
        last_progress = None
        last_heartbeat = time.time()
        
        # Send initial status
        yield f"data: {json.dumps(job.to_dict())}\n\n"
        
        while True:
            current_time = time.time()
            job = job_manager.get_job(job_id)
            
            if not job:
                yield f"data: {json.dumps({'error': 'Job lost'})}\n\n"
                break
            
            # Send heartbeat every 15 seconds
            if current_time - last_heartbeat > 15:
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': current_time})}\n\n"
                last_heartbeat = current_time
            
            # Send updates when something changes
            if (job.status != last_status or job.progress != last_progress):
                yield f"data: {json.dumps(job.to_dict())}\n\n"
                last_status = job.status
                last_progress = job.progress
            
            # Stop streaming when job is complete
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break
            
            time.sleep(1)
    
    response = Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        }
    )
    
    # Handle client disconnect gracefully
    @response.call_on_close
    def on_close():
        print(f"SSE client disconnected from job {job_id}")
    
    return response
```

### Testing Strategy for Phase 3

#### 3.5.1 Connection Method Tests
```bash
# Test SSE preference detection
# Test connection quality detection  
# Test fallback scenarios
# Test user preference persistence
```

#### 3.5.2 Network Condition Tests
```bash
# Test poor connection conditions
# Test intermittent connectivity
# Test high latency scenarios
# Test mobile network conditions
```

#### 3.5.3 User Experience Tests
```bash
# Test connection status display
# Test user preference settings
# Test graceful degradation
# Test error messaging
```

### Rollback Procedure Phase 3
- **Quick Rollback**: Set all clients to polling mode via localStorage
- **Feature Toggle**: Disable SSE via server-side flag  
- **Full Rollback**: Revert to Phase 2 implementation
- **Monitor**: Watch for user complaints about connection issues

---

## Phase 4: Full Async Mode with Backward Compatibility

### Goals
- ✅ Make async processing the default experience
- ✅ Maintain synchronous mode for compatibility
- ✅ Optimize performance and resource usage
- ✅ Provide seamless user experience

### Implementation Steps  

#### 4.1 Smart Mode Selection

```python
# Add intelligent async/sync selection to app.py
def should_use_async_processing(urls: List[str], model: str, user_agent: str = "") -> bool:
    """Determine if request should use async processing."""
    
    # Always use sync for single URLs (faster for simple cases)
    if len(urls) <= 1:
        return False
    
    # Use async for playlists or multiple videos
    if len(urls) > 1:
        return True
    
    # Check for complex processing requirements
    heavy_models = ['gpt-5', 'gemini-2.5-pro']
    if model in heavy_models:
        return True
    
    # Check user agent for API clients that might expect sync
    if 'curl' in user_agent.lower() or 'postman' in user_agent.lower():
        return False
    
    return True

@app.route("/summarize", methods=["POST"])
@require_auth
def summarize_adaptive():
    """Adaptive summarize endpoint - chooses sync or async automatically."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
        
        urls = data.get("urls", [])
        if not urls:
            return jsonify({"error": "No URLs provided"}), 400
        
        model_key = data.get("model", DEFAULT_MODEL)
        user_agent = request.headers.get('User-Agent', '')
        force_sync = data.get("force_sync", False)
        force_async = data.get("force_async", False)
        
        # Determine processing mode
        use_async = False
        if force_sync:
            use_async = False
        elif force_async:
            use_async = True  
        elif ASYNC_PROCESSING_ENABLED:
            use_async = should_use_async_processing(urls, model_key, user_agent)
        
        if use_async:
            return handle_async_request(urls, model_key, data)
        else:
            return handle_sync_request(urls, model_key, data)
            
    except Exception as e:
        app.logger.error(f"Error in adaptive summarize: {e}")
        return jsonify({
            "error": "An unexpected error occurred",
            "message": str(e)
        }), 500

def handle_async_request(urls: List[str], model_key: str, data: dict):
    """Handle request asynchronously."""
    # Validate model
    if model_key not in AVAILABLE_MODELS:
        available_models = list(AVAILABLE_MODELS.keys())
        return jsonify({
            "error": f"Unsupported model: {model_key}. Available models: {available_models}"
        }), 400
    
    # Create job
    job_id = job_manager.create_job(
        job_type="summarize",
        metadata={
            "urls": urls,
            "model": model_key,
            "user_session": session.get("user_id", "anonymous"),
            "created_by": "adaptive_endpoint"
        }
    )
    
    # Submit to worker pool  
    worker_pool.submit_job(job_id, "summarize", {
        "urls": urls,
        "model": model_key
    })
    
    return jsonify({
        "mode": "async",
        "job_id": job_id,
        "status": "accepted", 
        "message": "Job submitted for processing",
        "stream_url": f"/jobs/{job_id}/stream",
        "status_url": f"/jobs/{job_id}",
        "estimated_time": estimate_processing_time(urls, model_key)
    }), 202

def handle_sync_request(urls: List[str], model_key: str, data: dict):
    """Handle request synchronously - existing logic."""
    # This contains the existing synchronous logic from the original /summarize endpoint
    # (lines 1089-1275 from original app.py)
    
    # Validate model
    if model_key not in AVAILABLE_MODELS:
        available_models = list(AVAILABLE_MODELS.keys())
        return jsonify({
            "error": f"Unsupported model: {model_key}. Available models: {available_models}"
        }), 400
    
    # Process synchronously
    results = []
    
    # [Existing processing logic here - exact same as before]
    for url in urls:
        playlist_id, video_id = get_playlist_id(url), get_video_id(url)
        
        if playlist_id:
            # [Existing playlist logic]
            pass
        elif video_id:
            # [Existing video logic]
            pass
        else:
            # [Existing error handling]
            pass
    
    return jsonify({
        "mode": "sync",
        "results": results
    })

def estimate_processing_time(urls: List[str], model: str) -> int:
    """Estimate processing time in seconds."""
    base_time_per_url = 30  # seconds
    
    # Adjust for model complexity
    if model in ['gpt-5', 'gemini-2.5-pro']:
        base_time_per_url = 45
    elif model in ['gpt-4o-mini', 'gemini-2.5-flash']:
        base_time_per_url = 20
    
    # Check for playlists (rough estimate)
    total_estimated_items = 0
    for url in urls:
        if 'playlist' in url:
            total_estimated_items += 10  # Estimate 10 videos per playlist
        else:
            total_estimated_items += 1
    
    return total_estimated_items * base_time_per_url
```

#### 4.2 Enhanced Frontend with Automatic Mode Detection

```javascript
// Enhanced frontend with smart async/sync handling
class SmartSummarizer {
    constructor() {
        this.asyncEnabled = false;
        this.capabilities = null;
        this.activeJobs = new Map();
        
        this.detectCapabilities();
    }
    
    async detectCapabilities() {
        try {
            const response = await fetch('/api_status');
            const status = await response.json();
            
            this.capabilities = status;
            this.asyncEnabled = status.async_processing_enabled || false;
            
            console.log('Async processing:', this.asyncEnabled ? 'enabled' : 'disabled');
            
        } catch (error) {
            console.warn('Could not detect server capabilities:', error);
            this.asyncEnabled = false;
        }
    }
    
    async summarize(urls, model) {
        const processingMode = this.determineMode(urls, model);
        
        console.log(`Using ${processingMode} mode for ${urls.length} URLs`);
        
        if (processingMode === 'async') {
            return this.summarizeAsync(urls, model);
        } else {
            return this.summarizeSync(urls, model);
        }
    }
    
    determineMode(urls, model) {
        // Force sync for single URLs (faster response)
        if (urls.length === 1) {
            return 'sync';
        }
        
        // Use async for multiple URLs or heavy models
        if (urls.length > 1 || ['gpt-5', 'gemini-2.5-pro'].includes(model)) {
            return this.asyncEnabled ? 'async' : 'sync';
        }
        
        // Check user preference
        const userPreference = localStorage.getItem('processing_mode');
        if (userPreference === 'always_sync') {
            return 'sync';
        } else if (userPreference === 'always_async' && this.asyncEnabled) {
            return 'async';
        }
        
        // Default based on capabilities
        return this.asyncEnabled ? 'async' : 'sync';
    }
    
    async summarizeAsync(urls, model) {
        const response = await fetch('/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                urls: urls,
                model: model,
                force_async: true
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Async request failed');
        }
        
        const result = await response.json();
        
        if (result.mode === 'async') {
            return this.handleAsyncResponse(result);
        } else {
            // Server decided to process synchronously
            return this.handleSyncResponse(result);
        }
    }
    
    async summarizeSync(urls, model) {
        const response = await fetch('/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                urls: urls,
                model: model,
                force_sync: true
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Sync request failed');
        }
        
        const result = await response.json();
        return this.handleSyncResponse(result);
    }
    
    handleAsyncResponse(result) {
        const jobId = result.job_id;
        
        // Create progress display
        const progressContainer = this.createProgressDisplay(jobId, result);
        document.getElementById('new-results').appendChild(progressContainer);
        
        // Start tracking with enhanced job tracker
        const tracker = new EnhancedJobTracker(
            jobId,
            (jobData) => this.updateJobProgress(jobId, jobData),
            (jobData) => this.handleJobComplete(jobId, jobData),
            (error) => this.handleJobError(jobId, error)
        );
        
        this.activeJobs.set(jobId, {
            tracker: tracker,
            container: progressContainer
        });
        
        return {
            mode: 'async',
            jobId: jobId
        };
    }
    
    handleSyncResponse(result) {
        // Handle synchronous response (existing logic)
        const newResultsContainer = document.getElementById('new-results');
        displayResults(result.results, newResultsContainer, true);
        
        return {
            mode: 'sync',
            results: result.results
        };
    }
    
    createProgressDisplay(jobId, jobInfo) {
        const container = document.createElement('div');
        container.className = 'job-progress enhanced';
        container.id = `job-${jobId}`;
        
        const estimatedTime = jobInfo.estimated_time || 60;
        const formattedTime = this.formatTime(estimatedTime);
        
        container.innerHTML = `
            <div class="progress-header">
                <div class="job-info">
                    <h3>Processing ${jobInfo.total_items || 'unknown'} items</h3>
                    <span class="estimated-time">Est. ${formattedTime}</span>
                </div>
                <div class="job-actions">
                    <button class="cancel-btn" onclick="smartSummarizer.cancelJob('${jobId}')">Cancel</button>
                    <button class="minimize-btn" onclick="smartSummarizer.minimizeJob('${jobId}')">−</button>
                </div>
            </div>
            <div class="connection-status">Connecting...</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 0%"></div>
            </div>
            <div class="progress-details">
                <div class="progress-status">Initializing...</div>
                <div class="progress-stats">0 / ${jobInfo.total_items || 0}</div>
            </div>
            <div class="current-item"></div>
            <div class="job-log" style="display: none;">
                <div class="log-content"></div>
            </div>
        `;
        
        return container;
    }
    
    updateJobProgress(jobId, jobData) {
        const jobInfo = this.activeJobs.get(jobId);
        if (!jobInfo) return;
        
        const container = jobInfo.container;
        const progressFill = container.querySelector('.progress-fill');
        const statusEl = container.querySelector('.progress-status');
        const statsEl = container.querySelector('.progress-stats');
        const currentItemEl = container.querySelector('.current-item');
        
        // Update progress bar with smooth animation
        const progressPercent = jobData.total_items > 0 
            ? Math.min((jobData.progress / jobData.total_items) * 100, 100)
            : 0;
        
        progressFill.style.width = `${progressPercent}%`;
        
        // Update status and stats
        statusEl.textContent = this.getStatusMessage(jobData.status);
        statsEl.textContent = `${jobData.progress} / ${jobData.total_items}`;
        
        // Update current item
        if (jobData.current_item) {
            currentItemEl.textContent = `Processing: ${this.truncateUrl(jobData.current_item)}`;
        }
        
        // Add to log
        this.addToJobLog(jobId, jobData);
    }
    
    handleJobComplete(jobId, jobData) {
        const jobInfo = this.activeJobs.get(jobId);
        if (!jobInfo) return;
        
        const container = jobInfo.container;
        
        // Clean up tracker
        jobInfo.tracker.stop();
        
        if (jobData.status === 'completed' && jobData.results) {
            // Display results
            const newResultsContainer = document.getElementById('new-results');
            displayResults(jobData.results, newResultsContainer, true);
            
            // Show completion message briefly, then remove
            this.showCompletionMessage(container, jobData.results.length);
            
            setTimeout(() => {
                if (container.parentNode) {
                    container.remove();
                }
            }, 3000);
            
            // Refresh pagination
            loadPaginatedSummaries(currentPage, currentPageSize);
            
        } else if (jobData.status === 'failed') {
            container.classList.add('error');
            container.querySelector('.progress-status').textContent = `Failed: ${jobData.error}`;
        } else if (jobData.status === 'cancelled') {
            container.classList.add('cancelled');
            container.querySelector('.progress-status').textContent = 'Cancelled by user';
        }
        
        // Clean up
        this.activeJobs.delete(jobId);
        
        // Re-enable summarize button if no active jobs
        if (this.activeJobs.size === 0) {
            summarizeBtn.disabled = false;
            summarizeBtn.textContent = 'Summarize Links';
            loader.style.display = 'none';
        }
    }
    
    handleJobError(jobId, error) {
        const jobInfo = this.activeJobs.get(jobId);
        if (!jobInfo) return;
        
        const container = jobInfo.container;
        container.classList.add('error');
        container.querySelector('.progress-status').textContent = `Error: ${error}`;
        
        // Clean up
        jobInfo.tracker.stop();
        this.activeJobs.delete(jobId);
    }
    
    async cancelJob(jobId) {
        try {
            await fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
            
            const jobInfo = this.activeJobs.get(jobId);
            if (jobInfo) {
                jobInfo.tracker.stop();
                this.activeJobs.delete(jobId);
            }
            
        } catch (error) {
            console.error('Failed to cancel job:', error);
        }
    }
    
    minimizeJob(jobId) {
        const container = document.getElementById(`job-${jobId}`);
        if (container) {
            container.classList.toggle('minimized');
        }
    }
    
    getStatusMessage(status) {
        const messages = {
            pending: 'Waiting to start...',
            running: 'Processing...',
            completed: 'Completed!',
            failed: 'Failed',
            cancelled: 'Cancelled'
        };
        return messages[status] || status;
    }
    
    truncateUrl(url, maxLength = 50) {
        if (url.length <= maxLength) return url;
        return url.substring(0, maxLength - 3) + '...';
    }
    
    formatTime(seconds) {
        if (seconds < 60) return `${seconds}s`;
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}m ${remainingSeconds}s`;
    }
    
    showCompletionMessage(container, resultCount) {
        const message = document.createElement('div');
        message.className = 'completion-message';
        message.textContent = `✓ Completed! Processed ${resultCount} items.`;
        container.appendChild(message);
    }
    
    addToJobLog(jobId, jobData) {
        const container = document.getElementById(`job-${jobId}`);
        if (!container) return;
        
        const logContent = container.querySelector('.log-content');
        if (logContent) {
            const timestamp = new Date().toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.className = 'log-entry';
            logEntry.innerHTML = `
                <span class="log-time">${timestamp}</span>
                <span class="log-message">${this.getLogMessage(jobData)}</span>
            `;
            logContent.appendChild(logEntry);
            logContent.scrollTop = logContent.scrollHeight;
        }
    }
    
    getLogMessage(jobData) {
        if (jobData.current_item) {
            return `Processing: ${this.truncateUrl(jobData.current_item)}`;
        } else if (jobData.status === 'running') {
            return `Progress: ${jobData.progress}/${jobData.total_items}`;
        } else {
            return `Status: ${jobData.status}`;
        }
    }
}

// Initialize the smart summarizer
const smartSummarizer = new SmartSummarizer();

// Update the main event listener
summarizeBtn.addEventListener('click', async () => {
    if (currentAudioPlayer.state !== 'stopped') {
        player.pause();
        resetAudioPlayerUI();
    }
    
    const urls = linksTextarea.value.split('\n').filter(url => url.trim() !== '');
    if (urls.length === 0) {
        alert('Please paste at least one YouTube link.');
        return;
    }
    
    summarizeBtn.disabled = true;
    summarizeBtn.textContent = 'Processing...';
    loader.style.display = 'block';
    
    try {
        const selectedModel = document.getElementById('model-select').value;
        
        const result = await smartSummarizer.summarize(urls, selectedModel);
        
        if (result.mode === 'sync') {
            // Synchronous result - re-enable button immediately
            summarizeBtn.disabled = false;
            summarizeBtn.textContent = 'Summarize Links';
            loader.style.display = 'none';
            linksTextarea.value = '';
        }
        // For async mode, button will be re-enabled when job completes
        
    } catch (error) {
        console.error('Error during summarization:', error);
        alert(`An Error Occurred: ${error.message}`);
        
        summarizeBtn.disabled = false;
        summarizeBtn.textContent = 'Summarize Links';
        loader.style.display = 'none';
    }
});
```

#### 4.3 Enhanced CSS for Full Async Experience

```css
/* Add enhanced styles for Phase 4 */
.job-progress.enhanced {
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border: 1px solid #dee2e6;
    border-radius: 12px;
    padding: 24px;
    margin: 20px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    transition: all 0.3s ease;
}

.job-progress.enhanced:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.job-progress.enhanced.minimized {
    padding: 12px 24px;
}

.job-progress.enhanced.minimized .progress-details,
.job-progress.enhanced.minimized .current-item,
.job-progress.enhanced.minimized .job-log {
    display: none;
}

.progress-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 16px;
}

.job-info h3 {
    margin: 0 0 4px 0;
    color: #343a40;
    font-size: 18px;
}

.estimated-time {
    color: #6c757d;
    font-size: 14px;
    font-weight: 500;
}

.job-actions {
    display: flex;
    gap: 8px;
}

.cancel-btn, .minimize-btn {
    background-color: #6c757d;
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    transition: background-color 0.2s;
}

.cancel-btn:hover {
    background-color: #dc3545;
}

.minimize-btn:hover {
    background-color: #495057;
}

.connection-status {
    font-size: 12px;
    color: #6c757d;
    margin-bottom: 12px;
    padding: 4px 8px;
    background-color: #f8f9fa;
    border-radius: 4px;
    display: inline-block;
}

.connection-status.sse {
    background-color: #d4edda;
    color: #155724;
}

.connection-status.sse::before {
    content: "⚡ ";
}

.connection-status.polling {
    background-color: #d1ecf1;
    color: #0c5460;
}

.connection-status.polling::before {
    content: "🔄 ";
}

.progress-bar {
    width: 100%;
    height: 24px;
    background-color: #e9ecef;
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 16px;
    position: relative;
}

.progress-bar .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #8e44ad 0%, #9b59b6 100%);
    transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
}

.progress-bar .progress-fill::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(90deg, 
        transparent 0%, 
        rgba(255,255,255,0.3) 50%, 
        transparent 100%);
    animation: shimmer 2s infinite;
}

@keyframes shimmer {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
}

.progress-details {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.progress-status {
    font-weight: 600;
    color: #495057;
    font-size: 16px;
}

.progress-stats {
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 14px;
    color: #6c757d;
    background-color: #f8f9fa;
    padding: 4px 8px;
    border-radius: 4px;
}

.current-item {
    font-size: 14px;
    color: #6c757d;
    background-color: #f8f9fa;
    padding: 8px 12px;
    border-radius: 6px;
    word-break: break-all;
    font-family: 'Monaco', 'Menlo', monospace;
}

.completion-message {
    background-color: #d4edda;
    color: #155724;
    padding: 12px;
    border-radius: 6px;
    text-align: center;
    font-weight: 600;
    margin-top: 16px;
    animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.job-progress.error {
    border-color: #dc3545;
    background: linear-gradient(135deg, #f8d7da 0%, #f1b0b7 100%);
}

.job-progress.cancelled {
    border-color: #ffc107;
    background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
}

.job-log {
    margin-top: 16px;
    padding: 12px;
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    max-height: 200px;
    overflow-y: auto;
}

.log-entry {
    display: flex;
    gap: 8px;
    margin-bottom: 4px;
    font-size: 12px;
    font-family: 'Monaco', 'Menlo', monospace;
}

.log-time {
    color: #6c757d;
    flex-shrink: 0;
}

.log-message {
    color: #495057;
}

/* Processing mode toggle */
.processing-mode-toggle {
    margin: 16px 0;
    padding: 12px;
    background-color: #f8f9fa;
    border-radius: 8px;
    border: 1px solid #dee2e6;
}

.processing-mode-toggle label {
    display: block;
    margin: 6px 0;
    cursor: pointer;
}

.processing-mode-toggle input[type="radio"] {
    margin-right: 8px;
}

.processing-mode-toggle small {
    color: #6c757d;
    font-size: 12px;
    display: block;
    margin-top: 8px;
}
```

#### 4.4 Performance Monitoring and Optimization

```python
# Add performance monitoring to app.py
import psutil
import threading
from collections import defaultdict
from datetime import datetime, timedelta

class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'sync_requests': 0,
            'async_requests': 0,
            'avg_sync_time': 0,
            'avg_async_time': 0,
            'active_jobs': 0,
            'completed_jobs': 0,
            'failed_jobs': 0,
            'resource_usage': {}
        }
        self.request_times = defaultdict(list)
        self.start_monitoring()
    
    def start_monitoring(self):
        def monitor_resources():
            while True:
                try:
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory_info = psutil.virtual_memory()
                    
                    self.metrics['resource_usage'] = {
                        'cpu_percent': cpu_percent,
                        'memory_percent': memory_info.percent,
                        'memory_used_mb': memory_info.used / 1024 / 1024,
                        'memory_available_mb': memory_info.available / 1024 / 1024
                    }
                    
                except Exception as e:
                    print(f"Resource monitoring error: {e}")
                
                time.sleep(30)  # Update every 30 seconds
        
        monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
        monitor_thread.start()
    
    def record_request(self, request_type: str, duration: float):
        self.metrics[f'{request_type}_requests'] += 1
        self.request_times[request_type].append(duration)
        
        # Keep only last 100 requests for averaging
        if len(self.request_times[request_type]) > 100:
            self.request_times[request_type] = self.request_times[request_type][-100:]
        
        # Update average
        if self.request_times[request_type]:
            self.metrics[f'avg_{request_type}_time'] = sum(self.request_times[request_type]) / len(self.request_times[request_type])
    
    def get_metrics(self):
        return {
            **self.metrics,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

# Initialize performance monitor
perf_monitor = PerformanceMonitor()

# Add performance monitoring to endpoints
@app.route("/performance_metrics")
@require_auth
def get_performance_metrics():
    """Get performance metrics for monitoring."""
    return jsonify(perf_monitor.get_metrics())

# Update request handlers to include timing
def time_request(request_type):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                perf_monitor.record_request(request_type, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                perf_monitor.record_request(request_type, duration)
                raise
        return wrapper
    return decorator

# Apply timing decorators
handle_sync_request = time_request('sync')(handle_sync_request)
handle_async_request = time_request('async')(handle_async_request)
```

### Testing Strategy for Phase 4

#### 4.5.1 Mode Selection Tests
```bash
# Test automatic mode selection
# Test forced sync/async modes
# Test user preference handling
# Test performance under load
```

#### 4.5.2 Comprehensive Integration Tests
```bash
# Test all endpoints together
# Test migration from old to new system
# Test backward compatibility
# Test error scenarios
```

#### 4.5.3 Performance Tests
```bash
# Load testing with mixed sync/async requests
# Resource usage monitoring  
# Response time comparisons
# Concurrency testing
```

### Rollback Procedure Phase 4
- **Immediate**: Disable async processing via `ASYNC_PROCESSING_ENABLED=false`
- **Quick**: Force all requests to synchronous mode
- **Full**: Revert to Phase 3 or earlier implementation
- **Monitor**: Track performance metrics and user feedback

---

## Comprehensive Testing Strategy

### Testing Framework

#### Test Categories
1. **Unit Tests**: Individual components (jobs, workers, SSE)
2. **Integration Tests**: End-to-end workflows
3. **Performance Tests**: Load testing and benchmarks
4. **Compatibility Tests**: Browser/client compatibility
5. **Regression Tests**: Ensure existing functionality works

#### Test Files Structure
```
tests/
├── test_jobs.py              # Job management tests
├── test_workers.py           # Worker pool tests  
├── test_sse.py              # Server-Sent Events tests
├── test_migration_phase1.py  # Phase 1 specific tests
├── test_migration_phase2.py  # Phase 2 specific tests
├── test_migration_phase3.py  # Phase 3 specific tests
├── test_migration_phase4.py  # Phase 4 specific tests
├── test_performance.py       # Performance benchmarks
├── test_compatibility.py     # Backward compatibility
└── test_integration_full.py  # Full system integration
```

#### Sample Test Implementation

```python
# tests/test_migration_phase1.py
import pytest
import json
import time
from app import app, job_manager, worker_pool
from jobs import JobStatus

class TestPhase1Migration:
    """Test Phase 1 - Worker thread infrastructure without breaking existing functionality."""
    
    def setup_method(self):
        self.client = app.test_client()
        app.config['TESTING'] = True
        
    def test_existing_synchronous_endpoint_unchanged(self):
        """Ensure existing /summarize endpoint works exactly as before."""
        response = self.client.post('/summarize', 
            json={
                'urls': ['https://www.youtube.com/watch?v=test'],
                'model': 'gemini-2.5-flash'
            })
        
        assert response.status_code in [200, 400]  # Should work or fail gracefully
        # Verify response structure matches original format
        
    def test_new_async_endpoint_available(self):
        """Test that new async endpoint is available and working."""
        response = self.client.post('/summarize_async',
            json={
                'urls': ['https://www.youtube.com/watch?v=test'],
                'model': 'gemini-2.5-flash'
            })
        
        assert response.status_code == 202
        data = response.get_json()
        assert 'job_id' in data
        assert data['status'] == 'accepted'
        
    def test_job_status_endpoint(self):
        """Test job status retrieval."""
        # Create a job first
        job_id = job_manager.create_job('test', {})
        
        response = self.client.get(f'/jobs/{job_id}')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['id'] == job_id
        assert 'status' in data
        
    def test_job_cancellation(self):
        """Test job cancellation functionality."""
        job_id = job_manager.create_job('test', {})
        
        response = self.client.post(f'/jobs/{job_id}/cancel')
        assert response.status_code == 200
        
        # Verify job is cancelled
        job = job_manager.get_job(job_id)
        assert job.status == JobStatus.CANCELLED
        
    def test_worker_pool_processing(self):
        """Test that worker pool processes jobs correctly."""
        job_id = job_manager.create_job('summarize', {})
        
        # Submit job to worker pool
        worker_pool.submit_job(job_id, 'summarize', {
            'urls': ['https://www.youtube.com/watch?v=test'],
            'model': 'gemini-2.5-flash'
        })
        
        # Wait for processing (with timeout)
        timeout = 30
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            job = job_manager.get_job(job_id)
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            time.sleep(0.5)
        
        # Verify job was processed
        job = job_manager.get_job(job_id)
        assert job.status in [JobStatus.COMPLETED, JobStatus.FAILED]
        
    def test_no_impact_on_existing_users(self):
        """Verify that existing user workflows are not impacted."""
        # Test all existing endpoints
        endpoints_to_test = [
            ('/get_cached_summaries', 'GET'),
            ('/search_summaries?q=test', 'GET'),
            ('/api_status', 'GET'),
            ('/login_status', 'GET')
        ]
        
        for endpoint, method in endpoints_to_test:
            if method == 'GET':
                response = self.client.get(endpoint)
            else:
                response = self.client.post(endpoint)
                
            # Should not return server errors
            assert response.status_code < 500
```

#### Performance Benchmarks

```python
# tests/test_performance.py
import pytest
import time
import concurrent.futures
from app import app

class TestPerformance:
    """Performance benchmarks for migration phases."""
    
    def test_sync_vs_async_performance(self):
        """Compare synchronous vs asynchronous performance."""
        client = app.test_client()
        
        # Test data
        test_urls = ['https://www.youtube.com/watch?v=test1']
        
        # Benchmark synchronous
        sync_times = []
        for _ in range(10):
            start = time.time()
            response = client.post('/summarize', json={
                'urls': test_urls,
                'model': 'gemini-2.5-flash',
                'force_sync': True
            })
            sync_times.append(time.time() - start)
        
        # Benchmark asynchronous
        async_times = []
        for _ in range(10):
            start = time.time()
            response = client.post('/summarize', json={
                'urls': test_urls,
                'model': 'gemini-2.5-flash', 
                'force_async': True
            })
            # For async, we measure job creation time, not processing time
            async_times.append(time.time() - start)
        
        avg_sync = sum(sync_times) / len(sync_times)
        avg_async = sum(async_times) / len(async_times)
        
        print(f"Average sync response time: {avg_sync:.3f}s")
        print(f"Average async job creation time: {avg_async:.3f}s")
        
        # Async job creation should be much faster
        assert avg_async < avg_sync / 2
        
    def test_concurrent_requests(self):
        """Test system behavior under concurrent load."""
        client = app.test_client()
        
        def make_request():
            return client.post('/summarize', json={
                'urls': ['https://www.youtube.com/watch?v=test'],
                'model': 'gemini-2.5-flash'
            })
        
        # Test 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should complete without server errors
        for response in results:
            assert response.status_code < 500
            
    def test_memory_usage_stability(self):
        """Test that memory usage remains stable during processing."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        client = app.test_client()
        
        # Make multiple requests
        for _ in range(20):
            response = client.post('/summarize_async', json={
                'urls': ['https://www.youtube.com/watch?v=test'],
                'model': 'gemini-2.5-flash'
            })
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"Memory usage: {initial_memory:.1f}MB -> {final_memory:.1f}MB")
        print(f"Memory increase: {memory_increase:.1f}MB")
        
        # Memory increase should be reasonable (less than 100MB for test)
        assert memory_increase < 100
```

### Automated Test Execution

```bash
# run_migration_tests.sh
#!/bin/bash

echo "🚀 Running YouTube Summarizer Migration Tests"

# Phase 1 Tests
echo "📋 Testing Phase 1: Worker Thread Infrastructure"
python -m pytest tests/test_migration_phase1.py -v
if [ $? -ne 0 ]; then
    echo "❌ Phase 1 tests failed"
    exit 1
fi

# Phase 2 Tests  
echo "📋 Testing Phase 2: SSE Implementation"
python -m pytest tests/test_migration_phase2.py -v
if [ $? -ne 0 ]; then
    echo "❌ Phase 2 tests failed"
    exit 1
fi

# Phase 3 Tests
echo "📋 Testing Phase 3: SSE with Fallback"
python -m pytest tests/test_migration_phase3.py -v
if [ $? -ne 0 ]; then
    echo "❌ Phase 3 tests failed"
    exit 1
fi

# Phase 4 Tests
echo "📋 Testing Phase 4: Full Async Mode"
python -m pytest tests/test_migration_phase4.py -v
if [ $? -ne 0 ]; then
    echo "❌ Phase 4 tests failed"
    exit 1
fi

# Performance Tests
echo "📋 Running Performance Benchmarks"
python -m pytest tests/test_performance.py -v -s

# Integration Tests
echo "📋 Running Full Integration Tests"
python -m pytest tests/test_integration_full.py -v

# Compatibility Tests
echo "📋 Running Backward Compatibility Tests"
python -m pytest tests/test_compatibility.py -v

echo "✅ All migration tests passed!"
```

---

## Rollback Procedures and Monitoring

### Monitoring Strategy

#### Key Metrics to Monitor
1. **Response Times**: Sync vs async response times
2. **Error Rates**: Failed requests, job failures
3. **Resource Usage**: CPU, memory, disk usage
4. **Connection Health**: SSE connection success rates
5. **User Experience**: Time to first result, completion rates

#### Monitoring Implementation

```python
# monitoring.py - New file
import time
import psutil
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List
import json

@dataclass
class MetricSnapshot:
    timestamp: datetime
    response_times: Dict[str, float]
    error_rates: Dict[str, float]
    resource_usage: Dict[str, float]
    active_connections: int
    job_queue_size: int

class SystemMonitor:
    def __init__(self):
        self.snapshots: List[MetricSnapshot] = []
        self.alerts = []
        self.thresholds = {
            'max_response_time': 30.0,  # seconds
            'max_error_rate': 0.05,     # 5%
            'max_cpu_usage': 80.0,      # 80%
            'max_memory_usage': 85.0,   # 85%
            'max_queue_size': 50        # jobs
        }
    
    def take_snapshot(self) -> MetricSnapshot:
        """Take a snapshot of current system metrics."""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            response_times=self.get_response_times(),
            error_rates=self.get_error_rates(),
            resource_usage=self.get_resource_usage(),
            active_connections=self.get_active_connections(),
            job_queue_size=self.get_job_queue_size()
        )
        
        self.snapshots.append(snapshot)
        
        # Keep only last 1000 snapshots
        if len(self.snapshots) > 1000:
            self.snapshots = self.snapshots[-1000:]
        
        # Check for alerts
        self.check_alerts(snapshot)
        
        return snapshot
    
    def check_alerts(self, snapshot: MetricSnapshot):
        """Check if any metrics exceed thresholds."""
        alerts = []
        
        # Check response times
        for endpoint, time in snapshot.response_times.items():
            if time > self.thresholds['max_response_time']:
                alerts.append(f"High response time on {endpoint}: {time:.2f}s")
        
        # Check error rates
        for endpoint, rate in snapshot.error_rates.items():
            if rate > self.thresholds['max_error_rate']:
                alerts.append(f"High error rate on {endpoint}: {rate:.1%}")
        
        # Check resource usage
        if snapshot.resource_usage['cpu'] > self.thresholds['max_cpu_usage']:
            alerts.append(f"High CPU usage: {snapshot.resource_usage['cpu']:.1f}%")
        
        if snapshot.resource_usage['memory'] > self.thresholds['max_memory_usage']:
            alerts.append(f"High memory usage: {snapshot.resource_usage['memory']:.1f}%")
        
        # Check queue size
        if snapshot.job_queue_size > self.thresholds['max_queue_size']:
            alerts.append(f"High job queue size: {snapshot.job_queue_size}")
        
        if alerts:
            self.alerts.extend(alerts)
            print("🚨 ALERTS:", alerts)
    
    def get_response_times(self) -> Dict[str, float]:
        """Get average response times for key endpoints."""
        # This would integrate with the performance monitor
        return perf_monitor.get_avg_response_times()
    
    def get_error_rates(self) -> Dict[str, float]:
        """Get error rates for key endpoints."""
        return perf_monitor.get_error_rates()
    
    def get_resource_usage(self) -> Dict[str, float]:
        """Get current resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_info = psutil.virtual_memory()
            
            return {
                'cpu': cpu_percent,
                'memory': memory_info.percent,
                'disk': psutil.disk_usage('/').percent
            }
        except Exception:
            return {'cpu': 0, 'memory': 0, 'disk': 0}
    
    def get_active_connections(self) -> int:
        """Get number of active SSE connections."""
        # This would track active SSE streams
        return len(active_sse_connections)
    
    def get_job_queue_size(self) -> int:
        """Get current job queue size."""
        return worker_pool.task_queue.qsize() if worker_pool else 0

# Initialize system monitor
system_monitor = SystemMonitor()

# Add monitoring endpoint
@app.route("/system_health")
@require_auth
def get_system_health():
    """Get current system health status."""
    snapshot = system_monitor.take_snapshot()
    
    return jsonify({
        'status': 'healthy' if not system_monitor.alerts else 'warning',
        'timestamp': snapshot.timestamp.isoformat(),
        'metrics': {
            'response_times': snapshot.response_times,
            'error_rates': snapshot.error_rates,
            'resource_usage': snapshot.resource_usage,
            'active_connections': snapshot.active_connections,
            'job_queue_size': snapshot.job_queue_size
        },
        'alerts': system_monitor.alerts[-10:],  # Last 10 alerts
        'migration_phase': determine_current_phase()
    })

def determine_current_phase() -> str:
    """Determine which migration phase is currently active."""
    if not ASYNC_PROCESSING_ENABLED:
        return "pre-migration"
    elif not hasattr(app, 'sse_enabled'):
        return "phase-1"
    elif not getattr(app, 'sse_default', False):
        return "phase-2"
    elif not getattr(app, 'adaptive_mode', False):
        return "phase-3"
    else:
        return "phase-4"
```

### Automated Rollback System

```python
# rollback.py - New file
import subprocess
import os
import shutil
from datetime import datetime
from typing import Dict, Any

class RollbackManager:
    def __init__(self):
        self.backup_dir = os.path.join(DATA_DIR, "backups")
        self.ensure_backup_dir()
        
    def ensure_backup_dir(self):
        """Ensure backup directory exists."""
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self, phase: str) -> str:
        """Create a backup before migration phase."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"pre_{phase}_{timestamp}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        os.makedirs(backup_path, exist_ok=True)
        
        # Backup key files
        files_to_backup = [
            "app.py",
            "templates/index.html",
            "requirements.txt",
            os.path.join(DATA_DIR, "summary_cache.json")
        ]
        
        for file_path in files_to_backup:
            if os.path.exists(file_path):
                dest_path = os.path.join(backup_path, os.path.basename(file_path))
                shutil.copy2(file_path, dest_path)
        
        print(f"✅ Backup created: {backup_path}")
        return backup_path
    
    def rollback_to_phase(self, target_phase: str) -> bool:
        """Rollback to a specific phase."""
        try:
            if target_phase == "pre-migration":
                return self.rollback_to_original()
            elif target_phase == "phase-1":
                return self.rollback_to_phase_1()
            elif target_phase == "phase-2":
                return self.rollback_to_phase_2()
            elif target_phase == "phase-3":
                return self.rollback_to_phase_3()
            else:
                print(f"❌ Unknown rollback target: {target_phase}")
                return False
                
        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            return False
    
    def rollback_to_original(self) -> bool:
        """Rollback to pre-migration state."""
        print("🔄 Rolling back to original synchronous system...")
        
        # Disable async processing
        os.environ["ASYNC_PROCESSING_ENABLED"] = "false"
        
        # Remove worker-related files
        files_to_remove = ["jobs.py", "workers.py", "monitoring.py"]
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
                
        print("✅ Rollback to original state completed")
        return True
    
    def rollback_to_phase_1(self) -> bool:
        """Rollback to Phase 1 (worker threads only)."""
        print("🔄 Rolling back to Phase 1 (workers only)...")
        
        # Keep workers but disable SSE
        if hasattr(app, 'sse_enabled'):
            delattr(app, 'sse_enabled')
        
        print("✅ Rollback to Phase 1 completed")
        return True
    
    def get_available_backups(self) -> List[str]:
        """Get list of available backups."""
        if not os.path.exists(self.backup_dir):
            return []
        
        backups = []
        for item in os.listdir(self.backup_dir):
            backup_path = os.path.join(self.backup_dir, item)
            if os.path.isdir(backup_path):
                backups.append(item)
        
        return sorted(backups, reverse=True)  # Most recent first

# Initialize rollback manager
rollback_manager = RollbackManager()

# Add rollback endpoints
@app.route("/admin/rollback/<phase>", methods=["POST"])
@require_auth  # Additional admin auth should be added
def trigger_rollback(phase: str):
    """Trigger rollback to specific phase."""
    success = rollback_manager.rollback_to_phase(phase)
    
    return jsonify({
        'success': success,
        'message': f"Rollback to {phase} {'completed' if success else 'failed'}",
        'timestamp': datetime.now().isoformat()
    })

@app.route("/admin/backups")
@require_auth
def list_backups():
    """List available backups."""
    backups = rollback_manager.get_available_backups()
    
    return jsonify({
        'backups': backups,
        'current_phase': determine_current_phase()
    })
```

### Health Check Script

```bash
#!/bin/bash
# health_check.sh - Automated health monitoring

echo "🔍 YouTube Summarizer Health Check"

# Check if server is responding
HEALTH_URL="http://localhost:5001/system_health"
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/health_response.json "$HEALTH_URL" || echo "000")

if [ "$RESPONSE" != "200" ]; then
    echo "❌ Server not responding (HTTP $RESPONSE)"
    echo "🚨 CRITICAL: Consider immediate rollback"
    exit 1
fi

# Parse health response
HEALTH_STATUS=$(cat /tmp/health_response.json | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('status', 'unknown'))")
ALERTS_COUNT=$(cat /tmp/health_response.json | python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data.get('alerts', [])))")

echo "📊 System Status: $HEALTH_STATUS"
echo "🚨 Active Alerts: $ALERTS_COUNT"

if [ "$HEALTH_STATUS" = "warning" ] && [ "$ALERTS_COUNT" -gt 5 ]; then
    echo "⚠️  Multiple alerts detected - consider rollback"
    
    # Auto-rollback if too many alerts
    if [ "$ALERTS_COUNT" -gt 10 ]; then
        echo "🚨 CRITICAL: Auto-triggering rollback due to excessive alerts"
        curl -X POST "http://localhost:5001/admin/rollback/phase-1"
    fi
fi

# Check key endpoints
ENDPOINTS=("/api_status" "/get_cached_summaries" "/login_status")

for endpoint in "${ENDPOINTS[@]}"; do
    STATUS=$(curl -s -w "%{http_code}" -o /dev/null "http://localhost:5001$endpoint")
    if [ "$STATUS" != "200" ]; then
        echo "❌ Endpoint $endpoint failed (HTTP $STATUS)"
    else
        echo "✅ Endpoint $endpoint OK"
    fi
done

# Check resource usage
CPU_USAGE=$(python3 -c "import psutil; print(psutil.cpu_percent(interval=1))")
MEMORY_USAGE=$(python3 -c "import psutil; print(psutil.virtual_memory().percent)")

echo "💾 CPU Usage: ${CPU_USAGE}%"
echo "🧠 Memory Usage: ${MEMORY_USAGE}%"

# Alert if resource usage is high
if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
    echo "⚠️  High CPU usage detected"
fi

if (( $(echo "$MEMORY_USAGE > 85" | bc -l) )); then
    echo "⚠️  High memory usage detected"
fi

echo "✅ Health check completed"
```

---

## Deployment and Configuration

### Environment Variables

```bash
# Migration configuration
ASYNC_PROCESSING_ENABLED=true|false
WORKER_POOL_SIZE=2
SSE_ENABLED=true|false
SSE_HEARTBEAT_INTERVAL=15
JOB_RETENTION_HOURS=72
MAX_CONCURRENT_JOBS=10

# Monitoring configuration  
MONITORING_ENABLED=true|false
HEALTH_CHECK_INTERVAL=30
ALERT_WEBHOOK_URL=""
BACKUP_RETENTION_DAYS=7

# Performance tuning
REQUEST_TIMEOUT=300
SSE_TIMEOUT=3600
POLL_INTERVAL=2000
HEARTBEAT_TIMEOUT=30
```

### Docker Configuration Updates

```dockerfile
# Dockerfile updates for worker threads
FROM python:3.11-slim

# ... existing setup ...

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5001/system_health || exit 1

# Environment defaults for production
ENV ASYNC_PROCESSING_ENABLED=true
ENV WORKER_POOL_SIZE=2
ENV SSE_ENABLED=true
ENV MONITORING_ENABLED=true

# ... rest of existing Dockerfile ...
```

### Nginx Configuration for SSE

```nginx
# nginx.conf updates for SSE support
server {
    listen 80;
    server_name your-domain.com;
    
    # Regular proxy settings
    location / {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Special handling for SSE endpoints
    location /jobs/ {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE specific settings
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        
        # Increase timeouts for long-running jobs
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 3600s;
    }
}
```

---

## Summary

This comprehensive migration plan provides a safe, phased approach to implementing worker threads and real-time notifications in the YouTube Summarizer application. Key benefits:

### Phase Benefits
- **Phase 1**: Foundation for async processing with zero risk to existing users
- **Phase 2**: Real-time updates with automatic fallback for compatibility
- **Phase 3**: Enhanced user experience with intelligent connection management
- **Phase 4**: Fully optimized async system with backward compatibility

### Safety Features
- ✅ **Zero Downtime**: Each phase maintains full backward compatibility
- ✅ **Automatic Fallbacks**: Graceful degradation when features fail
- ✅ **Comprehensive Testing**: Unit, integration, and performance tests
- ✅ **Monitoring & Alerts**: Proactive issue detection and resolution
- ✅ **Quick Rollback**: Multiple rollback strategies for each phase

### Technical Improvements
- ✅ **Better Performance**: Non-blocking request handling
- ✅ **Real-time Updates**: Instant progress feedback via SSE
- ✅ **Resource Efficiency**: Optimized server resource usage
- ✅ **Scalability**: Foundation for handling increased load
- ✅ **User Experience**: Responsive interface with progress tracking

The plan ensures that users can continue using the application normally throughout the entire migration process, while progressively gaining access to enhanced features as they become available.