"""
FastAPI routes for printability checking and fixing.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai3d_designer.core.spec.models import PartSpec
from ai3d_designer.printability.checks import (
    PrintabilityChecker,
    CheckResult,
    CheckStatus,
    run_all_checks,
)
from ai3d_designer.printability.explanations import (
    EXPLANATIONS,
    GLOSSARY,
    get_explanation,
    get_glossary_entry,
)
from ai3d_designer.printability.fixes import (
    FixAction,
    FixResult,
    apply_fix_and_reverify,
    get_available_fixes,
)

router = APIRouter(prefix="/api/v1/printability", tags=["printability"])


class PrintabilityCheckRequest(BaseModel):
    partSpec: Dict[str, Any]
    thresholds: Optional[Dict[str, float]] = None
    bedSize: Optional[List[float]] = None


class PrintabilityCheckResponse(BaseModel):
    success: bool
    checks: List[Dict[str, Any]]
    summary: Dict[str, int]
    error: Optional[str] = None


class FixRequest(BaseModel):
    partSpec: Dict[str, Any]
    action: FixAction
    checkId: str
    parameters: Optional[Dict[str, Any]] = None


class FixResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    notices: List[str] = Field(default_factory=list)


class ExplanationResponse(BaseModel):
    checkId: str
    explanation: Dict[str, str]
    glossary: Dict[str, str]


@router.post("/check", response_model=PrintabilityCheckResponse)
def check_printability(request: PrintabilityCheckRequest):
    """
    Run all 8 printability checks on a PartSpec.
    
    Returns all checks including passes, with 4-part explanations
    and glossary references.
    """
    try:
        part_spec = PartSpec(**request.partSpec)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid PartSpec: {e}")
    
    bed_size = None
    if request.bedSize and len(request.bedSize) == 3:
        bed_size = tuple(request.bedSize)
    
    checker = PrintabilityChecker(
        thresholds=request.thresholds,
        bed_size=bed_size,
    )
    
    results = checker.check_all(part_spec)
    
    # Build summary
    summary = {
        "total": len(results),
        "pass": sum(1 for r in results if r.status == CheckStatus.PASS),
        "fail": sum(1 for r in results if r.status == CheckStatus.FAIL),
        "warning": sum(1 for r in results if r.status == CheckStatus.WARNING),
        "skipped": sum(1 for r in results if r.status == CheckStatus.SKIPPED),
    }
    
    # Add explanations to each check
    checks_with_explanations = []
    for result in results:
        check_dict = result.to_dict()
        check_dict["explanation"] = get_explanation(result.check_id)
        check_dict["available_fixes"] = [
            action.value for action in get_available_fixes(result.check_id)
        ]
        checks_with_explanations.append(check_dict)
    
    return PrintabilityCheckResponse(
        success=True,
        checks=checks_with_explanations,
        summary=summary,
    )


@router.post("/fix", response_model=FixResponse)
def apply_printability_fix(request: FixRequest):
    """
    Apply a 1-click fix action and re-verify.
    
    Mutates the PartSpec, rebuilds in kernel, re-runs checks.
    """
    try:
        part_spec = PartSpec(**request.partSpec)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid PartSpec: {e}")
    
    # Validate action is applicable
    available = get_available_fixes(request.checkId)
    if request.action not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Action '{request.action}' not applicable for check '{request.checkId}'. Available: {[a.value for a in available]}",
        )
    
    result = apply_fix_and_reverify(
        part_spec,
        request.action,
        request.checkId,
        request.parameters,
    )
    
    if not result.success:
        return FixResponse(success=False, error=result.error)
    
    notices: List[str] = []
    if request.action == FixAction.ADD_SUPPORT:
        notices.append(
            "This is a support recommendation only: it marks features as needing support, "
            "but does not generate support geometry or change slicer settings. Configure "
            "supports in the selected slicer and inspect its preview."
        )
    elif request.action == FixAction.SPLIT:
        notices.append(
            "This is a split recommendation only: it records split metadata but does not "
            "create separate solids or exportable split parts."
        )

    return FixResponse(success=True, result=result.to_dict(), notices=notices)


@router.get("/explanations/{check_id}", response_model=ExplanationResponse)
def get_check_explanation(check_id: str):
    """Get 4-part explanation and glossary for a check."""
    if check_id not in EXPLANATIONS:
        raise HTTPException(status_code=404, detail=f"Check '{check_id}' not found")
    
    # Include relevant glossary terms
    relevant_terms = {
        "min_wall_thickness": ["FDM", "nozzle", "wall thickness", "layer height"],
        "hole_size": ["FDM", "nozzle", "shrinkage"],
        "overhang_angle": ["overhang", "support", "layer height"],
        "bed_fit": ["build volume", "orientation", "bed adhesion"],
        "bridging_span": ["bridging", "support", "overhang"],
        "base_contact": ["bed adhesion", "brim", "raft", "warping"],
        "hole_edge_distance": ["wall thickness", "nozzle"],
        "flatness": ["planarity", "first layer", "elephant's foot", "bed adhesion"],
    }
    
    terms = relevant_terms.get(check_id, [])
    glossary = {term: get_glossary_entry(term) for term in terms}
    
    return ExplanationResponse(
        checkId=check_id,
        explanation=EXPLANATIONS[check_id],
        glossary=glossary,
    )


@router.get("/glossary")
def get_glossary():
    """Get the complete beginner glossary."""
    return {"glossary": GLOSSARY}


@router.get("/fixes/{check_id}")
def get_available_fixes_for_check(check_id: str):
    """Get available fix actions for a check."""
    fixes = get_available_fixes(check_id)
    return {
        "checkId": check_id,
        "availableFixes": [f.value for f in fixes],
        "descriptions": {
            FixAction.ROTATE.value: "Reorient the part on the build plate",
            FixAction.THICKEN.value: "Increase wall/shell thickness",
            FixAction.ENLARGE.value: "Enlarge holes or move features from edges",
            FixAction.SPLIT.value: "Record a proposed split; separate solids are not generated yet",
            FixAction.ADD_SUPPORT.value: (
                "Mark features as needing support; support geometry and slicer settings are not generated"
            ),
        },
    }
