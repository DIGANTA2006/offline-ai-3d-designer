"""FastAPI CAD Service for Offline AI 3D Designer."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional
import uuid
import base64
import io
import os
import re
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
from ai3d_designer.ocr.pipeline import (
    MAX_DOCUMENT_BYTES,
    OCRInputError,
    OCRProcessingError,
    OCRUnavailableError,
    extract_drawing_text,
    is_ocr_available,
)
from ai3d_designer.drawing_to_cad.blueprint import Blueprint
from ai3d_designer.drawing_to_cad.extraction import extract_blueprint
from ai3d_designer.drawing_to_cad.generator import GeometryError, export_blueprint


# =============================================================================
# Request/Response Models
# =============================================================================

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    # cadAvailable means that the engine and service-to-service auth are ready.
    cadAvailable: bool = False
    # Keep component-level diagnostics separate so health results are actionable.
    cadRuntimeAvailable: bool = False
    serviceTokenConfigured: bool = False
    cadRuntimeError: Optional[str] = None
    ocrAvailable: bool = False
    imageTo3dAvailable: bool = False
    limitations: list[str] = Field(default_factory=list)


CAD_RUNTIME_IMPORT_ERROR: Optional[str] = None


def cad_runtime_is_available() -> bool:
    """Check that build123d loads, and log the actionable import exception on failure."""
    global CAD_RUNTIME_IMPORT_ERROR
    try:
        import build123d  # noqa: F401

        CAD_RUNTIME_IMPORT_ERROR = None
        return True
    except Exception as exc:
        CAD_RUNTIME_IMPORT_ERROR = type(exc).__name__
        print(f"CAD runtime import check failed: {type(exc).__name__}: {exc}")
        return False


class OcrRequest(BaseModel):
    fileBase64: str = Field(min_length=4, max_length=7_100_000)
    fileName: str = Field(min_length=1, max_length=200)
    mimeType: str = Field(min_length=3, max_length=100)


class ExtractedSpec(BaseModel):
    dimensions: dict = Field(default_factory=dict)
    tolerances: list = Field(default_factory=list)
    fits: list = Field(default_factory=list)
    material: Optional[str] = None
    surfaceFinish: Optional[str] = None
    threads: list = Field(default_factory=list)
    views: list = Field(default_factory=list)
    annotations: list = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidenceMethod: Optional[str] = None
    rawText: str = Field(default="", max_length=50_000)
    pageCount: int = Field(default=1, ge=1, le=8)
    needsReview: bool = True
    limitations: list[str] = Field(default_factory=list)
    # Structured geometry is returned in parallel with OCR and is persisted with the OCR result.
    blueprint: Optional[Blueprint] = None
    dimensionInventory: list[dict] = Field(default_factory=list, max_length=200)
    blueprintSource: Optional[str] = None
    blueprintSourcePages: int = Field(default=1, ge=1, le=4)
    blueprintClearedFields: list[str] = Field(default_factory=list)
    blueprintVisionModel: Optional[str] = None


class OcrResponse(BaseModel):
    success: bool
    spec: Optional[ExtractedSpec] = None
    error: Optional[str] = None
    jobId: str


class GenerationRequest(BaseModel):
    spec: ExtractedSpec
    jobId: str = Field(min_length=1, max_length=128)
    userId: str = Field(min_length=1, max_length=128)
    reviewed: bool = False
    reviewedDescription: Optional[str] = Field(default=None, max_length=4000)
    # A reviewed editor blueprint takes precedence over free-text parsing.
    blueprint: Optional[Blueprint] = None


class GenerationResponse(BaseModel):
    success: bool
    jobId: Optional[str] = None
    stepUrl: Optional[str] = None
    stlUrl: Optional[str] = None
    glbUrl: Optional[str] = None
    stepBase64: Optional[str] = None
    stlBase64: Optional[str] = None
    partSpec: Optional[dict] = None
    fitReport: Optional[str] = None
    metrics: Optional[dict] = None
    warnings: list[str] = Field(default_factory=list)
    isApproximation: bool = False
    error: Optional[str] = None
    validationErrors: list[str] = Field(default_factory=list)
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
    # Keep health checks public, but report each capability separately to make
    # deployment failures diagnosable without exposing environment secrets.
    cad_runtime_available = cad_runtime_is_available()
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    is_development = app_env in {"development", "dev", "test"}
    token_configured = bool(os.environ.get("CAD_SERVICE_TOKEN", "").strip())
    ready = cad_runtime_available and (is_development or token_configured)
    status = "healthy" if ready else "degraded"
    ocr_available = is_ocr_available()
    limitations = [
        "Drawing OCR recognizes text and common annotations; it does not reconstruct arbitrary 3D geometry from drawing views.",
        "Single-view image-to-3D reconstruction is not available in this service.",
    ]
    return HealthResponse(
        status=status,
        cadAvailable=ready,
        cadRuntimeAvailable=cad_runtime_available,
        serviceTokenConfigured=token_configured,
        cadRuntimeError=CAD_RUNTIME_IMPORT_ERROR,
        ocrAvailable=ocr_available,
        imageTo3dAvailable=False,
        limitations=limitations,
    )


@app.post("/api/v1/ocr/extract", response_model=OcrResponse, dependencies=[Depends(require_cad_service_token)])
async def ocr_extract(request: OcrRequest):
    """Extract visible text and a grounded, structured blueprint from an engineering drawing."""
    job_id = str(uuid.uuid4())[:8]
    if not is_ocr_available():
        raise HTTPException(
            status_code=503,
            detail="Drawing OCR is not configured. Install pytesseract, PyMuPDF, Pillow, and the tesseract-ocr system executable.",
        )

    try:
        if len(request.fileBase64) > 7_100_000:
            raise OCRInputError("Encoded drawing exceeds the OCR request limit.")
        try:
            file_bytes = base64.b64decode(request.fileBase64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise OCRInputError("fileBase64 must be valid standard Base64.") from exc
        if len(file_bytes) > MAX_DOCUMENT_BYTES:
            raise OCRInputError("Drawing exceeds the 5 MiB OCR input limit.")

        extracted = await asyncio.to_thread(
            extract_drawing_text, file_bytes, request.fileName, request.mimeType
        )
        structured = await extract_blueprint(
            file_bytes=file_bytes,
            file_name=request.fileName,
            mime_type=request.mimeType,
            raw_text=str(extracted.get("rawText", "")),
            dimension_data=extracted,
        )
        extracted.update(
            {
                "blueprint": structured.blueprint.model_dump(mode="json"),
                "dimensionInventory": [
                    token.model_dump(mode="json") for token in structured.dimension_inventory
                ],
                "blueprintSource": structured.source,
                "blueprintSourcePages": structured.source_pages,
                "blueprintClearedFields": structured.cleared_fields,
                "blueprintVisionModel": structured.vision_model,
            }
        )
        extracted["needsReview"] = True
        extracted["limitations"] = list(
            dict.fromkeys(
                list(extracted.get("limitations", []))
                + [
                    "Structured drawing interpretation is provisional; compare each field against the drawing.",
                    "The v1 deterministic generator supports circular flanges, prismatic parts, simple open-top rectangular enclosures, and revolved profiles. Gear/sprocket teeth and sheet-metal bends are not generated automatically.",
                    "An optional vision-capable model must be configured using DRAWING_VISION_URL and DRAWING_VISION_MODEL for visual semantic extraction. Without it, only explicitly labelled text is used.",
                ]
            )
        )
        spec = ExtractedSpec(**extracted)
        return OcrResponse(success=True, spec=spec, jobId=job_id)
    except OCRInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OCRProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        print(f"OCR extraction failed for job {job_id}: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Drawing extraction failed unexpectedly. Check service logs.") from exc


@app.post("/api/v1/generate", response_model=GenerationResponse, dependencies=[Depends(require_cad_service_token)])
def generate_cad(request: GenerationRequest):
    """Generate STEP/STL from reviewed OCR text when the conservative parser can resolve it."""
    job_id = request.jobId
    if not request.reviewed:
        raise HTTPException(
            status_code=409,
            detail="Review the extracted text, dimensions, tolerances and shape assumptions before CAD generation; set reviewed=true only after checking the drawing.",
        )

    if request.blueprint is not None:
        try:
            exports = export_blueprint(request.blueprint)
            return GenerationResponse(
                success=True,
                jobId=job_id,
                stepBase64=exports["stepBase64"],
                stlBase64=exports["stlBase64"],
                partSpec=exports["partSpec"],
                fitReport=exports["fitReport"],
                metrics=exports["metrics"],
                warnings=exports["warnings"],
                isApproximation=True,
            )
        except GeometryError as exc:
            detail = str(exc)
            return GenerationResponse(
                success=False,
                jobId=job_id,
                error=detail[:500],
                validationErrors=[detail[:1000]],
                warnings=request.blueprint.warnings,
                isApproximation=True,
            )
        except Exception as exc:
            print(f"Structured blueprint CAD generation failed for job {job_id}: {type(exc).__name__}: {exc}")
            return GenerationResponse(
                success=False,
                jobId=job_id,
                error="Structured blueprint CAD generation failed. Check the reviewed fields and CAD service logs.",
                validationErrors=["No CAD files were returned because export validation failed."],
                isApproximation=True,
            )

    prompt = (request.reviewedDescription or request.spec.rawText or "").strip()
    if len(prompt) < 5:
        raise HTTPException(
            status_code=422,
            detail="No reviewed dimensioned description was supplied. Edit the OCR text into an explicit part description first.",
        )
    if not re.search(
        r"\b(box|block|cube|rectangular|plate|slab|cylinder|rod|shaft|pin|pipe|tube|sphere|ball|cone|conical|torus|donut|ring|wedge|ramp|triangle)\b",
        prompt,
        re.IGNORECASE,
    ):
        return GenerationResponse(
            success=False,
            jobId=job_id,
            error="Specify the primary shape explicitly (for example, box, plate, cylinder, tube, sphere or cone) along with its required dimensions.",
            validationErrors=["The service will not infer a shape from dimension triplets alone."],
            isApproximation=True,
        )

    try:
        parsed = parse_natural_language(prompt, unit_system=UnitSystem.MM)
        if not parsed.success or parsed.spec is None:
            detail = parsed.error or "The reviewed description could not be parsed."
            return GenerationResponse(success=False, jobId=job_id, error=detail, validationErrors=[detail], isApproximation=True)

        part_spec = parsed.spec
        spec_validation = validate_spec(part_spec)
        if not spec_validation.is_valid:
            messages = [issue.message for issue in spec_validation.errors]
            return GenerationResponse(
                success=False,
                jobId=job_id,
                error="Reviewed part specification failed validation.",
                validationErrors=messages,
                isApproximation=True,
            )

        part = create_part_from_spec(part_spec)
        geometry_validation = validate_geometry(part)
        if not geometry_validation.is_valid:
            messages = [issue.message for issue in geometry_validation.errors]
            return GenerationResponse(
                success=False,
                jobId=job_id,
                error="Generated geometry failed CAD-kernel validation.",
                validationErrors=messages,
                isApproximation=True,
            )

        exports = _export_part_to_base64(part, ["step", "stl"])
        fit_report = (
            "Geometry and file validation passed for the supported primitive features. "
            "This does not certify drawing interpretation, GD&T, fits, tolerances, material, "
            "or manufacturing suitability. Inspect the model in CAD and compare every dimension "
            "against the source drawing before use."
        )
        return GenerationResponse(
            success=True,
            jobId=job_id,
            stepBase64=exports.get("stepBase64"),
            stlBase64=exports.get("stlBase64"),
            partSpec=part_spec.model_dump(mode="json"),
            fitReport=fit_report,
            isApproximation=True,
        )
    except Exception as exc:
        print(f"OCR-derived CAD generation failed for job {job_id}: {type(exc).__name__}: {exc}")
        return GenerationResponse(
            success=False,
            jobId=job_id,
            error="CAD generation failed. Simplify the reviewed dimensions or try a supported primitive description.",
            validationErrors=["CAD kernel or export validation failed; no model was returned."],
            isApproximation=True,
        )


@app.post("/api/v1/text-to-cad", response_model=TextToCadResponse, dependencies=[Depends(require_cad_service_token)])
def text_to_cad(request: TextToCadRequest):
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
