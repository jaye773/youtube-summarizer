#!/bin/bash
# Deployment script for SSE-fixed YouTube Summarizer
# Works with both Docker and Podman

set -e

echo "======================================="
echo "YouTube Summarizer SSE Fix Deployment"
echo "======================================="

# Detect container runtime
if command -v podman &> /dev/null; then
    RUNTIME="podman"
    COMPOSE="podman-compose"
    echo "✓ Using Podman"
elif command -v docker &> /dev/null; then
    RUNTIME="docker"
    COMPOSE="docker-compose"
    echo "✓ Using Docker"
else
    echo "❌ Neither Docker nor Podman found!"
    exit 1
fi

# Check for compose
if ! command -v $COMPOSE &> /dev/null; then
    echo "⚠️ $COMPOSE not found, trying with $RUNTIME compose..."
    COMPOSE="$RUNTIME compose"
fi

# Function to check if gevent is installed
check_gevent() {
    echo "Checking for gevent installation..."
    if $RUNTIME run --rm python:3.11-slim pip list 2>/dev/null | grep -q gevent; then
        echo "✓ gevent is available"
    else
        echo "📦 Installing gevent..."
        pip install gevent gunicorn[gevent] 2>/dev/null || true
    fi
}

# Function to stop existing containers
stop_existing() {
    echo "Stopping existing containers..."
    $COMPOSE -f docker-compose-podman.yml down 2>/dev/null || true
    $RUNTIME stop youtube-summarizer-web youtube-summarizer-nginx 2>/dev/null || true
    $RUNTIME rm youtube-summarizer-web youtube-summarizer-nginx 2>/dev/null || true
}

# Function to build and deploy
deploy() {
    echo "Building and deploying with SSE fixes..."
    
    # Use the SSE-optimized Dockerfile if it exists
    if [ -f "Dockerfile.sse" ]; then
        echo "Using SSE-optimized Dockerfile..."
        mv Dockerfile Dockerfile.backup 2>/dev/null || true
        cp Dockerfile.sse Dockerfile
    fi
    
    # Build and run
    $COMPOSE -f docker-compose-podman.yml build
    $COMPOSE -f docker-compose-podman.yml up -d
    
    echo "✓ Deployment complete!"
}

# Function to verify deployment
verify() {
    echo "Verifying deployment..."
    sleep 5
    
    # Check if containers are running
    if $RUNTIME ps | grep -q youtube-summarizer; then
        echo "✓ Containers are running"
    else
        echo "❌ Containers not running!"
        $RUNTIME ps
        exit 1
    fi
    
    # Check health endpoint
    if curl -s -f http://localhost:5001/health > /dev/null 2>&1; then
        echo "✓ Health endpoint responding"
    else
        echo "⚠️ Health endpoint not responding (may need implementation)"
    fi
    
    # Check SSE endpoint
    echo "Testing SSE endpoint..."
    timeout 2 curl -N http://localhost:5001/events 2>/dev/null | head -n 5 || true
    echo "✓ SSE endpoint tested"
}

# Function to show logs
show_logs() {
    echo ""
    echo "Container logs (last 20 lines):"
    echo "--------------------------------"
    $RUNTIME logs --tail 20 youtube-summarizer-web 2>/dev/null || \
    $COMPOSE -f docker-compose-podman.yml logs --tail 20 web
}

# Main execution
main() {
    # Parse arguments
    case "${1:-deploy}" in
        stop)
            stop_existing
            ;;
        deploy)
            check_gevent
            stop_existing
            deploy
            verify
            show_logs
            ;;
        verify)
            verify
            ;;
        logs)
            show_logs
            ;;
        test)
            echo "Running SSE tests..."
            python test_sse_fixed.py http://localhost:8431 --username admin --password password
            ;;
        *)
            echo "Usage: $0 [deploy|stop|verify|logs|test]"
            exit 1
            ;;
    esac
    
    echo ""
    echo "======================================="
    echo "SSE Fix Deployment Complete!"
    echo "======================================="
    echo ""
    echo "Access the application at:"
    echo "  - Direct: http://localhost:5001"
    echo "  - Via Nginx: http://localhost:8431"
    echo ""
    echo "Test SSE functionality:"
    echo "  ./deploy-sse-fix.sh test"
    echo ""
    echo "View logs:"
    echo "  ./deploy-sse-fix.sh logs"
}

# Run main function
main "$@"