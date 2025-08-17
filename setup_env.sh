#!/bin/bash

# YouTube Summarizer - Environment Setup Script

echo "🔧 YouTube Summarizer - Environment Setup"
echo "==========================================="
echo ""

# Check if .env file exists
if [ -f ".env" ]; then
    echo "📋 Found existing .env file"
    if grep -q "GOOGLE_API_KEY" .env; then
        echo "✅ GOOGLE_API_KEY is already configured in .env"
        echo "🔍 To check if it's working, visit: http://localhost:5001/api_status"
    else
        echo "⚠️  .env file exists but GOOGLE_API_KEY is not set"
        echo "💡 Add this line to your .env file:"
        echo "   GOOGLE_API_KEY=your_api_key_here"
    fi
else
    echo "📝 Creating .env file..."
    echo "# YouTube Summarizer Configuration" > .env
    echo "GOOGLE_API_KEY=your_google_api_key_here" >> .env
    echo "OPENAI_API_KEY=your_openai_api_key_here" >> .env
    echo "✅ Created .env file"
    echo "🔧 Please edit .env and replace the API keys with your actual keys"
fi

echo ""
echo "📋 Required APIs:"
echo "   Google Cloud APIs (Required):"
echo "   1. YouTube Data API v3"
echo "   2. Generative AI API (Gemini)"
echo "   3. Cloud Text-to-Speech API"
echo ""
echo "   OpenAI API (Optional, for GPT models):"
echo "   4. OpenAI API"
echo ""
echo "🔗 Get Google API key from: https://console.cloud.google.com/"
echo "🔗 Get OpenAI API key from: https://platform.openai.com/"
echo "📖 See README.md for detailed setup instructions"
echo ""
echo "🚀 To start the app:"
echo "   python3 app.py"
echo ""
echo "🔍 To check API status:"
echo "   curl http://localhost:5001/api_status" 