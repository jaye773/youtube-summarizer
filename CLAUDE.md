# YouTube Summarizer - Claude Code Documentation

## Project Overview

YouTube Summarizer is a Flask-based web application that uses AI models to generate summaries of YouTube videos and playlists. The application features an async worker system for background processing, real-time updates via Server-Sent Events (SSE), and support for multiple AI models.

## Architecture

### Core Components

1. **Flask Web Application** (`app.py`)
   - Main application server
   - Handles HTTP requests and routing
   - Manages user sessions and authentication
   - Integrates with AI models and YouTube API

2. **Async Worker System**
   - **WorkerManager** (`worker_manager.py`): Coordinates multiple worker threads
   - **JobQueue** (`job_queue.py`): Priority-based job scheduling with rate limiting
   - **JobModels** (`job_models.py`): Data structures for async processing
   - **JobState** (`job_state.py`): Persistent state management
   - **ErrorHandler** (`error_handler.py`): Intelligent error classification and retry logic

3. **Real-time Updates**
   - **SSEManager** (`sse_manager.py`): Server-Sent Events for real-time notifications
   - **Client-side JavaScript**: SSE client, job tracker, and UI updater

4. **Voice Configuration** (`voice_config.py`)
   - Text-to-speech voice management
   - Multi-tier voice system with fallbacks
   - Cache optimization for audio files

## Key Features

### AI Model Support
- **OpenAI**: GPT-4o, GPT-4o-mini, GPT-3.5-turbo
- **Google Gemini**: Gemini 2.0 Flash, Gemini 1.5 Pro/Flash
- **Anthropic Claude**: Claude 3.5 Sonnet, Claude 3 Haiku

### Processing Capabilities
- Single video summarization
- Playlist processing (with 1-second delay between videos)
- Batch URL processing
- Background async processing with progress tracking
- Fallback to synchronous processing if worker system unavailable

### Error Handling
- Timeout protection (30-second timeout for YouTube API calls)
- Retry logic with exponential backoff (up to 3 retries)
- Intelligent error classification (9 categories)
- Graceful degradation on failures

## Important Implementation Details

### Worker System
- **3 worker threads** by default
- **Priority levels**: HIGH, MEDIUM, LOW
- **Rate limiting**: 60 requests per minute per IP
- **State persistence**: JSON-based job state storage
- **Automatic cleanup**: Jobs older than 24 hours are removed

### API Timeout Handling
```python
# YouTube API client with 30-second timeout
def create_youtube_client_with_timeout(api_key, timeout=30):
    http = httplib2.Http(timeout=timeout)
    socket.setdefaulttimeout(timeout)
    return build("youtube", "v3", developerKey=api_key, http=http)
```

### Rate Limiting Protection
- 1-second delay between processing videos in playlists
- 1-second delay between URLs in batch processing
- Prevents YouTube API rate limiting

### SSE Connection Management
- Maximum 100 concurrent connections
- Automatic cleanup of stale connections (5-minute timeout)
- Connection status indicator in UI
- Exponential backoff for reconnection (1s, 2s, 4s, 8s, 16s, max 30s)

## File Structure

```
youtube-summarizer/
├── app.py                    # Main Flask application
├── worker_manager.py         # Async worker coordination
├── job_queue.py             # Priority job scheduling
├── job_models.py            # Job data structures
├── job_state.py             # State persistence
├── error_handler.py         # Error handling logic
├── sse_manager.py           # SSE implementation
├── voice_config.py          # TTS configuration
├── static/
│   ├── js/
│   │   ├── sse_client.js   # SSE client
│   │   ├── job_tracker.js  # Job lifecycle management
│   │   └── ui_updater.js   # Dynamic UI updates
│   └── css/
│       └── async_ui.css    # Async UI styling
├── templates/
│   └── index.html           # Main UI template
├── tests/                   # Comprehensive test suite
├── data/                    # Data storage directory
└── audio_cache/            # TTS audio cache
```

