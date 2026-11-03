# Beginner-First 3D Printing Product Roadmap

**Repository:** `DIGANTA2006/offline-ai-3d-designer`  
**Product owner:** Diganta Chakraborty  
**Roadmap created:** 3 November 2026  
**Status:** Active — baseline audit completed; first engineering blockers identified  
**Primary deployment:** Vercel (web) + Railway (Python/CAD) + Supabase/PostgreSQL (data)  
**Execution rule:** Work in small, testable branches and pull requests. Do not commit directly to `main` or deploy to Production without the product owner's approval.

---

## 1. Product mission

Make 3D printing usable by ordinary people who do not know CAD, engineering drawing conventions, dimensions, tolerances, mesh formats, slicers, or printer settings.

A user should be able to explain what they need in everyday language, upload a photograph or engineering drawing, or start from a simple template. The application should guide them through understanding the object, checking missing information, reviewing a 3D model, and preparing it for a suitable printer.

**Product promise:** The user explains the need. The application handles the engineering workflow and explains the decisions the user must make.

This is not a promise that every arbitrary image or object can immediately become an accurate printable part. Unsupported or ambiguous designs must be identified honestly and routed to a clarification or expert-review step.

## 2. Target users and product experience

Initial target users include:

- People at home who need a replacement or custom plastic item.
- Local shopkeepers, electricians, mechanics, farmers, and repair workers.
- Students, hobbyists, and first-time 3D-printing users.
- Local 3D-printing service operators who receive designs from non-experts.

The primary experience must be beginner-first. An advanced mode can expose CAD terminology and detailed settings, but it must not be required for the normal user journey.

### Core user journey

1. **Tell us what you need:** upload a drawing/photo, enter a plain-language request, or choose a template.
2. **Understand the input:** extract visible text and dimensions, inspect drawing views, identify features, and show what is known or uncertain.
3. **Ask simple questions:** request one missing decision at a time. Never silently invent a measurement.
4. **Review the design:** show a rotatable 3D model and a plain-language summary with dimensions the user can edit.
5. **Check printability:** use the user's printer/material profile when known; clearly label generic assumptions otherwise.
6. **Prepare the print:** slice the approved model, validate G-code and show a layer/toolpath preview.
7. **Get the object made:** initially download files; later, connect the user to a local print provider.

### Product principles

- **Evidence before confidence:** every engineering value must have a source, unit, and verification state.
- **Ask, do not guess:** unknown values remain unknown until supplied or explicitly accepted as assumptions.
- **Show the model:** a successful STEP/STL export is not proof that the design matches the drawing.
- **Explain in ordinary language:** introduce technical terms only when useful, with an explanation.
- **Separate design from manufacturing approval:** software checks do not certify strength, material suitability, printer compatibility, or physical success.
- **Privacy by default:** drawings are private. Do not send drawings to a hosted AI provider unless the owner has deliberately enabled and approved that data flow.
- **Human approval:** no physical printing, paid local-service order, or external sharing without explicit user approval.

---

## 3. Current baseline (audited against `main` on 3 November 2026)

### Existing capabilities to preserve

- Private drawing upload and authenticated project storage.
- Tesseract/PyMuPDF text extraction and a structured drawing blueprint.
- Optional vision-model adapter that receives rendered drawing images and a structured schema.
- Dimension grounding, blueprint review/editing, and a deterministic build123d/OpenCASCADE generator for a limited feature set.
- STEP/STL export with solid validity, positive-volume, and watertight-STL checks.
- CuraEngine slicing through the Railway backend, plus the printability API and project panel.
- Vercel, Railway, and Supabase/PostgreSQL deployment separation.

Do not rebuild these systems wholesale. Extend them behind tested contracts and preserve existing retention, authentication, subscription, private-storage, and Preview/Production isolation rules.

### Known limitations and live-test evidence

The following was observed in the product owner's live test on 3 November 2026:

1. A 54 KB JPEG uploaded successfully after being given a `.jpg` extension.
2. The OCR panel reported **28% OCR word confidence**, with no recognized dimension triplets, diameters/radii, tolerances/fits, or material/finish values.
3. The blueprint panel reported **no vision model configured/reported**, an unresolved body type, no machinable features, and a positive-thickness warning.
4. A Version 2 STEP and STL export was nevertheless saved. This proves only that files were produced; the original drawing and exported mesh have not yet been compared.
5. The new Printability Checks panel rejected Version 2 with: **“This project version does not contain a supported, saved PartSpec.”**
6. CuraEngine reported ready and returned a G-code download with 1 h 51 m, 98 layers, 0.000 m filament length, and no filament mass.
7. The PR #16 CI Docker smoke test also produced a 98-layer, 160,857-byte G-code file but reported 0.000 m filament and no grams. This demonstrates that the old smoke gate and old absolute-E check were insufficient to prove real positive filament deposition. It does not, by itself, prove that the physical G-code contained no E-axis extrusion; the downloaded G-code must be measured.

