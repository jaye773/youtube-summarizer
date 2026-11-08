FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

# Install Python dependencies first to leverage Docker's layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app

COPY --chown=app:app . .

USER app

EXPOSE 5001

# python:slim has no curl, so probe with the standard library
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5001/health', timeout=4).status == 200 else 1)"

# gunicorn_config.py: one process (app state is in-memory), many threads so
# long-lived SSE streams and slow summaries don't block other requests.
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