## Testing

### Test Coverage
- **400+ test cases** across 22 test files
- **Unit tests**: Job models, queue, state management
- **Integration tests**: End-to-end workflows, API endpoints
- **Performance tests**: Load testing, memory usage
- **JavaScript tests**: Client-side functionality

### Running Tests
```bash
# Quick essential tests
make quick-test

# All async worker tests
make test-worker

# Complete test suite with coverage
make coverage

# Specific test categories
make test-models      # Job models
make test-state       # State management
make test-sse         # SSE implementation
make test-integration # Integration tests
```

## Environment Variables

### Required
- `GOOGLE_API_KEY`: YouTube API and Gemini models
- `OPENAI_API_KEY`: OpenAI GPT models
- `ANTHROPIC_API_KEY`: Claude models

### Optional
- `LOGIN_ENABLED`: Enable authentication (default: false)
- `LOGIN_USERNAME`: Admin username
- `LOGIN_PASSWORD_HASH`: Hashed admin password
- `TESTING`: Enable test mode
- `WEBSHARE_PROXY_*`: Proxy configuration

## Common Operations

### Starting the Application
```bash
# Development mode
make run

# Production mode with workers
python app.py
```

### Worker System Management
- Starts automatically with Flask app
- 3 worker threads process jobs concurrently
- Graceful shutdown on application exit
- Automatic recovery from worker failures

### Cache Management
- Summary cache: `data/summary_cache.json`
- Audio cache: `audio_cache/` directory
- Job state: `data/job_state.json`
- Automatic cleanup of old entries

## Known Issues and Solutions

### Timeout Errors
- **Issue**: YouTube API requests timing out
- **Solution**: Implemented 30-second timeout with retry logic

### Rate Limiting
- **Issue**: Too many rapid API calls
- **Solution**: Added 1-second delays between video processing

### Connection Status
- **Issue**: Multiple disconnect buttons appearing
- **Solution**: Consolidated to single status indicator

## Development Guidelines

### Adding New AI Models
1. Update model configuration in `app.py`
2. Add model to UI selection in `index.html`
3. Implement model-specific logic in `generate_summary()`
4. Test with various video types

### Modifying Worker System
1. Worker configuration in `WorkerManager.__init__()`
2. Job processing logic in `WorkerThread._process_job()`
3. Progress notifications via `_notify_progress()`
4. State persistence through `JobStateManager`

### UI Updates
1. Progress bars managed by `UIUpdater` class
2. Real-time updates via SSE events
3. Toast notifications for user feedback
4. Responsive design with mobile support

## Performance Considerations

### Optimization Points
- Cache lookups before API calls
- Parallel worker processing
- Rate limiting per client IP
- Automatic retry with backoff
- Connection pooling for SSE

### Resource Limits
- Max 1000 jobs in queue
- Max 100 SSE connections
- 24-hour job state retention
- 30-second API timeout
- 3 retry attempts per request

## Security Features

### Authentication
- Optional login system
- Password hashing with SHA-256
- IP-based lockout (5 attempts, 30-minute lockout)
- Session management

### Input Validation
- URL sanitization
- XSS prevention in UI
- Rate limiting protection
- Safe file path handling

## Debugging Tips

### Common Issues
1. **Worker not processing**: Check `worker_manager.is_running`
2. **SSE not connecting**: Verify `/sse` endpoint accessibility
3. **Cache issues**: Clear `data/` directory
4. **API failures**: Check environment variables
5. **Memory usage**: Monitor worker thread count

### Logging
- Application logs in console
- Worker logs with thread IDs
- SSE connection tracking
- Error classification in logs

## Future Enhancements

### Planned Features
- Database storage (replace JSON)
- User accounts and quotas
- Advanced queue management
- Webhook notifications
- API endpoint documentation

### Performance Improvements
- Redis for caching
- Celery for distributed workers
- CDN for static assets
- Database connection pooling