Additional code-level findings:

- The drawing generator stores a drawing `Blueprint` object in project version data, with fields such as `part_name`, `primary_body_type`, `base_sketch`, and drawing features.
- Before PR #16, the printability route only accepted the separate canonical `PartSpec` (`name` and canonical `features`). PR #16 adds a dedicated blueprint-native check endpoint and preserves the distinction between the two schemas.
- The drawing reader supports an optional vision provider, but production's live UI reported none configured. Hosted vision calls are blocked by default unless `DRAWING_VISION_ALLOW_HOSTED=true`; keep that privacy protection.
- The current project detail page exposes STEP/STL downloads and slicing; it does not yet provide a verified interactive preview of the drawing-generated mesh.
- Before PR #17, G-code validation treated a positive absolute E coordinate as an extrusion indicator and trusted Cura filament comments. PR #17 computes E-axis deltas and reports measured filament length when possible. The user's downloaded G-code artifact still needs direct inspection.
- Upload/OCR extension and format support should be made consistent. The current uploader, stored MIME metadata, and drawing panel's extension filter do not advertise exactly the same set of formats.

**Important:** The 3D source image, generated Version 2 STL/STEP, and downloaded G-code have not yet been independently inspected in this repository review. Do not mark drawing accuracy or physical print-readiness as passed until those artifacts are compared.

---

## 4. Roadmap and release gates

The phases are ordered by dependency. A phase is complete only when its exit gate passes; a merged feature or green deployment alone is not enough.

### Phase 0 — Establish a trustworthy benchmark and operating process

**Goal:** Make improvements measurable and reproducible.

- [x] Audit current OCR, blueprint, CAD, printability, and slicing paths.
- [x] Record the first live-test failures and limitations in this roadmap.
- [ ] Obtain and preserve an approved test bundle: original drawing image, generated STEP/STL, and corresponding G-code.
- [ ] Build a small initial golden set of representative drawings: simple flange/plate, rectangular part, enclosure, hole pattern, pocket/slot, and at least one intentionally unsupported part.
- [ ] For each golden drawing, record owner-verified dimensions, units, feature list, expected unsupported items, and expected model bounds.
- [ ] Add deterministic synthetic drawings from known CAD models; use them to measure extraction and geometry accuracy.
- [ ] Extend the benchmark over time in line with the B2 drawing-to-program benchmark in `Offline_AI3D_TEAM_EXECUTION_PLAN.md`.

**Exit gate:** every test drawing has a known reference specification and a repeatable test procedure. Test data is either synthetic or supplied with permission.

### Phase 1 — Fix correctness and cross-service contracts (highest priority)

**Goal:** Never call an export successful when required geometry is unresolved, and ensure a successfully generated drawing model can be checked by the printability system.

- [x] Define a versioned API boundary for the reviewed drawing Blueprint and provide a blueprint-native printability path; PR #16 adds `/api/v1/printability/check-blueprint` rather than relabelling Blueprint fields as the legacy canonical `PartSpec`.
- [ ] Persist the original reviewed blueprint separately from the normalized canonical geometry specification. Preserve measurement provenance and generation warnings.
- [ ] Add regression tests for drawing-generated versions passing the printability endpoint, including supported flange, box/enclosure, and hole-feature examples.
- [ ] Reject unresolved body types, missing required dimensions, unresolved unsupported geometry, and invalid defaults before export. If a default is deliberately allowed, show it as an assumption and require user confirmation.
- [ ] Verify the generated solid's bounding box and key feature dimensions against the reviewed specification, not only kernel validity and watertightness.
- [x] Require real positive extrusion movement using absolute/relative E-axis deltas, G92 resets, tool selection and volumetric E conversion; PR #17 adds regression tests. This is an extrusion validator, not a complete firmware-specific G-code simulator.
- [x] Reconcile CuraEngine metadata with measured G-code E-axis movement. Zero metadata is not treated as a real estimate; a slice with no positive extrusion on an XYZ print move is rejected. PR #17 strengthens the real Docker smoke test.
- [ ] Add route/API regression tests for the real drawing-to-CAD → saved version → printability → slice flow.
- [x] Preserve the existing authentication, ownership, Pro policy, same-origin, service-token, request/response limits, and no-store controls on the web route; PR #16 keeps drawing-blueprint checks on the existing authenticated route.

