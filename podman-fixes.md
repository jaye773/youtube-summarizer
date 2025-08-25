# Podman Compatibility Fixes for YouTube Summarizer

## Quick Fixes to Make It Work with Podman

### 1. Create a Podman-Compatible Docker Compose

Create `docker-compose-podman.yml`:

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
      - LOGIN_ENABLED=${LOGIN_ENABLED:-false}
    volumes:
      # Use :Z flag for SELinux contexts (important for Podman)
      - ./data:/app/data:Z
      - ./audio_cache:/app/audio_cache:Z
    # Remove user directive for rootless Podman
    # user: "1000:1000"  
    command: python app.py --host 0.0.0.0 --port 5001
    networks:
      - summarizer-net

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./docker/nginx-podman.conf:/etc/nginx/conf.d/default.conf:Z
    depends_on:
      - web
    networks:
      - summarizer-net

networks:
  summarizer-net:
    driver: bridge
```

### 2. Fix Nginx Configuration

Create `docker/nginx-podman.conf`:

```nginx
server {
    listen 80;
    server_name localhost;

    # SSE-specific settings
    proxy_buffering off;
    proxy_cache off;
    proxy_http_version 1.1;

    location / {
        # Use container name instead of localhost
        proxy_pass http://web:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /events {
        # Use container name for SSE endpoint
        proxy_pass http://web:5001/events;
        
        # SSE-specific headers
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }
}
```

### 3. Fix Flask App to Bind to All Interfaces

Update the Flask app startup in `app.py`:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5001, help='Port to bind to')
    args = parser.parse_args()
    
    app.run(debug=debug_mode, host=args.host, port=args.port)
```

### 4. Run with Podman

```bash
# Option 1: Using podman-compose
pip install podman-compose
podman-compose -f docker-compose-podman.yml up

# Option 2: Direct Podman with proper permissions
podman run -d \
  --name youtube-summarizer \
  --userns=keep-id \
  -p 5001:5001 \
  -v ./data:/app/data:Z \
  -v ./audio_cache:/app/audio_cache:Z \
  -e GOOGLE_API_KEY=$GOOGLE_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  youtube-summarizer

# Option 3: With explicit user mapping
podman run -d \
  --name youtube-summarizer \
  --user $(id -u):$(id -g) \
  -p 5001:5001 \
  -v ./data:/app/data:Z \
  -v ./audio_cache:/app/audio_cache:Z \
  -e GOOGLE_API_KEY=$GOOGLE_API_KEY \
  youtube-summarizer
```

### 5. SELinux Context (if on RHEL/Fedora)

```bash
# Set proper SELinux contexts for volumes
chcon -Rt svirt_sandbox_file_t ./data
chcon -Rt svirt_sandbox_file_t ./audio_cache

# Or use :Z flag in volume mounts (as shown above)
```

### 6. Add Missing Health Check Endpoint

Add to `app.py`:

```python
@app.route("/health")
def health_check():
    """Basic health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "worker_system": WORKER_SYSTEM_AVAILABLE,
        "sse_connections": len(sse_connections) if 'sse_connections' in globals() else 0
    })

@app.route("/sse/health")
def sse_health():
    """SSE system health check"""
    return jsonify({
        "status": "healthy",
        "sse_manager": sse_manager is not None if 'sse_manager' in globals() else False,
        "connections": len(sse_connections) if 'sse_connections' in globals() else 0
    })
```

## Common Podman Issues and Solutions

### Issue 1: Permission Denied Errors
**Solution**: Use `:Z` flag for SELinux or `--userns=keep-id` for user namespace mapping

### Issue 2: Container Can't Connect to Each Other
**Solution**: Use container names (not localhost) in configurations

### Issue 3: SSE Not Working
**Solution**: Ensure Flask binds to `0.0.0.0` not `127.0.0.1`

### Issue 4: Ports Already in Use
**Solution**: Check with `podman ps` and `podman port` commands

### Issue 5: Volume Mounts Not Working
**Solution**: Use absolute paths and proper SELinux contexts

## Testing Podman Setup

```bash
# Test basic connectivity
curl http://localhost:5001/health

# Test SSE endpoint
curl -N http://localhost:5001/events

# Check logs
podman logs youtube-summarizer

# Debug networking
podman exec youtube-summarizer ping nginx
```

## Environment Variables for Podman

Create `.env.podman`:

```bash
# API Keys
GOOGLE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# App Configuration
LOGIN_ENABLED=false
FLASK_ENV=production

# Podman-specific
PODMAN_USERNS=keep-id
```

Then run:
```bash
podman run --env-file .env.podman ...
```