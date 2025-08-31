# AGENTS.md

This document provides guidance for AI agents working on the YouTube Summarizer codebase.

## Project Overview

**YouTube Summarizer** is a Flask web application that generates AI-powered summaries of YouTube videos and playlists. It extracts transcripts, uses AI models (Google Gemini and OpenAI GPT) to create summaries, and can convert them to audio.

The application is designed to be run with Docker, but can also be run manually. It features an optional login system for security, a caching mechanism for summaries and audio files, and support for using proxies to fetch YouTube transcripts.

## Architecture

The application follows a standard Flask project structure. Here are the key components:

-   **`app.py`**: The main Flask application file. It contains all the routes, API endpoints, and business logic.
-   **`templates/`**: Contains the HTML templates for the web interface.
-   **`static/`**: Contains the CSS and JavaScript files for the frontend.
-   **`data/`**: The directory where cached summaries and audio files are stored.
-   **`worker_manager.py`, `job_models.py`, `job_queue.py`, `job_state.py`**: These files implement a worker system for asynchronous processing of summarization tasks. This is a key feature for handling long-running summarization jobs without blocking the main application thread.
-   **`requirements.txt`**: Lists the Python dependencies for the project.
-   **`Dockerfile` and `docker-compose.yml`**: Used for building and running the application with Docker.
-   **`tests/`**: Contains the unit and integration tests for the application.

### APIs Used

The application integrates with the following APIs:

-   **Google APIs**:
    -   YouTube Data API v3: For fetching video metadata and playlist information.
    -   Google Generative AI (Gemini): For generating summaries.
    -   Google Cloud Text-to-Speech API: For converting summaries to audio.
-   **OpenAI API**: For generating summaries using GPT models.
-   **youtube-transcript-api**: A third-party library used to extract transcripts from YouTube videos.

## Getting Started

To set up the development environment and run the application, follow these steps:

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd youtube-summarizer
    ```

2.  **Set up environment variables**:
    Create a `.env` file in the project root and add your API keys:
    ```
    GOOGLE_API_KEY=your_google_api_key_here
    OPENAI_API_KEY=your_openai_api_key_here
    ```

3.  **Run with Docker (recommended)**:
    ```bash
    ./init_data.sh
    docker-compose up -d
    ```
    The application will be available at `http://localhost:5001`.

4.  **Run manually**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python app.py
    ```

## Testing

The project has a comprehensive test suite in the `tests/` directory. The tests are written using Python's `unittest` framework.

To run the tests, use the following command:

```bash
make test
```

Or, to run the full suite with coverage:

```bash
make coverage
```

The tests are divided into several files, including:

-   **`tests/test_app.py`**: Tests for the Flask application, including the API endpoints.
-   **`tests/test_transcript_and_summary.py`**: Tests for the transcript and summary generation logic.
-   **`tests/test_cache.py`**: Tests for the caching functionality.
-   **`tests/test_integration.py`**: End-to-end integration tests.

When adding new features, please add corresponding tests to ensure the application remains stable and reliable.

## Contributing

Contributions to the project are welcome. To contribute, please follow these steps:

1.  **Fork the repository**.
2.  **Create a new branch** for your changes.
3.  **Make your changes** and add any necessary tests.
4.  **Ensure all tests pass** by running `make test`.
5.  **Submit a pull request** with a clear description of your changes.

When working on a new feature, please ensure that you follow the existing coding style and conventions. Use a linter to check your code for any style issues. You can run the quality checks with:

```bash
make quality
```

And auto-fix formatting issues with:

```bash
make fix
```