**Exit gate:** still open. PR #16 makes supported saved drawing blueprints consumable by geometry-based printability checks, and PR #17 rejects G-code without genuine extrusion. Broader stored-provenance, export-blocking, bounding-box/feature-dimension, and full drawing-to-print end-to-end coverage remain incomplete.


### CI verification for the first corrective PRs (3 November 2026)

- **PR #16 — drawing Blueprint printability contract:** GitHub Python tests (317 passed, 2 warnings), Web Frontend Checks, Docker/CuraEngine image build, both CodeQL language scans, and Vercel Preview status succeeded. The PR remains open for product-owner review.
- **PR #17 — G-code extrusion validation:** GitHub Python tests (321 passed, 2 warnings), Web Frontend Checks, Docker/CuraEngine image build, both CodeQL language scans, and Vercel Preview status succeeded. The real Docker smoke test sliced a deterministic 10 mm cube and measured 345.410 mm of E-axis filament movement (0.345410 m), with 2,962 positive-extrusion print moves, 98 layers, and a 6,666-second Cura estimate. Filament mass remains unreported. This verifies measurable extrusion in the test cube's G-code, not a full printer-firmware simulation or physical print. The PR remains open for product-owner review.

### Phase 2 — Multimodal engineering drawing reader

**Goal:** Understand the drawing image as a drawing, not merely extract its text.

**Execution update — 3 November 2026:** Draft PR #18 adds typed image-read measurement candidates, instructs the vision model to inspect image pixels independently of OCR, reconciles candidate values against OCR evidence without trusting model-supplied verification, and displays candidates in the drawing review UI. Its Python regression, Docker/CuraEngine, frontend and CodeQL checks are still being verified. This is an initial implementation slice, not completion of Phase 2. The live Railway service has not yet reported an approved vision provider, so actual image-read results still require an explicit provider/data-handling decision and a live test.

- [ ] Keep OCR for text recognition, but add visual analysis of the rendered page: view detection, dimension arrows/extension lines, leader lines, symbols, geometry candidates, section views, and repeated-feature counts.
- [ ] Combine OCR text, PDF-native text/vector evidence, and vision output. No single model response should be treated as ground truth.
- [ ] Associate each candidate measurement with a name, value, unit, tolerance (when present), feature, source page/view, image coordinates or crop, extraction method, and confidence.
- [ ] Distinguish a measured value from a derived value, an assumption, and a user-entered correction. For example, a PCD is a diameter; a derived pitch radius must be labelled as calculated.
- [ ] Link dimensions to features only when evidence supports the relationship. If a callout could refer to multiple features, ask the user.
- [ ] Detect and report unreadable, conflicting, missing, and unsupported information. Do not fill unknown values with a vision-model guess.
- [ ] Improve image preprocessing (orientation, resolution, contrast, noise and page crops) while retaining a path back to the original page.
- [ ] Add clear service readiness/diagnostics for OCR and vision separately. The UI must state whether a vision model actually ran, which model/provider was used, and whether fallback mode was used.
- [ ] Keep the vision provider pluggable (private/reachable Ollama or approved OpenAI-compatible endpoint). Do not require a specific paid provider. Do not enable hosted drawing transfer without an explicit owner data-handling decision.

**Exit gate:** the benchmark reports dimension precision/recall, value accuracy, feature-association accuracy, abstention quality, and hallucination rate. Uncertain values are visibly uncertain; no ungrounded dimension is silently accepted.

### Phase 3 — Beginner-friendly measurement and feature editor

**Goal:** Let a non-engineer correct and complete a design without learning CAD terminology first.

- [ ] Show a measurement ledger with friendly labels, values, units, source, confidence, and confirmation state.
- [ ] Provide direct controls to add, rename, edit, and remove a measurement or feature.
- [ ] Explain common features using simple descriptions and optional illustrated help: hole, slot, pocket, wall, boss, groove, chamfer, fillet, pattern, and enclosure.
- [ ] Ask one missing question at a time. Offer simple choices and show why the answer is needed.
- [ ] Show the original drawing beside the interpreted blueprint and allow a user to select a measurement to highlight its source location.
- [ ] Separate measured, derived, defaulted, and manually entered values in both UI and stored data.
- [ ] Make unit conversion explicit and never silently reinterpret inches, mm, cm, or degrees.
- [ ] Keep an Advanced Mode for experienced users without making it the default.

