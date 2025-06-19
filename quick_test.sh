#!/bin/bash

# Quick test runner for YouTube Summarizer
# This script just runs the tests without all the quality checks

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🧪 Running YouTube Summarizer Tests..."
echo "======================================"

# Set testing environment variable
export TESTING=true

# Run tests
if python3 -m pytest -v --tb=short; then
    echo ""
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}❌ Some tests failed!${NC}"
    exit 1
fi 