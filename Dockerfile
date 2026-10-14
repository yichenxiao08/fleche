FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock requirements-video.lock ./
RUN pip install --no-cache-dir -r requirements.lock
ARG VIDEO=false
RUN if [ "$VIDEO" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libasound2 libportaudio2 \
      && rm -rf /var/lib/apt/lists/* \
      && pip install --no-cache-dir -r requirements-video.lock; \
    fi
COPY pyproject.toml README.md ./
COPY src ./src
COPY knowledge ./knowledge
COPY examples ./examples
COPY scripts/setup_video.py ./scripts/setup_video.py
RUN pip install --no-deps . \
    && if [ "$VIDEO" = "true" ]; then python scripts/setup_video.py; fi \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/data && chown app:app /app/data

USER app
ENV FENCECOACH_KNOWLEDGE_DIR=/app/knowledge FENCECOACH_DB_PATH=/app/data/fencecoach.sqlite3 FENCECOACH_SEED_EXAMPLES=true
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn fencecoach.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