**Exit gate:** a first-time user can review and correct a supported test part using the guided interface, and the final approved values are stored with provenance.

### Phase 4 — Real 3D model preview and drawing comparison

**Goal:** Users can see and inspect what the application actually built before slicing.

- [ ] Generate or derive a browser-friendly preview artifact (for example, GLB) from the exact validated solid/mesh used for exports.
- [ ] Add an interactive 3D viewer with rotate, pan, zoom, reset, and basic dimension/bounds display.
- [ ] Show the original 2D drawing and the 3D preview side by side.
- [ ] Display feature and dimension annotations in the preview where mapping is available.
- [ ] Compare expected and actual bounding box, key holes, pattern counts, thicknesses, and other known reference measurements.
- [ ] Make changes produce a new proposal/version; do not silently overwrite the last approved STEP/STL.
- [ ] Label approximations and unsupported or hidden geometry explicitly.

**Exit gate:** every supported benchmark model can be visually inspected and its key dimensions checked against the golden specification before it is approved for slicing.

### Phase 5 — Printer-aware printability and slicing

**Goal:** Prepare real, inspectable toolpaths for a known printer/material setup.

- [ ] Introduce explicit printer and material selection. Store manufacturer/model/build volume/nozzle diameter/filament type and source of each profile value.
- [ ] Clearly distinguish generic advice from printer-specific profile validation.
- [ ] Run printability checks on the same canonical geometry that generated the STEP/STL.
- [ ] Map each warning to a plain-language explanation, severity, affected feature, and safe next action.
- [ ] Clearly label actions that are recommendations only versus actions that alter geometry or slicer settings.
- [ ] Validate G-code with robust handling of absolute/relative extrusion, retraction, coordinate modes, layer markers, temperature commands, and tool changes.
- [ ] Verify non-zero actual extrusion, plausible model/toolpath extents, and layer count before returning G-code.
- [ ] Show layer-by-layer toolpath preview, estimated time, filament length/weight and their provenance. Never display zero or missing metadata as a successful estimate.
- [ ] Keep physical printer connection disabled until printer-specific safety, authentication, cancellation, and operator-confirmation requirements are implemented.

**Exit gate:** a known printer profile and representative material produce valid G-code with real extrusion moves; a slicer preview is visually reviewed; the estimate agrees within a documented tolerance with the slicer's output.

### Phase 6 — Beginner product experience and accessibility

**Goal:** Make the whole workflow understandable to people who do not know 3D printing.

- [ ] Replace technical-first navigation with a guided "What would you like to make?" entry point.
- [ ] Add guided routes for a drawing, a photo/idea, an existing STL, and a template.
- [ ] Explain STL, STEP, slicing, infill, supports, layer height, wall thickness and material only when relevant.
- [ ] Give safe beginner defaults with a clear explanation and an easy way to override them.
- [ ] Add responsive/mobile-friendly upload, preview, review, and download experiences.
- [ ] Add accessible labels, keyboard support, readable contrast, clear errors, and progress states.
- [ ] Evaluate localized language support for the first target users; do not translate engineering values or units ambiguously.
- [ ] Add a clear "I need help" path and a way to share a review package with a trusted technician when the part is unsupported.

**Exit gate:** usability tests with first-time users show they can complete a supported task, understand what is uncertain, and identify when expert help is required.

### Phase 7 — Local 3D printing access network (later, after design reliability)

**Goal:** Help users who do not own a printer get their approved object manufactured locally.

- [ ] Explore a directory of local print providers and printer capabilities.
- [ ] Let users share an approved design package and request a quote only with explicit consent.
- [ ] Match material, build volume, quality, location, price and delivery options.
- [ ] Provide clear ownership, design privacy, deletion, payment, refund, and dispute rules before taking orders.
- [ ] Keep provider vetting and manufacturing responsibility explicit; the platform must not imply a provider has validated a design unless they have.

**Exit gate:** pilot with a small number of vetted providers and real user-approved jobs; privacy and commercial policies reviewed before public launch.

---

## 5. Quality gates and measurable outcomes

