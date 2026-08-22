# Container image for the Personal AI Chat Web App.
# Works on Fly.io, Railway, Google Cloud Run, a VPS, or Render (Docker runtime).

FROM python:3.12-slim

# Keep Python lean and predictable inside a container.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app
COPY static ./static
COPY templates ./templates

# Where the SQLite database and uploads live. Mount a volume here to keep
# your chats between deploys (see DEPLOY.md).
ENV DB_PATH=/data/chat.db \
    UPLOAD_DIR=/data/uploads
RUN mkdir -p /data

EXPOSE 8000

# $PORT is provided by most hosts; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
