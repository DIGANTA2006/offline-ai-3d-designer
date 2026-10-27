"""FastAPI CAD Service for Offline AI 3D Designer."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional
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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, model_validator
import uvicorn

# Import our CAD engine
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai3d_designer.core.spec.models import (
    PartSpec, FeatureSpec, ParameterSpec,
    PrimitiveType, OperationType, UnitSystem
)
from ai3d_designer.fitcheck.engine import FitCheckEngine
from ai3d_designer.fitcheck.models import ComponentSpec, EnclosureSpec
from ai3d_designer.fitcheck.presets import get_preset_component, list_hardware_presets
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.export.exporter import export_step, export_stl, export_3mf, export_zip_bundle, ExportResult, check_export_blockers
from ai3d_designer.core.validation.validator import validate_spec, validate_geometry
from ai3d_designer.core.nlp.parser import parse_natural_language
from ai3d_designer.ocr.pipeline import (
    MAX_DOCUMENT_BYTES,
    OCRInputError,
    OCRProcessingError,
    OCRUnavailableError,
    extract_drawing_annotations,
    extract_drawing_text,
    is_ocr_available,
)
from ai3d_designer.drawing_to_cad.blueprint import Blueprint
from ai3d_designer.drawing_to_cad.extraction import extract_blueprint
from ai3d_designer.drawing_to_cad.generator import GeometryError, export_blueprint
from ai3d_designer.slicing.slicer import SliceSettings, Slicer, get_slicing_capability


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
    drawingVisionAvailable: bool = False
    imageTo3dAvailable: bool = False
    slicingAvailable: bool = False
    slicingEngine: Optional[str] = None
    slicingStatusReason: Optional[str] = None
    imageTo3dStatus: str = "not offered"
    telemetry: dict[str, dict[str, Any]] = Field(default_factory=dict)
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


class SliceSettingsRequest(BaseModel):
    layer_height: float = Field(default=0.2, gt=0, le=1.0)
    wall_thickness: float = Field(default=1.2, gt=0, le=40.0)
    infill_density: float = Field(default=20.0, ge=0, le=100)
    support_enabled: bool = False
    preset: Optional[str] = Field(default=None, description="Quick, Balanced, or Strong")


class SliceRequest(BaseModel):
    stlBase64: str = Field(min_length=8, max_length=28 * 1024 * 1024)
    settings: SliceSettingsRequest = Field(default_factory=SliceSettingsRequest)


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
    vectorGeometry: list[dict] = Field(default_factory=list, max_length=250)
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


class ExportRequest(BaseModel):
    partSpec: dict
    formats: list[str] = Field(default_factory=lambda: ["step", "stl", "3mf", "zip"])
    settings: Optional[dict] = None


class ExportResponse(BaseModel):
    success: bool
    stepBase64: Optional[str] = None
    stlBase64: Optional[str] = None
    mfBase64: Optional[str] = None
    zipBase64: Optional[str] = None
    dimensionReport: Optional[dict] = None
    printGuide: Optional[str] = None
    error: Optional[str] = None
    validationErrors: list[str] = Field(default_factory=list)


class FitCheckRequest(BaseModel):
    """Request for an axis-aligned component/enclosure fit check."""

    presetId: Optional[str] = Field(default=None, min_length=1, max_length=100)
    component: Optional[ComponentSpec] = None
    componentConfirmed: bool = False
    enclosure: EnclosureSpec
    clearanceMm: Optional[float] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_component_source(self):
        if (self.presetId is None) == (self.component is None):
            raise ValueError("Provide exactly one of presetId or component.")
        return self


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
    supported = {"step", "stl", "3mf"}
    normalized = list(dict.fromkeys(str(fmt).strip().lower() for fmt in formats if str(fmt).strip()))
    if not normalized:
        raise ValueError("Choose at least one export format: step, stl, or 3mf.")
    unknown = sorted(set(normalized) - supported)
    if unknown:
        raise ValueError(f"Unsupported export format(s): {', '.join(unknown)}. Supported: step, stl, 3mf.")

    results = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for fmt in normalized:
            file_path = os.path.join(tmpdir, f"part.{fmt}")
            result: ExportResult
            if fmt == "step":
                result = export_step(part, file_path)
                result_key = "stepBase64"
            elif fmt == "stl":
                result = export_stl(part, file_path)
                result_key = "stlBase64"
            else:
                result = export_3mf(part, file_path)
                result_key = "mfBase64"

            if not result.success or not os.path.isfile(file_path) or os.path.getsize(file_path) == 0:
                details = "; ".join(result.validation_errors) or "exporter did not produce a non-empty file"
                raise RuntimeError(f"{fmt.upper()} export failed: {details}")

            with open(file_path, "rb") as exported_file:
                results[result_key] = base64.b64encode(exported_file.read()).decode("ascii")

    return results


def _export_zip_bundle_to_base64(part, part_spec: dict, settings: Optional[dict] = None) -> dict:
    """Export ZIP bundle and return base64."""
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "bundle.zip")
        result = export_zip_bundle(part, zip_path, part_spec=part_spec, settings=settings, include_step=True, include_stl=True, include_3mf=True, validate=True)
        if not result.success or not os.path.isfile(zip_path) or os.path.getsize(zip_path) == 0:
            details = "; ".join(result.validation_errors) or "exporter did not produce a non-empty ZIP file"
            raise RuntimeError(f"ZIP export failed: {details}")
        with open(zip_path, "rb") as f:
            return {"zipBase64": base64.b64encode(f.read()).decode("ascii")}


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
    vision_provider = os.environ.get("DRAWING_VISION_PROVIDER", "ollama").strip().lower()
    vision_url = os.environ.get("DRAWING_VISION_URL", "").strip()
    if vision_provider == "ollama":
        vision_url = vision_url or os.environ.get("OLLAMA_URL", "").strip()
    vision_available = bool(vision_url) and vision_provider in {
        "ollama", "openai", "openai_compatible", "openai-compatible"
    }
    slicing_capability = get_slicing_capability()
    limitations = [
        "Drawing OCR recognizes text and common annotations; it does not guarantee reconstruction of arbitrary 3D geometry from drawing views.",
        "The v1 deterministic generator supports a limited set of primitive/mechanical features; teeth, bends, threads and other unsupported shapes are blocked rather than approximated.",
        "Single-view image-to-3D reconstruction is not available in this service.",
    ]
    if not vision_available:
        limitations.append(
            "No vision model endpoint is configured. Structured extraction uses conservative explicit-label fallback; configure DRAWING_VISION_URL and DRAWING_VISION_MODEL for visual semantic extraction."
        )
    if not slicing_capability["available"]:
        limitations.append("STL slicing is unavailable: " + str(slicing_capability["reason"]))
    return HealthResponse(
        status=status,
        cadAvailable=ready,
        cadRuntimeAvailable=cad_runtime_available,
        serviceTokenConfigured=token_configured,
        cadRuntimeError=CAD_RUNTIME_IMPORT_ERROR,
        ocrAvailable=ocr_available,
        drawingVisionAvailable=vision_available,
        imageTo3dAvailable=False,
        slicingAvailable=bool(slicing_capability["available"]),
        slicingEngine=slicing_capability["engine"],
        slicingStatusReason=slicing_capability["reason"],
        limitations=limitations,
    )


@app.get("/api/v1/fit-check/presets", dependencies=[Depends(require_cad_service_token)])
def fit_check_presets():
    """Return built-in hardware starting points; users must confirm exact board dimensions."""
    return {
        "presets": list_hardware_presets(),
        "notice": (
            "Preset dimensions are starting points only. Verify the exact manufacturer, "
            "board revision, mounting-hole coordinates, and dimensions before relying on a fit check."
        ),
    }


@app.post("/api/v1/fit-check", dependencies=[Depends(require_cad_service_token)])
def fit_check(request: FitCheckRequest):
    """Check a confirmed component against confirmed axis-aligned enclosure dimensions."""
    if not request.enclosure.confirmed:
        raise HTTPException(
            status_code=422,
            detail="Confirm the enclosure's interior dimensions before running a fit check.",
        )

    if request.presetId is not None:
        if not request.componentConfirmed:
            raise HTTPException(
                status_code=422,
                detail="Confirm the selected preset's dimensions for your exact hardware revision.",
            )
        try:
            component = get_preset_component(request.presetId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # Confirmation is scoped to this explicit request; preset data remains unconfirmed in code.
        component = component.model_copy(update={"confirmed": True})
    else:
        component = request.component
        if component is None:
            raise HTTPException(status_code=422, detail="A component specification is required.")
        if not component.confirmed:
            raise HTTPException(
                status_code=422,
                detail="Confirm the component dimensions before running a fit check.",
            )

    clearance = component.clearance_mm if request.clearanceMm is None else request.clearanceMm
    try:
        report = FitCheckEngine(default_clearance_mm=clearance).check_all_components(
            [component],
            request.enclosure,
            clearance_mm=clearance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "success": True,
        "component": component.model_dump(mode="json"),
        "enclosure": request.enclosure.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
        "limitations": [
            "The current check compares axis-aligned width, depth, and height; it does not test rotated placements, keep-out zones, thermal clearances, or full 3D interference.",
            "Mounting-hole alignment is checked only when enclosure mounting-boss coordinates are supplied.",
            "A successful fit check does not certify printability, material suitability, structural strength, or manufacturing readiness.",
        ],
    }


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

        try:
            extracted = await asyncio.to_thread(
                extract_drawing_text, file_bytes, request.fileName, request.mimeType
            )
        except OCRProcessingError as exc:
            # A vision-capable extractor can still classify the rendered views when
            # text recognition fails. It must not invent measurements: an empty
            # dimension inventory leaves numeric blueprint fields ungrounded/cleared.
            if "No drawing text was recognized" not in str(exc):
                raise
            extracted = {
                **extract_drawing_annotations(""),
                "rawText": "",
                "confidence": 0.0,
                "confidenceMethod": "no_readable_text",
                "pageCount": 1,
                "needsReview": True,
                "limitations": [
                    "No readable drawing text was recognized. Visual classification may still run, but numeric dimensions remain ungrounded and must not be inferred as fact."
                ],
            }
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
                "vectorGeometry": structured.vector_geometry,
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


@app.post("/api/v1/slice", dependencies=[Depends(require_cad_service_token)])
def slice_stl(request: SliceRequest):
    """Slice a validated STL using CuraEngine; return G-code only on real success.
    
    Supports both project-generated STLs and standalone uploaded STLs (T63).
    """
    capability = get_slicing_capability()
    if not capability["available"]:
        raise HTTPException(
            status_code=503,
            detail=str(capability["reason"] or "A compatible CuraEngine installation is not available."),
        )

    try:
        stl_bytes = base64.b64decode(request.stlBase64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="stlBase64 must be valid standard Base64.") from exc
    if not stl_bytes or len(stl_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="STL must be non-empty and no larger than 20 MiB.")

    # Apply preset if specified
    settings_dict = request.settings.model_dump()
    preset = settings_dict.pop("preset", None)
    if preset:
        try:
            preset_settings = SliceSettings.from_preset(preset)
            # Merge preset with any explicitly provided settings
            for key, value in settings_dict.items():
                if value is not None:
                    setattr(preset_settings, key, value)
            settings = preset_settings
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        settings = SliceSettings(**settings_dict)

    with tempfile.TemporaryDirectory(prefix="offline-ai-slice-") as work_dir:
        stl_path = os.path.join(work_dir, "input.stl")
        gcode_path = os.path.join(work_dir, "output.gcode")
        with open(stl_path, "wb") as handle:
            handle.write(stl_bytes)

        result = Slicer().slice(stl_path, gcode_path, settings=settings, timeout_seconds=45.0)
        if not result.success or not result.gcode_path:
            detail = "; ".join(result.errors)[:1500] or "CuraEngine did not produce a valid G-code file."
            lowered = detail.lower()
            invalid_model_markers = ("watertight", "empty", "invalid", "exceed configured build volume", "could not validate stl")
            status_code = 422 if any(marker in lowered for marker in invalid_model_markers) else 502
            raise HTTPException(status_code=status_code, detail=detail)

        if os.path.getsize(result.gcode_path) > 40 * 1024 * 1024:
            raise HTTPException(status_code=502, detail="Generated G-code exceeds the 40 MiB download limit.")
        with open(result.gcode_path, "rb") as handle:
            gcode_bytes = handle.read()
        if not gcode_bytes:
            raise HTTPException(status_code=502, detail="CuraEngine returned an empty G-code file.")

        headers = {
            "Content-Disposition": 'attachment; filename="model.gcode"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Slice-Engine": str(capability["engine"] or "CuraEngine"),
            "X-Slice-Filament-Grams-Estimated": "true" if result.filament_weight_estimated else "false",
        }
        if result.print_time is not None:
            headers["X-Slice-Print-Time-Seconds"] = str(round(result.print_time, 2))
        if result.filament_used is not None:
            headers["X-Slice-Filament-Grams"] = str(round(result.filament_used, 3))
        if result.filament_length_m is not None:
            headers["X-Slice-Filament-Meters"] = str(round(result.filament_length_m, 4))
        if result.layers is not None:
            headers["X-Slice-Layers"] = str(result.layers)
        return Response(content=gcode_bytes, media_type="text/x-gcode", headers=headers)


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


@app.post("/api/v1/export", response_model=ExportResponse, dependencies=[Depends(require_cad_service_token)])
def export_part(request: ExportRequest):
    """Export a part to STEP, STL, 3MF, and/or ZIP bundle with dimension report and print guide.
    
    Blocks export on unconfirmed defaults (L-05) and sprocket previews (L-06).
    """
    try:
        # Check export blockers
        blockers = check_export_blockers(request.partSpec)
        if blockers:
            return ExportResponse(
                success=False,
                error="Export blocked",
                validationErrors=blockers,
            )
        
        # Create PartSpec from dict
        part_spec = PartSpec(**request.partSpec)
        
        # Validate spec
        spec_validation = validate_spec(part_spec)
        if not spec_validation.is_valid:
            return ExportResponse(
                success=False,
                error="Specification validation failed",
                validationErrors=[issue.message for issue in spec_validation.errors],
            )
        
        # Generate geometry
        part = create_part_from_spec(part_spec)
        
        # Validate geometry
        geom_validation = validate_geometry(part)
        if not geom_validation.is_valid:
            return ExportResponse(
                success=False,
                error="Geometry validation failed",
                validationErrors=[issue.message for issue in geom_validation.errors],
            )
        
        # Export individual formats
        export_results = _export_part_to_base64(part, request.formats)
        
        # Generate dimension report
        dimension_report = None
        if "step" in request.formats or "stl" in request.formats or "3mf" in request.formats or "zip" in request.formats:
            dimension_report = generate_dimension_report(part, part_spec.model_dump(mode="json"))
        
        # Generate print guide
        print_guide = None
        if "zip" in request.formats:
            print_guide = generate_print_guide(part, request.settings)
        
        # Export ZIP bundle if requested
        zip_base64 = None
        if "zip" in request.formats:
            zip_result = _export_zip_bundle_to_base64(part, part_spec.model_dump(mode="json"), request.settings)
            zip_base64 = zip_result.get("zipBase64")
        
        return ExportResponse(
            success=True,
            stepBase64=export_results.get("stepBase64"),
            stlBase64=export_results.get("stlBase64"),
            mfBase64=export_results.get("mfBase64"),
            zipBase64=zip_base64,
            dimensionReport=dimension_report,
            printGuide=print_guide,
        )
        
    except Exception as e:
        traceback.print_exc()
        return ExportResponse(
            success=False,
            error="Export failed. Check the service logs.",
            validationErrors=[str(e)],
        )


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
