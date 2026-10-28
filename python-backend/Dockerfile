# Build context must be the repository root.
# Railway Build Configuration: Dockerfile builder; Dockerfile path: python-backend/Dockerfile.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    CURA_PRINTER_DEFINITION=/app/python-backend/cura_resources/definitions/generic_fdm_printer.def.json;/app/python-backend/cura_resources/definitions/generic_fdm_extruder.def.json

# Runtime libraries for OpenCascade/build123d, VTK/PyVista, and headless OCR.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgcc-s1 \
    libstdc++6 \
    libgl1 \
    libglx0 \
    libegl1 \
    libopengl0 \
    libglib2.0-0 \
    libsm6 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    cura-engine \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install the backend's Linux-compatible runtime requirements, including build123d.
COPY python-backend/requirements.lock ./python-backend/requirements.lock
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r ./python-backend/requirements.lock \
    && python -m pip check

# Install the repository's own package metadata/code without re-installing its
# desktop-only dependencies (for example pywin32 and PySide6) into this server image.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir --no-deps .

# Copy the ASGI service only after the shared package is installed.
COPY python-backend/ ./python-backend/
WORKDIR /app/python-backend

# Copy Cura resources to the expected location
COPY python-backend/cura_resources/ ./cura_resources/

# Fix ownership for non-root user
RUN chown -R appuser:appuser /app

# Fail the image build, rather than deploy a service that returns cadAvailable=false.
# This smoke test also verifies the OCR runtime and system Tesseract executable.
RUN python -c "import build123d, ai3d_designer, main; assert main.cad_runtime_is_available(), 'build123d runtime import failed'; assert main.is_ocr_available(), 'Tesseract/PyMuPDF/Pillow OCR runtime is unavailable'; print('CAD_RUNTIME_AVAILABLE=true OCR_AVAILABLE=true')"

# Validate CuraEngine is available and functional (fail build if not)
RUN python -c "import shutil, subprocess; path = shutil.which('CuraEngine'); assert path, 'CuraEngine binary not found on PATH'; result = subprocess.run([path, 'help'], capture_output=True, timeout=10); out = (result.stdout + result.stderr).decode(errors='replace'); assert 'CuraEngine slice' in out, 'CuraEngine help output unexpected: ' + out[:500]; print('CURA_ENGINE_AVAILABLE=true', path)"

# Validate bundled Cura definitions are present and valid JSON
RUN python -c "import json, os; p1='/app/python-backend/cura_resources/definitions/generic_fdm_printer.def.json'; p2='/app/python-backend/cura_resources/definitions/generic_fdm_extruder.def.json'; assert os.path.isfile(p1) and os.path.isfile(p2), 'Bundled Cura definitions missing'; json.load(open(p1)); json.load(open(p2)); print('CURA_DEFINITIONS_VALID=true')"

EXPOSE 8000

# Switch to non-root user
USER appuser

# This check is independent of curl and honors Railway's runtime PORT.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import json, os, urllib.request; r=json.load(urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=3)); assert r.get('cadAvailable') is True and r.get('ocrAvailable') is True" || exit 1

# Railway injects PORT. Never hard-code the public service port.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
