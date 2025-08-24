# Docker Setup for Enhanced SSE Support

This guide explains the Docker configuration changes needed to properly support Server-Sent Events (SSE) in the YouTube Summarizer application.

## Quick Start

### Using Standard Docker Compose (Basic SSE)
```bash
# For basic SSE support (existing setup)
docker-compose up
```

### Using Enhanced SSE Docker Compose
```bash
# For enhanced SSE with all optimizations
docker-compose -f docker-compose-sse.yml up
```

## Key Docker Changes for SSE

### 1. Worker Configuration
**Critical for SSE**: SSE requires either a single worker or sticky sessions.

```yaml
# In docker-compose-sse.yml
environment:
  - GUNICORN_WORKERS=1  # Single worker for SSE
  - GUNICORN_WORKER_CLASS=eventlet  # Async worker class
```

**Why this matters**: 
- SSE connections are stateful and tied to specific processes
- Multiple workers would cause connections to be lost when routed to different workers
- Eventlet enables async handling of multiple connections in a single worker

### 2. Nginx Configuration
**Required**: Disable all buffering for SSE endpoints.

```nginx
# In docker/nginx-sse.conf
location /sse {
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header X-Accel-Buffering 'no';
    proxy_read_timeout 86400s;  # 24 hours
    proxy_http_version 1.1;
    proxy_set_header Connection '';
}
```

**Why this matters**:
- Buffering would delay or break real-time event delivery
- Long timeouts prevent connection drops
- HTTP/1.1 required for chunked transfer encoding

### 3. Timeout Settings
**Important**: Extended timeouts for long-lived connections.

```yaml
# Gunicorn settings
GUNICORN_TIMEOUT=300  # 5 minutes
GUNICORN_KEEPALIVE=75  # 75 seconds

# Nginx settings  
proxy_read_timeout 86400s;  # 24 hours
proxy_send_timeout 86400s;  # 24 hours
```

**Why this matters**:
- SSE connections can last hours or days
- Heartbeats every 30 seconds keep connections alive
- Timeouts must be longer than heartbeat intervals

### 4. Resource Limits
**Recommended**: Appropriate resource allocation.

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

**Why this matters**:
- Each SSE connection uses ~2-3KB memory
- 500 connections = ~1.5MB for connections alone
- CPU needed for heartbeats and compression

## Building and Running

### Build the Enhanced SSE Image
```bash
# Build with SSE optimizations
docker build -f Dockerfile.sse -t youtube-summarizer:sse .
```

### Run with Docker Compose
```bash
# Start with enhanced SSE support
docker-compose -f docker-compose-sse.yml up -d

# View logs
docker-compose -f docker-compose-sse.yml logs -f

# Stop
docker-compose -f docker-compose-sse.yml down
```

### Environment Variables
```bash
# Create .env file with required variables
cat > .env << EOF
GOOGLE_API_KEY=your_google_api_key
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
SSE_MAX_CONNECTIONS=500
SSE_HEARTBEAT_INTERVAL=30
EOF
```

## Monitoring SSE in Docker

### Health Check
```bash
# Check SSE health from host
curl http://localhost:5001/sse/health

# Check from inside container
docker exec youtube-summarizer-sse curl http://localhost:5001/sse/health
```

### View Logs
```bash
# Application logs
docker exec youtube-summarizer-sse tail -f /app/logs/gunicorn.error.log

# Nginx logs
docker exec youtube-summarizer-sse tail -f /app/logs/nginx.error.log

# SSE-specific logs
docker logs youtube-summarizer-sse 2>&1 | grep SSE
```

### Connection Monitoring
```bash
# Count active SSE connections
docker exec youtube-summarizer-sse netstat -an | grep :5001 | grep ESTABLISHED | wc -l

# Monitor in real-time
watch -n 1 'docker exec youtube-summarizer-sse netstat -an | grep :5001 | grep ESTABLISHED | wc -l'
```

## Troubleshooting

### SSE Connections Not Working

1. **Check worker configuration**:
```bash
docker exec youtube-summarizer-sse ps aux | grep gunicorn
# Should show only 1 worker process
```

2. **Verify nginx configuration**:
```bash
docker exec youtube-summarizer-sse nginx -t
# Should show "syntax is ok"
```

3. **Test SSE endpoint directly**:
```bash
curl -N http://localhost:5001/sse
# Should show event stream
```

### Connection Drops

1. **Check heartbeats**:
```bash
docker logs youtube-summarizer-sse 2>&1 | grep heartbeat
# Should show heartbeats every 30 seconds
```

2. **Increase timeouts** in docker-compose-sse.yml:
```yaml
environment:
  - GUNICORN_TIMEOUT=600  # Increase to 10 minutes
  - SSE_HEARTBEAT_INTERVAL=15  # More frequent heartbeats
```

### High Memory Usage

1. **Check connection count**:
```bash
curl http://localhost:5001/sse/health | jq '.connections.active'
```

2. **Reduce limits** if needed:
```yaml
environment:
  - SSE_MAX_CONNECTIONS=200  # Reduce from 500
  - SSE_MAX_CONNECTIONS_PER_IP=5  # Reduce from 10
```

## Performance Tuning

### For Low-Resource Environments
```yaml
# Minimal configuration
environment:
  - SSE_MAX_CONNECTIONS=100
  - SSE_COMPRESSION_THRESHOLD=2048  # Less compression
  - GUNICORN_WORKER_CONNECTIONS=200
  
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1G
```

### For High-Traffic Environments
```yaml
# Maximum performance (requires sticky sessions)
environment:
  - GUNICORN_WORKERS=4  # Multiple workers
  - SSE_MAX_CONNECTIONS=2000
  - GUNICORN_WORKER_CONNECTIONS=500
  
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 4G
```

**Note**: Multiple workers require sticky session configuration at load balancer level.

## Docker Swarm Deployment

For production Docker Swarm deployment:

```yaml
# docker-stack-sse.yml
version: '3.8'

services:
  summarizer-app:
    image: youtube-summarizer:sse
    deploy:
      replicas: 1  # Single replica for SSE
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      placement:
        constraints:
          - node.role == worker
    # ... rest of configuration
```

Deploy:
```bash
docker stack deploy -c docker-stack-sse.yml youtube-summarizer
```

## Kubernetes Considerations

If deploying to Kubernetes:

1. **Use StatefulSet** for SSE pods (not Deployment)
2. **Configure session affinity**:
```yaml
service:
  sessionAffinity: ClientIP
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 86400
```

3. **Set appropriate resource limits**:
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

## Security Considerations

### Network Security
- SSE connections are long-lived and may bypass some security tools
- Ensure firewall rules allow persistent connections
- Monitor for connection abuse

### Resource Protection
- Connection limits prevent DoS attacks
- IP-based limits prevent single-source abuse
- Heartbeat mechanism detects stale connections

### Headers and CORS
```nginx
# Ensure proper CORS headers for SSE
add_header 'Access-Control-Allow-Origin' '*';
add_header 'Access-Control-Allow-Credentials' 'true';
add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS';
```

## Conclusion

The Docker configuration for SSE requires careful attention to:
1. Worker configuration (single worker or sticky sessions)
2. Buffering disabled at all levels
3. Extended timeouts for long connections
4. Appropriate resource allocation
5. Monitoring and health checks

Use `docker-compose-sse.yml` for production deployments with full SSE optimization.