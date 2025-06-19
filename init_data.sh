#!/bin/bash

# Initialize data directory for YouTube Summarizer

echo "Initializing data directory..."

# Create data directory if it doesn't exist
mkdir -p data/audio_cache

# Create summary_cache.json file if it doesn't exist
if [ ! -f data/summary_cache.json ]; then
    echo "{}" > data/summary_cache.json
    echo "Created empty summary_cache.json"
else
    echo "summary_cache.json already exists"
fi

# Fix permissions if needed
chmod 644 data/summary_cache.json
chmod 755 data/audio_cache

echo "Data directory initialized successfully!"
echo ""
echo "You can now run:"
echo "  docker-compose up -d"
echo "or"
echo "  podman-compose up -d" 