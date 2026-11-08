# Offline AI 3D Designer — Project Architecture, Status and Delivery

**Document date:** 8 November 2026  
**Product:** Offline AI 3D Designer  
**Client:** C-DAC Kolkata  
**Product owner / architect:** Diganta Chakraborty  
**Repository:** \`DIGANTA2006/offline-ai-3d-designer\` — Private  
**Default branch:** \`main\`  
**Verified main:** \`06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80\`  
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
- Blueprint-native printability endpoint and UI from merged PR #23.
- Positive E-axis extrusion/deposition parsing and validation from merged PR #24.
- MIME-aware OCR source selection from merged PR #25.
- Visual measurement candidates and persisted review-decision sidecar from merged PR #29. Confirming a reading remains distinct from binding it to a CAD parameter.
- Latest mainline CI: 337 Python tests passed (2 warnings); web lint/typecheck/production build, both CodeQL analyses and Docker CAD/OCR runtime smoke passed.
- Latest real CuraEngine smoke: 160,857-byte G-code, 98 layers, reported print time 6,666 seconds, E-axis filament length 0.345410 m and 2,962 deposition moves. Filament mass is not measured.

## 6. Current pull-request baseline

Current main at this audit is `06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80`. The following PRs are merged:

| PR | Purpose | State |
|---|---|---|
| #20 | Drawing export provenance and provisional-dimension confirmation | Merged |
| #23 | Blueprint-native printability | Merged |
| #24 | Positive E-axis extrusion/deposition validation | Merged |
| #25 | OCR source selection using validated MIME/type | Merged |
| #26 | Guided UX / advanced engineering scope wording | Merged |
| #28 | Architecture/status documentation | Merged; original PR-status snapshot was superseded after subsequent same-day merges |
| #29 | Visual measurement candidates and persisted review ledger | Merged |

Open PRs at the audit:
- #15 — accessible 3D-printing roadmap; documentation-only and diverged from current main (11 commits ahead / 29 behind at audit). Refresh before relying on its status data.
- #22 — semantic dimension evidence; diverged from current main (3 commits ahead / 18 behind at audit) and overlaps extraction/docs/tests changed by #29. Do not merge wholesale; selectively port only verified missing hunks after a full diff review.

All PR CI evidence applies only to its specific tested head SHA. Latest mainline verification and submission gaps are recorded in `docs/CLIENT_SUBMISSION_READINESS_2026-11-08.md`.

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
| 0 — Benchmark | Owner-verified reference drawings | Approved golden set, expected dimensions/features/reference STEP/STL, accuracy/association/abstention metrics |
| 1 — Correctness | Safe drawing/manufacturing workflow | Current mainline end-to-end journey, saved-version/mesh comparison, export/API/upload verification |
| 2 — Drawing understanding | OCR + vision + vector evidence | Approved provider/data policy; benchmark views, arrows and feature association; calibrated confidence and multi-page cases |
| 3 — Measurement editor | Provenance-aware review | PR #29 persists transcription decisions; still required: manual entries, source-region highlighting, tolerance/GD&T, direct CAD-parameter association and confirmation invalidation on geometry changes |
| 4 — Interactive preview | Inspect exact generated model | Production web mesh viewer, rotate/zoom/pan, dimensions/features, drawing/model comparison and version identity |
| 5 — Printer-aware manufacturing | Reliable slicing | Selected printer/material profiles, layer/toolpath preview, filament-mass methodology, G-code review and physical print records |
| 6 — Guided product experience | Accessible user journey | Questions/templates plus accessibility, localisation and non-technical user acceptance; same engineering contracts |
| 7 — Local print ecosystem | Local manufacturing access | Vetted providers, consent, quotes, IP/privacy/refund policy and order fulfilment if included in contract |

See the [Client Submission Readiness and Verified Gap Register](CLIENT_SUBMISSION_READINESS_2026-11-08.md) for owners, risks, required artifacts and ordered gates.

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

**Not yet evidenced as accepted for client production release.** Latest mainline automated checks pass, but no approved golden drawing accuracy report, full production user-journey record, CATIA open-test record, physical print record, printer-specific acceptance or signed C-DAC acceptance matrix is present in this repository baseline.

Passing CI, successful compilation, a generated solid or valid G-code is necessary but not sufficient. Release requires signed scope, owner-reviewed benchmarks, privacy/deployment decisions, current-head CI, staging E2E/UAT, CATIA and printer evidence where contracted, and written client acceptance or documented deviations.

This status snapshot is dated 8 November 2026 and must be refreshed after material merges or new acceptance evidence.