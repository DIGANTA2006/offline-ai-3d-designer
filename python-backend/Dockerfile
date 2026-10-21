# Build from the repository root with Dockerfile path: python-backend/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Native OpenCascade runtime libraries used by build123d.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY python-backend/requirements.txt ./python-backend/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r ./python-backend/requirements.txt

# The CAD service imports the shared package from /app/src.
COPY src/ ./src/
COPY python-backend/ ./python-backend/

WORKDIR /app/python-backend
ENV PYTHONPATH=/app/src
EXPOSE 8000

# Use Python's standard library so the healthcheck does not depend on curl being installed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=3)" || exit 1

# Railway supplies PORT at runtime; do not hard-code 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]