Do not use "file generated" as the main success metric. Track the following for every release:

| Area | Required evidence |
|---|---|
| Input | File type/content validation; source file preserved privately |
| OCR | Recognized text with confidence and page provenance |
| Visual understanding | Identified views/features with evidence and abstention where uncertain |
| Dimensions | Named value + unit + tolerance + source + confidence + confirmation |
| Blueprint | Schema-valid, fully reviewed, no unresolved blockers |
| CAD | Kernel-valid solid, expected solid count, positive volume, expected dimensions |
| Mesh | Non-empty, valid, watertight STL; bounds agree with expected dimensions |
| Preview | Same geometry as the export; visually reviewed against the drawing |
| Printability | Checks use the exact saved canonical specification and printer profile |
| Slicing | Genuine extrusion, plausible layer/toolpath bounds, valid metadata |
| User outcome | First-time user understands and approves the design before export/order |

### Non-negotiable acceptance rules

1. A vision model's output is a proposal, not truth.
2. A dimension is not accepted as drawing-derived unless its evidence and unit are retained.
3. An assumed/default dimension must be labelled and confirmed before it can affect a final user-approved export.
4. Unsupported geometry must block simplified substitution.
5. A valid solid or watertight STL does not prove that the drawing was interpreted correctly.
6. A green CI job or cloud deployment does not prove the live user journey works.
7. A successful G-code HTTP response does not prove a usable physical print.
8. Physical-print or strength claims require independent tests; they are never inferred from software checks.

---

## 6. Execution order for the team

Work one milestone at a time, in dependency order:

1. Phase 0 benchmark and test artifacts.
2. Phase 1 geometry/PartSpec and G-code correctness blockers.
3. Phase 2 multimodal drawing understanding.
4. Phase 3 measurement/feature editor.
5. Phase 4 interactive 3D preview and comparison.
6. Phase 5 printer-aware checks and verified slicing.
7. Phase 6 beginner-first product usability.
8. Phase 7 local print-provider network.

If implementation evidence shows a dependency is wrong, update this document in a PR and explain the reason. Do not skip an exit gate because a demo appears to work.

### Branch, testing and release policy

- Create a dedicated branch for each milestone or tightly related task.
- Make a backup before local file modifications when working on the owner's Windows checkout.
- Keep Developer 1's Python/CAD work and Developer 2's Next.js/platform work separated when practical; integrate through explicit API contracts.
- Add regression tests with every bug fix. Add benchmark cases with every new supported geometry feature.
- Use GitHub Actions for Linux Docker/CuraEngine image builds and CI. The product owner's Windows machine does not need Docker Desktop or a Linux distribution for hosted deployment testing.
- Use Railway and Vercel Preview deployments for isolated end-to-end tests. Keep Preview services, tokens, database and storage isolated from Production.
- Never place secrets in Git, browser code, logs, screenshots, or this plan.
- Do not apply database migrations to Production or change Production environment variables without explicit approval.
- Do not merge to `main`, delete user projects, or trigger a Production deployment without explicit approval from the product owner.
- Keep the roadmap checkboxes and `WORK_STATUS.md` current as work is completed.

---

## 7. Immediate next actions

**Current active milestone: Phase 0 → Phase 1.**

- [x] Review the current `main` architecture and existing execution plan.
- [x] Record the first live OCR/CAD/slicing test results.
- [x] Identify the blueprint-versus-canonical-PartSpec contract mismatch in the printability path.
- [ ] Obtain the original JPEG, Version 2 STEP/STL, and Version 2 G-code for independent inspection.
- [x] Reproduce the saved-PartSpec rejection and add a regression test for the drawing-blueprint printability route (PR #16).
- [x] Implement and test the explicit drawing-blueprint-to-printability contract (PR #16; open for owner review).
- [ ] Add a guard so unresolved/invalid drawings cannot produce a misleading successful export.
- [ ] Inspect the downloaded user G-code artifact and compare its actual E-axis moves with Cura metadata.
- [x] Validate absolute/relative/volumetric E-axis semantics and make the Docker smoke fail when deposition or filament length is zero (PR #17; CI passed, open for owner review).
- [ ] Only after these correctness gates pass, proceed to the visual-reader provider setup and drawing-understanding benchmark.

**Current release decision:** the application is deployed and its services respond, but the drawing-to-model workflow is **not accepted as production-quality** yet. The 3D accuracy, printability integration, and zero-filament G-code report remain open verification items.
