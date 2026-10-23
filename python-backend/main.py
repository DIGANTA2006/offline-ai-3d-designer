"""FastAPI CAD Service for Offline AI 3D Designer."""

from contextlib import asynccontextmanager
from typing import Optional
import uuid
import base64
import io
import os
import tempfile
import traceback
import secrets
from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, File, UploadFile, Form, Header, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Import our CAD engine
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai3d_designer.core.spec.models import (
    PartSpec, FeatureSpec, ParameterSpec,
    PrimitiveType, OperationType, UnitSystem
)
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.export.exporter import export_step, export_stl, ExportResult
from ai3d_designer.core.validation.validator import validate_spec, validate_geometry
from ai3d_designer.core.nlp.parser import parse_natural_language
from ai3d_designer.core.ocr.extractor import (
    DrawingOcrError,
    OcrRuntimeUnavailable,
    decode_base64_file,
    extract_drawing_spec,
    is_ocr_runtime_available,
)
from starlette.concurrency import run_in_threadpool


# =============================================================================
# Request/Response Models
# =============================================================================

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    ocrAvailable: bool = False
    cadAvailable: bool = True
    imageTo3dAvailable: bool = False


def cad_runtime_is_available() -> bool:
    """Check that the CAD runtime can be imported before advertising readiness."""
    try:
        import build123d  # noqa: F401

        return True
    except Exception:
        return False


class OcrRequest(BaseModel):
    fileBase64: str = Field(min_length=1, max_length=14_000_000)
    fileName: str = Field(min_length=1, max_length=240)
    mimeType: str = Field(min_length=1, max_length=100)


class ExtractedSpec(BaseModel):
    dimensions: dict = Field(default_factory=dict)
    tolerances: dict = Field(default_factory=dict)
    fits: list = Field(default_factory=list)
    material: Optional[str] = None
    surfaceFinish: Optional[str] = None
    threads: list = Field(default_factory=list)
    views: list = Field(default_factory=list)
    annotations: list = Field(default_factory=list)
    confidence: float = 0.0
    rawText: str = ""


class OcrResponse(BaseModel):
    success: bool
    spec: Optional[ExtractedSpec] = None
    error: Optional[str] = None
    jobId: str


class GenerationRequest(BaseModel):
    spec: ExtractedSpec
    jobId: str
    userId: str


class GenerationResponse(BaseModel):
    success: bool
    stepUrl: Optional[str] = None
    stlUrl: Optional[str] = None
    glbUrl: Optional[str] = None
    fitReport: Optional[str] = None
    isApproximation: bool = False
    error: Optional[str] = None
    version: int = 1


class TextToCadRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    userId: str = Field(min_length=1, max_length=128)
    unitSystem: UnitSystem = UnitSystem.MM
    exportFormats: list[str] = Field(default_factory=lambda: ["step", "stl"])

class TextToCadResponse(BaseModel):
    success: bool
    partSpec: Optional[dict] = None
    stepBase64: Optional[str] = None
    stlBase64: Optional[str] = None
    validationErrors: list[str] = Field(default_factory=list)
    error: Optional[str] = None


def require_cad_service_token(authorization: Optional[str] = Header(default=None)) -> None:
    """Require the shared web-to-CAD token; only explicit development/test may omit it."""
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    expected = os.environ.get("CAD_SERVICE_TOKEN", "").strip()
    is_development = app_env in {"development", "dev", "test"}
    if not expected:
        if is_development:
            return
        raise HTTPException(status_code=503, detail="CAD_SERVICE_TOKEN is not configured on the CAD service.")

    scheme, separator, supplied = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized CAD service request.")

# =============================================================================
# In-memory job storage (replace with Redis/DB in production)
# =============================================================================

jobs: dict[str, dict] = {}


# =============================================================================
# Helper Functions
# =============================================================================

def _export_part_to_base64(part, formats: list[str]) -> dict:
    """Export the requested formats; never report success for a skipped/failed export."""
    supported = {"step", "stl"}
    normalized = list(dict.fromkeys(str(fmt).strip().lower() for fmt in formats if str(fmt).strip()))
    if not normalized:
        raise ValueError("Choose at least one export format: step or stl.")
    unknown = sorted(set(normalized) - supported)
    if unknown:
        raise ValueError(f"Unsupported export format(s): {', '.join(unknown)}. Supported: step, stl.")

    results = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for fmt in normalized:
            file_path = os.path.join(tmpdir, f"part.{fmt}")
            result: ExportResult
            if fmt == "step":
                result = export_step(part, file_path)
                result_key = "stepBase64"
            else:
                result = export_stl(part, file_path)
                result_key = "stlBase64"

            if not result.success or not os.path.isfile(file_path) or os.path.getsize(file_path) == 0:
                details = "; ".join(result.validation_errors) or "exporter did not produce a non-empty file"
                raise RuntimeError(f"{fmt.upper()} export failed: {details}")

            with open(file_path, "rb") as exported_file:
                results[result_key] = base64.b64encode(exported_file.read()).decode("ascii")

    return results
