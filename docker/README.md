# Docker Configuration for SSE Support

This directory contains Docker configuration files optimized for Server-Sent Events (SSE) support in the YouTube Summarizer application.

## Files

### nginx-sse.conf
Nginx configuration with SSE-specific optimizations:
- Disabled buffering for SSE endpoints
- Long timeout values for persistent connections
- Keep-alive settings for connection stability
- Proper header forwarding for real IP detection

### supervisord.conf
Supervisor configuration to manage multiple processes:
- Nginx reverse proxy
- Gunicorn application server
- Coordinated startup and shutdown
- Log rotation and management

### gunicorn_config.py
Gunicorn configuration optimized for SSE:
- Eventlet worker class for async support
- Single worker (or sticky sessions required for multiple)
- Extended timeouts for long-lived connections
- Keep-alive settings for SSE connections

## Usage

### Development
```bash
# Use the standard docker-compose for development
docker-compose up
```

### Production with SSE
```bash
# Use the SSE-optimized configuration
docker-compose -f docker-compose-sse.yml up
```

## Key SSE Considerations

### 1. Single Worker vs Multiple Workers
SSE connections are stateful and tied to specific server processes. Options:
- **Single Worker** (default): Simple, works out of the box
- **Multiple Workers**: Requires sticky sessions at load balancer level

### 2. Buffering
All buffering must be disabled for SSE to work properly:
- Nginx: `proxy_buffering off`
- Nginx: `X-Accel-Buffering: no`
- Gunicorn: Uses eventlet worker class

### 3. Timeouts
Long-lived connections require extended timeouts:
- Nginx: `proxy_read_timeout 86400s` (24 hours)
- Gunicorn: `timeout 300` (5 minutes between heartbeats)
- Keep-alive: `keepalive 75` seconds

### 4. Connection Limits
Enhanced SSE supports more connections:
- Default: 100 connections
- Enhanced: 500 connections
- Per-IP limit: 10 connections

### 5. Heartbeat Mechanism
Prevents connection drops:
- Server sends heartbeat every 30 seconds
- Client monitors heartbeat with 45-second timeout
- Automatic reconnection on heartbeat failure

## Monitoring

### Health Check
```bash
# Check SSE health endpoint
curl http://localhost:5001/sse/health
```

### Logs
- Nginx access: `/app/logs/nginx.access.log`
- Nginx error: `/app/logs/nginx.error.log`
- Gunicorn access: `/app/logs/gunicorn.access.log`
- Gunicorn error: `/app/logs/gunicorn.error.log`
- Supervisor: `/app/logs/supervisord.log`

### Metrics
The `/sse/health` endpoint provides:
- Active connections count
- Connection pool utilization
- Heartbeat statistics
- Compression metrics
- System resource usage

## Troubleshooting

### SSE Not Working
1. Check nginx buffering is disabled
2. Verify eventlet is installed
3. Ensure single worker or sticky sessions
4. Check firewall allows long connections

### Connection Drops
1. Increase timeout values
2. Check heartbeat is working
3. Verify network stability
4. Monitor resource usage

### High Resource Usage
1. Check connection pool limits
2. Monitor compression efficiency
3. Review heartbeat interval
4. Consider scaling options

## Performance Tuning

### Memory Usage
- Each connection: ~2KB base
- With compression: ~3KB average
- 500 connections: ~1.5MB total

### CPU Usage
- Heartbeat processing: <1% per 100 connections
- Compression: ~2% for active traffic
- Event routing: <1% overhead

### Network
- Heartbeat: 100 bytes every 30 seconds
- Compressed events: 20-60% bandwidth savings
- Keep-alive: Reduces connection overhead

## Security

### Connection Limits
- Per-IP limit prevents abuse
- Total connection limit prevents DoS
- Rate limiting on event sending

### Authentication
- Optional login system
- Session-based authentication
- IP-based lockout on failures

### Headers
- Real IP forwarding for logging
- CORS headers for cross-origin
- Security headers in responses