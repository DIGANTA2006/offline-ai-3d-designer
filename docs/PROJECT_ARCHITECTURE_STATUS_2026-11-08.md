# Offline AI 3D Designer — Project Architecture, Status and Delivery

**Document date:** 8 November 2026  
**Product:** Offline AI 3D Designer  
**Client:** C-DAC Kolkata  
**Product owner / architect:** Diganta Chakraborty  
**Repository:** \`DIGANTA2006/offline-ai-3d-designer\` — Private  
**Default branch:** \`main\`  
**Verified main:** \`9c8707c89f6ae04607a4a77cd183ba1491ad18a8\`  
**Status:** Engineering baseline for product-owner review; not a release certificate

## 1. Product identity and mission

Offline AI 3D Designer is an engineering-grade CAD and manufacturing platform whose interface is designed to make 3D printing practical for people who do not know CAD, drawing conventions, dimensions, tolerances or slicer settings.

This is **not a beginner coding project, toy CAD application or reduced engineering tool**. A guided user experience is a presentation and assistance layer. Guided and advanced modes must use the same validated feature program, CAD kernel, dimensional provenance, geometry checks, export safeguards, printability rules and manufacturing acceptance gates.

The user explains what they need. The application performs the engineering workflow, explains uncertainty, asks for missing information and does not silently invent dimensions.

Target users include household users, electricians, mechanics, farmers, shopkeepers, students and local 3D-printing service customers.

## 2. Intended product workflow

1. Accept a plain-language description, dimensioned drawing, sketch, datasheet or template.
2. Validate uploaded content and preserve the source privately.
3. Extract text/annotations with OCR and inspect rendered drawing pixels using an approved vision provider when configured.
4. Produce a structured drawing Blueprint and measurement evidence inventory.
5. Keep OCR text, visual-only candidates, derived values, assumptions and user-entered corrections distinguishable.
6. Ask one clear question for each missing or ambiguous engineering decision.
7. Let the user review and correct dimensions with units, source and confirmation state.
8. Generate editable CAD deterministically through build123d/OpenCASCADE.
9. Validate the actual solid and exported mesh against the reviewed specification.
10. Run printability and hardware fit checks with explicit limitations.
11. Show a real interactive 3D preview of the exact generated geometry.
12. After approval, export STEP/STL/3MF/ZIP and dimensional reports.
13. Slice the approved STL with a selected printer/material profile using CuraEngine.
14. Inspect G-code extrusion, bounds, layers and slicer preview before making a print-ready claim.
15. Later, connect approved designs to local print providers with explicit consent.

A valid B-rep, watertight STL, successful HTTP response or green CI is not proof that the model matches the drawing or will print correctly.

## 3. Live architecture

\`\`\`mermaid
flowchart LR
  U["User browser"] --> W["Vercel: Next.js 15 / TypeScript"]
  W --> F["Firebase authentication"]
  W --> DB[("Supabase PostgreSQL / Prisma")]
  W --> B[("Private Vercel Blob")]
  W -->|"server-side service token"| API["Railway: FastAPI / Python"]
  API --> CAD["build123d / OpenCASCADE"]
  API --> OCR["PyMuPDF / Tesseract"]
  API -.->|"optional; server-side policy"| V["Ollama or approved vision provider"]
  API --> SL["CuraEngine"]
  W --> PAY["Razorpay subscriptions"]
\`\`\`

| Layer | Actual implementation | Responsibility |
|---|---|---|
| Web application | \`web/\`, Next.js App Router, TypeScript | User experience, dashboards, project APIs, billing, and server-side service proxying |
| Authentication | Firebase | User authentication and server-side session validation |
| Database | PostgreSQL via Prisma; Supabase is the hosted provider | Users, projects, versions, subscriptions and audit data |
| File storage | Private Vercel Blob | Uploaded drawings and generated model/manufacturing files |
| CAD service | \`python-backend/main.py\`, FastAPI, Railway Docker | Authenticated OCR, drawing generation, text-to-CAD, fit-check, exports and slicing |
| CAD kernel | Python build123d / OpenCASCADE | Deterministic solid construction and geometry validation |
| Drawing extraction | PyMuPDF, Tesseract, Pillow and optional vision adapter | Text, annotations, page rendering and image-read candidates |
| Slicing | CuraEngine and printer/extruder definitions | STL-to-G-code manufacturing path |
| Payments | Razorpay | Pro subscriptions and webhook processing |
| CI/security | GitHub Actions | Python/CAD tests, web lint/typecheck/build, Docker smoke and CodeQL |

### Main service APIs

The current FastAPI service exposes authenticated endpoints including:

- \`GET /health\`
- \`GET /api/v1/fit-check/presets\` and \`POST /api/v1/fit-check\`
- \`POST /api/v1/ocr/extract\`
- \`POST /api/v1/slice\`
- \`POST /api/v1/generate\`
- \`POST /api/v1/text-to-cad\`
- \`POST /api/v1/export\`

The Next.js project APIs include drawing OCR, drawing CAD generation, printability and slicing beneath \`web/src/app/api/projects/[projectId]/\`. Browser clients do not receive CAD service secrets.

## 4. Two distinct CAD contracts

### 4.1 General PartSpec / GeometryEngine

The general feature-based CAD contract lives in:

- \`src/ai3d_designer/core/spec/models.py\`
- \`src/ai3d_designer/core/geometry/engine.py\`

Its \`PrimitiveType\` enum defines box, cylinder, sphere, cone, torus, wedge, extrusion, revolution, loft and sweep. Boolean operations are union, difference and intersection. Parameters carry units and source metadata.

This general engine is not proof that every operation is exposed through every drawing or web workflow.

### 4.2 Drawing Blueprint

The drawing-to-CAD contract lives in:

- \`src/ai3d_designer/drawing_to_cad/blueprint.py\`
- \`src/ai3d_designer/drawing_to_cad/extraction.py\`
- \`src/ai3d_designer/drawing_to_cad/generator.py\`

Current body types: \`rotational_flange\`, \`prismatic_box\`, \`sheet_enclosure\`, \`revolved_profile\`.

Current feature types: \`circular_pattern_cut\`, \`hole_pattern\`, \`radial_cutout_pattern\`, \`ring_step\`, \`through_hole\`, \`pocket\`, \`fillet\`.

This drawing Blueprint is intentionally narrower than the general PartSpec engine. Default height (10 mm) and enclosure wall (2.5 mm) are provisional, flagged and must be confirmed before drawing-generated export. PR #20 records the effective Blueprint used to create the solid.

### 4.3 Sprocket limitation

The dedicated builder is \`src/ai3d_designer/drawing_to_cad/sprocket_cad.py\`. It currently uses circular seat cuts around the pitch circle as a preview approximation. It is **not** an ISO 606 involute chain-sprocket tooth profile. If the 10-tooth C-DAC reference sprocket is an acceptance item, it requires a separate engineering implementation and approved benchmark.

## 5. Verified implementation on current main

- Authenticated web project workflow, Firebase sessions, project versioning, private upload/storage, subscription checks and administration.
- Server-side CAD service proxying and service-token-authenticated FastAPI endpoints.
- General PartSpec/GeometryEngine, conservative text parser, OpenCASCADE solid validation and STEP/STL/other exporter support in the Python package.
- Drawing OCR and typed Blueprint extraction, explicit text-dimension inventory, PDF vector candidates and optional vision adapter.
- Drawing review UI with editable supported Blueprint fields and provisional-default confirmation.
- PR #20 export-provenance correction: effective defaults are retained; missing saved Blueprints cannot silently fall back to free text; exact provisional values require server-side confirmation.
- Axis-aligned hardware fit-check endpoints and dashboard.
- PartSpec-oriented printability checks and project panel. The FastAPI printability router is mounted behind the CAD service-token dependency; authenticated/unauthenticated route tests exist. Issue #11 was closed after verifying this current-main behavior.
- CuraEngine integration and a real Docker smoke slice. Mainline's smoke can still report 0.000 m filament; draft PR #24 adds E-axis deposition parsing and positive-extrusion validation. Issue #8 remains open for this correction, API/upload journey verification, printer profiles and physical print tests.

## 6. Current pull-request baseline

All states below were checked against live GitHub on 8 November 2026. CI results apply only to the tested PR head.

| PR | Purpose | State |
|---|---|---|
| #15 | Accessible 3D-printing product roadmap | Open; documentation-only |
| #18 | Original visual-dimension candidate PR | Closed as stale |
| #20 | Drawing export provenance and confirmation | Merged into 9c8707c... |
| #22 | Semantic dimension-evidence binding | Draft; tested head passed 324 Python tests plus web, Docker and CodeQL |
| #23 | Blueprint-native printability against saved Blueprint | Draft; tested head passed 320 Python tests plus web and CodeQL; its pre-#24 Docker smoke still reported 0.000 m filament |
| #24 | Positive E-axis extrusion/deposition validation | Draft; tested head passed 322 Python tests; test cube measured 0.345410 m and 2,962 deposition moves; web and CodeQL passed |
| #25 | OCR source selection using validated MIME/type | Draft; 316 Python tests, OCR helper test, web, Docker and CodeQL passed |
| #26 | Guided UX wording / advanced engineering mode | Draft; documentation-only; CI passed |
| #27 | Combined Phase 2 visual candidates | Closed as superseded by #29 |
| #29 | Phase 2 visual candidates plus persisted Phase 3 measurement-review ledger | Draft; head ee77ff2...; 327 Python tests, web, Docker/CAD-OCR smoke and both CodeQL scans passed; smoke still reports 0.000 m filament |

PRs #16/#17/#19 are closed as superseded by #23/#24/#25. PRs #18 and #27 are closed as superseded by #29. PR #21 is closed as superseded by #22. PR #20 is merged. PRs #22–#26 and #29 remain unmerged.

## 7. Engineering and data rules

- AI proposes; deterministic code validates.
- Every dimension needs a source, unit and verification state.
- A vision-only candidate is not a CAD parameter. OCR agreement means a value was also recognized by OCR; it does not prove the callout arrow points to the intended feature.
- Editing a confirmed value invalidates its prior confirmation.
- Unsupported geometry is blocked; do not substitute a smooth cylinder/box for a gear, bend, thread or arbitrary profile.
- A photograph without known scale is not an exact engineering drawing.
- Hosted vision remains blocked unless the server-side \`DRAWING_VISION_ALLOW_HOSTED\` switch is explicitly enabled after C-DAC's data-handling decision.
- Free plan: one saved project. Pro: unlimited subject to active-subscription checks. Projects are not automatically deleted.
- No physical printer control or local print-provider ordering is implemented.
- Software checks do not certify strength, fatigue life, material behaviour, tolerance compliance or physical print success.

## 8. Delivery phases and actual gaps

| Phase | Goal | Remaining work |
|---|---|---|
| 0 — Benchmark | Owner-verified reference drawings | Golden set, synthetic cases, accuracy/association/abstention metrics and source/export artifacts |
| 1 — Correctness | Safe drawing export/manufacturing checks | Review/rebase #22–#25; combined CI; drawing-to-solid dimensions/bounds; saved-version end-to-end test |
| 2 — Drawing understanding | OCR + vision + vector evidence | Finish #27; approved private provider test; benchmark views/arrows/feature association; confidence remains uncalibrated |
| 3 — Measurement editor | Provenance-aware review | PR #29 adds persisted reading confirmation/rejection with reviewer/time provenance and immutable OCR. Still required: manual entries, full source/unit/value/tolerance/page/view/region/feature ledger, direct dimension-to-CAD-field binding, image highlighting and confirmation invalidation for geometry edits |
| 4 — Interactive preview | Inspect exact generated model | Real WebGL/mesh viewer, rotate/zoom/pan, dimensions/features, side-by-side drawing and geometry comparison |
| 5 — Printer-aware manufacturing | Reliable slicing | Owner-selected printer/material profiles, layer preview, estimates, physical print records and firmware-specific review |
| 6 — Guided product experience | Accessible user journey | Questions, templates, accessibility/localisation/usability testing; same validated engineering contracts |
| 7 — Local print ecosystem | Local manufacturing access | Vetted providers, consent, quote, privacy/IP/refund policies after design reliability |

## 9. “65 features” clarification

No separate authoritative 65-feature C-DAC acceptance catalogue was found in the current repository or supplied status material. The team execution plan contains task IDs T01–T122; **T65 specifically means the product owner opens the exported STEP in CATIA and records the result**. Section 5.2 contains the target feature-program operation list, not a claim that all such operations are currently supported by the drawing Blueprint.

Do not claim “all 65 features implemented” until Diganta provides/confirms the C-DAC 65-item specification and each item is mapped to code, tests and an acceptance result.

## 10. Product-owner decisions and artifacts required

- Signed C-DAC scope and authoritative acceptance list.
- Whether the ISO 606 sprocket tooth profile is contracted.
- Approved vision-provider/data-handling policy and deployment boundary.
- Golden drawing set: original drawing, intended dimensions, reference STEP/STL and any G-code.
- Printer models, nozzle/extruder, materials and permission for physical print tests.
- IP/licence and deliverable-ownership terms.

## 11. Release status and verification boundary

**Not approved for client release.** No fresh full Production end-to-end run is claimed. No physical print, CATIA open test, drawing-to-mesh accuracy benchmark or customer Version 2 artifact inspection was performed as part of this document update.

Passing CI, successful compilation or file generation is necessary but not sufficient. Release requires owner-reviewed benchmarks, approved scope, current-head CI, Preview journey tests, privacy/IP decisions, printer-specific G-code review and required physical-print evidence.