# =============================================================================
# Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 CAD Service starting...")
    yield
    # Shutdown
    print("🛑 CAD Service shutting down...")


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Offline AI 3D Designer - CAD Service",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
cors_origins = [origin.strip().rstrip("/") for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Routes
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    # Keep health checks public, but never advertise a CAD runtime that cannot load.
    cad_available = cad_runtime_is_available()
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    is_development = app_env in {"development", "dev", "test"}
    token_configured = bool(os.environ.get("CAD_SERVICE_TOKEN", "").strip())
    ready = cad_available and (is_development or token_configured)
    status = "healthy" if ready else "degraded"
    return HealthResponse(
        status=status,
        cadAvailable=ready,
        ocrAvailable=is_ocr_runtime_available(),
        imageTo3dAvailable=False,
    )


@app.post("/api/v1/ocr/extract", response_model=OcrResponse, dependencies=[Depends(require_cad_service_token)])
async def ocr_extract(request: OcrRequest):
    """Extract reviewable OCR text and engineering-dimension candidates from a PDF/image."""
    job_id = str(uuid.uuid4())[:8]
    try:
        file_bytes = decode_base64_file(request.fileBase64)
        extracted = await run_in_threadpool(
            extract_drawing_spec,
            file_bytes,
            request.fileName,
            request.mimeType,
        )
        spec = ExtractedSpec(**extracted)
        if not spec.rawText.strip():
            return OcrResponse(
                success=False,
                spec=spec,
                error="No readable drawing text was detected. Try a higher-resolution, clearer scan. No CAD geometry was generated.",
                jobId=job_id,
            )
        return OcrResponse(
            success=True,
            spec=spec,
            jobId=job_id,
        )
    except OcrRuntimeUnavailable as exc:
        return OcrResponse(
            success=False,
            error=str(exc),
            jobId=job_id,
        )
    except DrawingOcrError as exc:
        return OcrResponse(
            success=False,
            error=str(exc),
            jobId=job_id,
        )
    except Exception:
        traceback.print_exc()
        return OcrResponse(
            success=False,
            error="Drawing OCR failed unexpectedly. Check the CAD service logs; no CAD geometry was generated.",
            jobId=job_id,
        )


@app.post("/api/v1/generate", response_model=GenerationResponse, dependencies=[Depends(require_cad_service_token)])
async def generate_cad(request: GenerationRequest):
    """Generate CAD from extracted specification."""
    job_id = request.jobId
    
    # TODO: Implement full pipeline (Phase 3+)
    return GenerationResponse(
        success=False,
        error="Full generation pipeline not yet implemented. Use /api/v1/text-to-cad.",
        jobId=job_id,
    )


@app.post("/api/v1/text-to-cad", response_model=TextToCadResponse, dependencies=[Depends(require_cad_service_token)])
async def text_to_cad(request: TextToCadRequest):
    """Convert natural language to 3D CAD model."""
    try:
        # Parse natural language
        parse_result = parse_natural_language(request.text, unit_system=request.unitSystem)
        
        if not parse_result.success or not parse_result.spec:
            return TextToCadResponse(
                success=False,
                error=parse_result.error or "Failed to parse description",
                validationErrors=([parse_result.error] if parse_result.error else []),
            )
        
        part_spec = parse_result.spec
        part_spec.unit_system = request.unitSystem
        
        # Validate spec
        spec_validation = validate_spec(part_spec)
        if not spec_validation.is_valid:
            return TextToCadResponse(
                success=False,
                error="Specification validation failed",
                validationErrors=[issue.message for issue in spec_validation.issues],
            )
        
        # Generate geometry
        part = create_part_from_spec(part_spec)
        
        # Validate geometry
        geom_validation = validate_geometry(part)
        if not geom_validation.is_valid:
            return TextToCadResponse(
                success=False,
                error="Geometry validation failed",
                validationErrors=[issue.message for issue in geom_validation.issues],
            )
        
        # Export to requested formats
        export_results = _export_part_to_base64(part, request.exportFormats)
        
        return TextToCadResponse(
            success=True,
            partSpec=part_spec.model_dump(mode="json"),
            stepBase64=export_results.get("stepBase64"),
            stlBase64=export_results.get("stlBase64"),
        )
        
    except Exception as e:
        traceback.print_exc()
        return TextToCadResponse(
            success=False,
            error="CAD generation failed. Check the service logs and try a simpler dimensioned description.",
        )


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
