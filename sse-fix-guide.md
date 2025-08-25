# SSE Endpoint Fix Guide

## Issue Identified
The SSE endpoint is hanging because:
1. **Endpoint mismatch**: App uses `/events` but tests/nginx look for `/sse`
2. **Gunicorn incompatibility**: Default sync workers don't support SSE long-lived connections
3. **Proxy buffering**: Nginx/reverse proxy may buffer SSE responses

## Root Cause Analysis

### The Critical Issue: Gunicorn Worker Type
**Gunicorn's default `sync` worker blocks on SSE connections**, causing the hanging behavior you observed. SSE requires:
- Long-lived connections
- Asynchronous handling
- Non-blocking I/O

### Endpoint Path Confusion
- **App defines**: `/events` (correct)
- **Tests expect**: `/sse` (incorrect)
- **Nginx routes**: `/sse` (incorrect)

## Complete Fix Implementation

### Step 1: Install Required Dependencies
```bash
pip install gevent gunicorn[gevent]
# OR
pip install eventlet gunicorn[eventlet]
```

### Step 2: Create Gunicorn Configuration
Create `gunicorn_config.py`:

```python
# Gunicorn configuration for SSE support
import multiprocessing

# Worker configuration
worker_class = 'gevent'  # or 'eventlet' - both support async
workers = multiprocessing.cpu_count() * 2 + 1
worker_connections = 1000

# Server mechanics
bind = '0.0.0.0:5001'
daemon = False
pidfile = None
errorlog = '-'
accesslog = '-'
loglevel = 'info'

# Timeouts - important for SSE
timeout = 86400  # 24 hours for long-lived SSE connections
keepalive = 2
graceful_timeout = 30

# Process naming
proc_name = 'youtube-summarizer'

# Server hooks
def when_ready(server):
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)
```

### Step 3: Update Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gevent gunicorn[gevent]

# Copy application
COPY . .

# Use Gunicorn with gevent workers
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
```

### Step 4: Fix Nginx Configuration
Create `nginx-sse-fixed.conf`:

```nginx
server {
    listen 80;
    server_name localhost;

    # Main application
    location / {
        proxy_pass http://web:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE endpoint - CORRECT PATH
    location /events {
        proxy_pass http://web:5001/events;
        
        # Critical SSE headers
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_set_header Cache-Control 'no-cache';
        proxy_set_header X-Accel-Buffering 'no';
        
        # Disable buffering - CRITICAL for SSE
        proxy_buffering off;
        proxy_cache off;
        
        # Long timeouts for SSE connections
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_connect_timeout 60s;
        
        # Real IP forwarding
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }

    # SSE status endpoint
    location /events/status {
        proxy_pass http://web:5001/events/status;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # SSE broadcast endpoint
    location /events/broadcast {
        proxy_pass http://web:5001/events/broadcast;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Step 5: Docker Compose for SSE
Create `docker-compose-sse-fixed.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "5001:5001"
    environment:
      - FLASK_ENV=production
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LOGIN_ENABLED=${LOGIN_ENABLED:-true}
      - LOGIN_USERNAME=${LOGIN_USERNAME}
      - LOGIN_PASSWORD_HASH=${LOGIN_PASSWORD_HASH}
    volumes:
      - ./data:/app/data:Z
      - ./audio_cache:/app/audio_cache:Z
    command: gunicorn -c gunicorn_config.py app:app
    networks:
      - youtube-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  nginx:
    image: nginx:alpine
    ports:
      - "8431:80"
    volumes:
      - ./nginx-sse-fixed.conf:/etc/nginx/conf.d/default.conf:Z
    depends_on:
      - web
    networks:
      - youtube-net

networks:
  youtube-net:
    driver: bridge
```

### Step 6: Podman-Specific Run Command
```bash
# For Podman with SSE support
podman run -d \
  --name youtube-summarizer \
  --userns=keep-id \
  -p 8431:5001 \
  -v ./data:/app/data:Z \
  -v ./audio_cache:/app/audio_cache:Z \
  -e GOOGLE_API_KEY=$GOOGLE_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e LOGIN_ENABLED=true \
  -e LOGIN_USERNAME=admin \
  -e LOGIN_PASSWORD_HASH=$PASSWORD_HASH \
  youtube-summarizer \
  gunicorn -c gunicorn_config.py app:app

# Or with podman-compose
podman-compose -f docker-compose-sse-fixed.yml up
```

### Step 7: Add Health Check Endpoint
Add to `app.py`:

```python
@app.route("/health")
def health_check():
    """Health check endpoint for container orchestration"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "worker_system": WORKER_SYSTEM_AVAILABLE,
        "sse_connections": len(sse_connections)
    })
```

## Testing the Fix

### Quick Test Script
```python
#!/usr/bin/env python3
import requests
import time

base_url = "http://192.168.50.56:8431"

# Test 1: Check if server responds
print("Testing basic connectivity...")
response = requests.get(base_url, timeout=5)
print(f"Status: {response.status_code}")

# Test 2: Test SSE endpoint
print("\nTesting SSE endpoint...")
response = requests.get(f"{base_url}/events", stream=True, timeout=2)
print(f"SSE Status: {response.status_code}")
print(f"Headers: {response.headers.get('Content-Type')}")

# Read first few lines
for i, line in enumerate(response.iter_lines()):
    if i > 5:
        break
    print(f"SSE Line {i}: {line}")
```

## Verification Checklist

- [ ] Gunicorn running with gevent/eventlet workers
- [ ] Nginx routing to `/events` not `/sse`
- [ ] Proxy buffering disabled
- [ ] Long timeout values set
- [ ] Health endpoint working
- [ ] SSE connections don't hang
- [ ] Can receive real-time events

## Common Issues and Solutions

### Issue: Still hanging after fix
**Solution**: Check if firewall/SELinux blocking long connections
```bash
# For SELinux
semanage port -a -t http_port_t -p tcp 8431
setsebool -P httpd_can_network_connect 1
```

### Issue: Connection drops after 60 seconds
**Solution**: Increase proxy timeouts in nginx and Gunicorn

### Issue: No events received
**Solution**: Check if worker system is initialized properly

### Issue: "Connection refused" errors
**Solution**: Ensure Gunicorn binds to 0.0.0.0 not 127.0.0.1

## Alternative: Use Flask Development Server (Testing Only)
If you need a quick test without Gunicorn:
```bash
# Development mode with threading
python app.py --host 0.0.0.0 --port 8431
```

Note: Flask dev server supports SSE but isn't production-ready.

## Summary
The main fix is switching from Gunicorn sync workers to async workers (gevent/eventlet) and ensuring the correct endpoint path (`/events`) is used throughout the configuration.