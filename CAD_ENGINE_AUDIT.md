# CAD Engine Audit and Engineering Roadmap

Audit date: 23 October 2026

This document separates capabilities that exist in code from capabilities that are only planned. The current engine is a conservative parametric primitive generator, not a general-purpose CAD kernel or a vision model that can reconstruct every mechanical part from a single image.

## Current architecture

- **Web UI:** `web/` — Next.js App Router, authenticated projects, private source-file uploads, STEP/STL downloads, and subscription gating.
- **CAD API:** `python-backend/main.py` — FastAPI service authenticated with `CAD_SERVICE_TOKEN`.
- **Specification:** `src/ai3d_designer/core/spec/models.py` — `PartSpec`, `FeatureSpec`, per-parameter units, transforms, and boolean operations.
- **Geometry kernel:** `src/ai3d_designer/core/geometry/engine.py` — build123d / OpenCascade primitives and sequential boolean operations.
- **Rule parser:** `src/ai3d_designer/core/nlp/parser.py` — deterministic pattern-based interpretation for supported, dimensioned descriptions. The local LLM class exists, but the deployed API currently selects the rule-based parser.
- **Validation and export:** `src/ai3d_designer/core/validation/validator.py` and `src/ai3d_designer/core/export/exporter.py`.
- **Desktop slicing:** `src/ai3d_designer/slicing/slicer.py` — CuraEngine integration. A valid CuraEngine installation and matching printer/extruder definitions are required; a fallback that emitted placeholder G-code is being removed.

## Known implemented web/backend behavior

- Sign-in/session verification and server-side user/role lookup.
- Text-to-CAD for supported descriptions, STEP/STL export, private storage, and saved projects.
- Supported base solids include box, cylinder, sphere, cone, torus, and wedge.
- Boolean union, difference, and intersection are represented in feature history.
- Source drawings/images can be uploaded and stored privately.
- Subscription gating checks for `ADMIN` or `PRO` with an `ACTIVE` status.

## Important incomplete areas

| Capability | Actual status | What is still needed |
| --- | --- | --- |
| General engineering drawing OCR | Not implemented in the web workflow | Secure raster/PDF processing, OCR engine deployment, structured extraction, and confidence/provenance reporting |
| Drawing annotations/tolerances/fits | Schema fields exist, but extraction pipeline is not implemented | Dimension and GD&T parsing, unit recognition, datum/feature association, and human review |
| Single-image depth relief/lithophane | Experimental prototype; work on this branch makes the generated relief/lithophane a validated watertight solid. Depth is relative, not metric. | Real image-quality benchmarks, optional MiDaS model deployment, quality/performance limits, and user review before printing |\n| Image-to-parametric CAD | Not implemented as an accurate engineering pipeline | Multiple views/calibration, feature correspondence, constraints, ambiguity handling, and validation |
| Complex parametric features | Extrusion/revolution/loft/sweep are declared but the geometry engine currently does not implement them | Explicit validated profiles, paths, axis definitions, dependency handling, and kernel tests |
| Fillets/chamfers/threads/gears/freeform surfaces | Not supported by the deterministic parser | Feature-history operations, standards-aware parameters, geometric failure handling, and tests |
| Automatic 3D printing slicer in the web app | Not implemented | Server/job orchestration, machine profiles, safe storage of G-code, and detailed print-setting UI |
| Production slicing on desktop | Requires CuraEngine and valid installation resources | Integration tests against supported CuraEngine versions and printer profiles |
| Full end-to-end tests with external services | Not automated | Separate test database, Firebase test setup, private Blob store, CAD service and Razorpay Test Mode |
| Arbitrary-design correctness | Cannot be guaranteed | Input-specific validation, confidence/ambiguity handling, engineering review, and measured benchmark coverage |

## Reliability rules

1. Never silently invent missing dimensions or silently drop an unsupported feature. Return a specific error instead.
2. Preserve explicit units on every parameter and document coordinate conventions. Feature positions in the current spec are millimetres; dimensional parameters carry their own unit.
3. Do not export an empty, non-finite, or invalid boolean result as a successful CAD file.
4. Treat a successful file write as necessary but not sufficient: validate file structure and geometry before making a download available.
5. Never label placeholder or partial G-code as a successful print slice.
6. Keep image-derived measurements, assumptions, and confidence separate from explicitly specified dimensions.
7. Before changing database schema or subscriptions, use backups and non-production verification.

## Verification

The pull request for this audit adds parser/geometry regression coverage and a dedicated Python CI workflow for Python 3.11 and 3.12. A code change is not considered verified until the workflow passes. Production CAD downloads and machine-specific G-code still require end-to-end tests with a configured CAD service and a real CuraEngine/printer profile.

## Staged roadmap

### Stage 1 — Reliability (current branch)
- Correct parameter-unit conversion and millimetre position semantics.
- Reject malformed/ambiguous specs rather than making misleading shapes.
- Check base feature operation, finite parameters, parent relationships, boolean results and kernel validity.
- Add regression tests for unit conversion, holes, hollow tube geometry, invalid intersections, and slicing failure behavior.
- Remove false-success placeholder G-code generation.

### Stage 2 — Parametric feature history
- Implement extrusion from validated 2D profiles.
- Implement revolution with explicit axis and closed profile.
- Implement loft/sweep with validated section/path relationships.
- Add fillet/chamfer operations with explicit edge selection and graceful kernel failure.
- Add property-based testing for boolean operations, dimensions, unit conversions, degenerate inputs, and topology.

### Stage 3 — Drawing interpretation
- Add real OCR for raster images and PDFs; keep OCR text as an editable intermediate artifact.
- Parse explicitly dimensioned views and tolerance strings into a structured, reviewable specification.
- Track units, text source, confidence, view association, and any unresolved dimensions.
- Require confirmation for ambiguous or underconstrained drawings; do not auto-manufacture from low-confidence interpretation.

### Stage 4 — Slicer integration
- Support a versioned set of machine/material profiles.
- Invoke a real slicer (CuraEngine or another maintained engine), validate its output, and store a print report.
- Add model orientation/build-volume checks, support/adhesion/material parameters, layer preview, time/material estimates, and explicit print approval.
- Never run unverified G-code on a printer automatically.

### Stage 5 — Benchmark and release gating
- Build a golden corpus of known dimensioned parts and drawings with expected geometry, units, volumes, topology and exported files.
- Run deterministic regression tests on every pull request.
- Test on the deployed backend before release; compare bounding boxes, volumes, dimensions and mesh validity against expected tolerances.
- Publish only the supported feature set; do not claim universal image-to-CAD accuracy.

