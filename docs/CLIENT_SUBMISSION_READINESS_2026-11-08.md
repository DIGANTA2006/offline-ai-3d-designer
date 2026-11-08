# C-DAC Client Submission Readiness and Verified Gap Register

**Assessment date:** 8 November 2026  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Baseline:** `main` at `06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80`  
**Purpose:** Internal engineering control document for product-owner review and client-submission planning.  
**Release status:** **Not yet evidenced as a production acceptance candidate. This document is not a release certificate.**

## 1. Executive decision

The repository has a substantial working foundation and the latest mainline CI is green. That is not the same as completion of the contracted C-DAC product.

Do not describe the system as fully production-ready, fully offline, accurate for arbitrary engineering drawings, certified for arbitrary mechanical parts, or accepted for physical manufacturing until the relevant gates in this register have evidence and owner approval.

A limited technical-progress demonstration may be possible if it is explicitly described as a supported-scope demonstration and uses non-confidential or approved test drawings. It must not be presented as final acceptance.

## 2. Verified repository baseline

### 2.1 Current main

- Main SHA: `06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80`.
- Latest main commit: merge of PR #26.
- The latest mainline run completed successfully:
  - Python CAD/mesh regression: **337 passed, 2 warnings**.
  - Web lint, typecheck and production build: passed.
  - CodeQL Python: passed.
  - CodeQL JavaScript/TypeScript: passed.
  - Docker CAD/OCR runtime smoke: passed.
  - Real CuraEngine smoke: 160,857-byte G-code, 98 layers, 6,666-second reported time, 0.345410 m E-axis filament length, 2,962 deposition moves.
- The smoke does not report measured filament mass: `filament_grams=None`; mass is not a verified result.
- GitHub Vercel and Railway commit status contexts are successful for the recorded main SHA. These status contexts are not a substitute for an end-to-end production user-journey test.

### 2.2 Relevant merged pull requests

| PR | Merged work | What the merge proves |
|---|---|---|
| #20 | Drawing export provenance and provisional-dimension confirmation | Saved/effective Blueprint provenance and guarded confirmation path were added |
| #23 | Blueprint-native printability | Saved drawing Blueprints can be sent through the supported printability path |
| #24 | Positive G-code extrusion validation | The validator can measure positive E-axis extrusion and reject zero-deposition output in the tested path |
| #25 | MIME-aware OCR input selection | Validated upload MIME/type metadata is used for OCR source selection |
| #26 | Engineering-grade guided UX wording | Documentation now states that guided UX cannot reduce engineering requirements |
| #28 | Architecture/status document | Architecture and status snapshot was added; **its PR table and main SHA became stale after later same-day merges** |
| #29 | Visual measurement candidates and persisted review ledger | Review decisions can be persisted without overwriting the original OCR evidence or silently changing CAD geometry |

Merged PRs are implementation increments, not whole-system acceptance. The current `WORK_STATUS.md` and `PROJECT_ARCHITECTURE_STATUS_2026-11-08.md` contain pre-merge PR/mainline statements and must be refreshed. This register supersedes their historical PR-status tables until corrected.

### 2.3 Remaining open PRs

| PR | Current disposition |
|---|---|
| #22 semantic callout evidence | Open, diverged from current main (3 commits ahead / 18 behind at assessment). It touches drawing extraction/tests/docs already changed by merged #29. Do not merge the branch wholesale. Compare the exact remaining hunks and selectively port only demonstrably missing fixes, then test the resulting main-based branch. |
| #15 accessible 3D-printing roadmap | Open, documentation-only, diverged (11 ahead / 29 behind at assessment). Refresh its content against current main before accepting it. Its old branch must not replace current status information. |

Older PRs closed as superseded are not separate completed product capabilities. Their successor work is represented by the merged PRs above.

## 3. Product contracts that must not be conflated

The repository has two different modeling contracts:

1. General `PartSpec` / `GeometryEngine` for text-to-CAD and supported general geometry.
2. Drawing-specific `Blueprint` / `drawing_to_cad` for the structured drawing workflow.

The drawing Blueprint is materially narrower than the general engine. Its current body types are:

- `rotational_flange`
- `prismatic_box`
- `sheet_enclosure`
- `revolved_profile`

Its current feature types are:

- `circular_pattern_cut`
- `hole_pattern`
- `radial_cutout_pattern`
- `ring_step`
- `through_hole`
- `pocket`
- `fillet`

The application must refuse unsupported geometry rather than substitute a simpler part. A successful CAD build, valid B-rep, single solid or watertight STL does not establish that the generated part matches the engineering drawing.

## 4. Production-readiness gap register

Status meanings:

- **Implemented — CI verified:** a defined code path exists and relevant automated tests pass; this does not mean client acceptance.
- **Partial:** useful implementation exists, but material acceptance requirements remain.
- **Not evidenced:** the repository does not contain the required end-to-end or customer acceptance artifact.
- **Owner decision required:** implementation cannot safely be finalized without a client/product-owner decision.

| ID | Workstream | Verified current state | Remaining gap / risk | Required acceptance evidence |
|---|---|---|---|---|
| G0 | Contract and C-DAC scope | Team execution plan T01–T123 exists. | The separately referenced C-DAC 65-item acceptance catalogue was not found in the repository or supplied status material. Do not infer its contents. T65 in the execution plan means opening the STEP output in CATIA and recording the result; it is not a 65-feature implementation count. | Signed/versioned scope, exact acceptance item list, exclusions, inputs, outputs, tolerances, responsibilities, acceptance process and milestone/payment terms. Map every line to implementation, test and evidence. |
| G1 | Data privacy and offline boundary | Private repository/storage and a server-side vision adapter exist. Hosted vision requires configuration. | No recorded C-DAC decision confirming which providers may receive drawings, approved hosting/data-residency boundary, retention and backup policy. The presence of an “offline” product name does not prove the complete web/cloud/CAD/AI stack works disconnected from the internet. | Written data-handling decision; approved deployment topology; documented offline mode boundary; retention/deletion test; threat/security review. Do not upload client-confidential drawings to an unapproved provider. |
| G2 | Drawing ingestion and OCR | PDF/raster processing, Tesseract/PyMuPDF, text dimension inventory, MIME-aware input selection and optional vision adapter exist. | Accuracy on real C-DAC drawings is not measured. OCR symbol/digit ambiguity, multi-view association, scanned drawings and complex multi-page inputs need a representative benchmark. Vision confidence is explicitly uncalibrated. | Golden drawing corpus approved by C-DAC; expected OCR tokens and dimensions; per-drawing precision/recall or agreed accuracy metrics; abstention/error analysis; repeatable benchmark report. |
| G3 | Measurement evidence and review | Visual candidates and a persisted confirm/reject ledger exist. Original OCR evidence is preserved with reviewer and timestamp provenance. | Confirming a reading confirms transcription only. It does not establish arrow/extension-line association, view association, or bind the value to a CAD parameter. Manual measurements, full tolerance/GD&T ledger, region overlay and geometry-change invalidation remain incomplete. | Reviewer can inspect source region and units, correct/add a value, bind it to a named feature/parameter, see provenance, and re-confirm after dependent geometry changes. Automated tests plus recorded user acceptance. |
| G4 | Drawing-to-CAD accuracy | Deterministic generator supports four body types and seven feature types; unsupported geometry can block export. | No measured drawing-to-solid accuracy benchmark or complete dimension/bounds comparison against owner-approved reference models. A generated valid solid may still be the wrong part. | Golden drawing → expected Blueprint/parameters → generated STEP/STL → measured dimensions/bounds/feature comparison, with tolerances set by C-DAC and signed results. |
| G5 | Feature coverage | The drawing Blueprint supports the v1 list in section 3. General PartSpec engine supports a broader but different vocabulary. | The complete contracted operation list is unknown. Threads, arbitrary freeform geometry, many chamfers/countersinks, sheet-metal bends/flanges, multi-body assemblies and unsupported profiles are not comprehensively implemented in the drawing pipeline. | Item-by-item acceptance matrix against the authoritative client list. Each operation requires schema, deterministic generator, invalid-input tests, geometry regression, export validation and example artifact. |
| G6 | Sprocket/gear geometry | A dedicated sprocket builder and spec exist. | Current tooth-seat pattern is a circular-cut preview approximation, not an ISO 606 involute chain-sprocket tooth profile. It must not be presented as engagement-certified. | Confirm whether sprocket is in contracted scope. If required, implement the specified standard/profile and validate pitch, tooth form, roller engagement and reference dimensions against approved engineering data. Otherwise clearly exclude/block certified export. |
| G7 | Hardware fit check | Protected endpoint/UI, dimension confirmation, initial presets and axis-aligned clearance calculation exist. | This is not general 3D collision/interference analysis. Rotated/arbitrary placement, full keep-out volumes, cable/port access, thermal/structural checks and datasheet verification are not complete. Presets are revision-sensitive. | Approved component catalogue with exact manufacturer/revision/datasheet source; tested clearances; rotation/keep-out requirements; explicit limitations and pass/fail examples. |
| G8 | Printability | Printability checker implements several geometry heuristics, including wall/hole/overhang/bed/bridge/base-contact checks. Blueprint-native route was added. | Generic FDM thresholds and a default 220×220×250 mm bed are not printer/material certification. Some Blueprint/profile cases are explicitly not evaluable. Software checks do not prove material strength, fatigue, tolerance or real print success. | Selected printer/material/nozzle profiles, calibrated limits, supported geometry coverage, known-negative and known-positive corpus, explanation/fix regression and accepted limitations. |
| G9 | Slicing and G-code | CuraEngine Docker smoke uses real STL-to-G-code; positive E-axis deposition is parsed and zero-deposition output rejected in the tested path. | Current smoke uses generic definitions. No C-DAC-selected physical printer profiles are evidenced. Filament grams are not measured in the current successful smoke. Layer preview, firmware review and uploaded-STL end-to-end evidence require further verification. | Two selected printer profiles from manuals; profile-specific real slices; G-code bounds/extrusion/temperature/motion checks; upload-route/API test; customer G-code review; physical print records. |
| G10 | Interactive 3D inspection | STEP/STL/other export code exists; drawing and printability panels exist. | No production WebGL viewer for the exact generated mesh was found in the current web project component tree/package manifest during this audit. Dimension/feature selection and side-by-side drawing/model inspection are not evidenced. | Web viewer renders the saved version's exact geometry; rotate/zoom/pan; unit-aware dimension/feature panel; drawing overlay/comparison; export-version identity and browser performance/accessibility tests. |
| G11 | Export interoperability | Python exporter has STEP, STL, 3MF, report and ZIP-related functions. Drawing generation records STEP/STL artifacts. | Function existence is not proof all formats work end-to-end from the authenticated web workflow. No CATIA import/open acceptance artifact was found. | Authenticated generate → persist → download for every contracted format; file validation; open STEP in CATIA and STL/3MF in agreed slicer; screenshots/logs and sample files retained. |
| G12 | Full product journey | Authentication, private storage, subscriptions, project versioning, APIs and CI exist. | No fresh recorded end-to-end run covers sign-in → upload → OCR → manual review → CAD → version save → viewer → printability → slice → G-code review → download, including negative/auth/quota/error paths. | Repeatable staging E2E suite plus human-run UAT script on a clean account and approved sample drawings. Capture traces, screenshots and outputs. |
| G13 | Operations and security | CI/CodeQL, service-token boundary, authenticated project routes and deployment configuration exist. | Main success statuses do not prove monitoring, rate limits, backup/restore, dependency lock/reproducibility, data residency or external security review. | Threat model, secrets/config audit, access-control tests, rate limits, SBOM/dependency review, monitoring/alert test, tested backup/restore, incident and recovery runbook. |
| G14 | Customer acceptance and handover | Team plan defines phased gates and deliverable documentation. | No signed gate decisions, CATIA report, physical print record, representative non-technical user test or final handover acceptance is evidenced here. | C-DAC witness/demo record, acceptance matrix with pass/fail/deviation, user guide, admin/deployment/restore guide, known-limitations register, ownership/licence and handover sign-off. |
| G15 | Local printing ecosystem | Product direction includes access to local printing. | Vetted provider discovery, quotes, order workflow, consent, IP/privacy/refund terms and manufacturing delivery tracking are not implemented. | Treat as a separately scoped later phase unless explicitly required for current contract. |

## 5. Work classification: what is usable now versus incomplete

### Usable engineering foundation

- Authenticated project/web platform and private file storage.
- Python FastAPI CAD service with build123d/OpenCASCADE.
- Conservative text-to-CAD path for supported primitives/features.
- Structured drawing Blueprint path for the limited v1 bodies/features listed above.
- Drawing OCR, MIME-aware source selection, OCR inventory and optional image-read candidates.
- Guarded provisional defaults and persisted review decisions.
- PartSpec printability checks and a Blueprint-native printability route.
- Hardware fit check for supported axis-aligned dimensional comparisons.
- Real CuraEngine Docker slicing smoke and positive E-axis extrusion validation.
- STEP/STL and additional exporter functions in the Python package.
- Automated regression, web build and CodeQL workflows.

### Still partial / not production-accepted

- Arbitrary/complex engineering drawing understanding.
- Calibrated model accuracy and dimension-to-feature association.
- Complete dimension/tolerance/GD&T editor and direct CAD parameter binding.
- Broad mechanical feature coverage and ISO 606 sprocket tooth geometry.
- Full 3D fit/interference analysis.
- Printer/material-specific printability and slicing acceptance.
- Complete interactive web viewer.
- Full authenticated browser end-to-end and customer UAT evidence.
- CATIA interoperability and physical print evidence.
- Approved deployment/privacy/offline architecture and operations evidence.
- Complete C-DAC acceptance mapping and signed handover.

## 6. Required submission gates (order of execution)

Do not skip a gate because a later component looks visually complete.

### Gate A — Freeze contractual scope before more feature coding

1. Obtain the authoritative C-DAC SRS/65-item list/acceptance sheet and signed deliverables.
2. Map each item to: supported now, partial, not implemented, excluded, or requires clarification.
3. Record exact tolerances, supported printers/materials, offline/data rules, demo environment and acceptance method.
4. Resolve the meaning of the ₹50,000 total, the ₹20,000 advance, milestones, payment conditions, change requests and rejection/rework clauses from the signed agreement or written messages. Technical status alone cannot determine contractual liability.

**Exit:** client/product-owner-approved scope and traceability matrix.

### Gate B — Establish safe, reproducible staging

1. Freeze a baseline from the current main SHA.
2. Confirm environment variables, secrets, database migrations, Blob access, CAD service token and service health.
3. Confirm staging and production are separated and client data is not sent to an unapproved vision provider.
4. Run backup and restore in the approved environment.
5. Record the exact deployed commit and migration version.

**Exit:** reproducible staging deployment and tested recovery path. Do not use Production as a test environment.

### Gate C — Create and pass the golden engineering benchmark

1. Gather C-DAC-approved drawings with expected dimensions/features and reference STEP/STL where available.
2. Include clear, scanned, low-quality, multi-view and intentionally ambiguous drawings.
3. Record OCR/vision results, missing data, abstentions and wrong-feature associations.
4. Compare generated geometry against reference dimensions, bounding boxes, features and solids.
5. Define pass thresholds with C-DAC before evaluating results.

**Exit:** repeatable benchmark report with failures visible and traceable.

### Gate D — Close drawing-to-CAD correctness gaps

1. Add explicit measurement-region review and manual measurement entry.
2. Bind a confirmed measurement to a named feature and CAD parameter, with a separate confirmation gate.
3. Invalidate downstream confirmations after geometry changes.
4. Extend only the feature operations required by the approved scope.
5. Keep unsupported geometry blocked.

**Exit:** all required drawing cases pass the approved golden benchmark.

### Gate E — Make geometry inspectable

1. Implement a real web viewer for the exact saved geometry/version.
2. Add dimension and feature inspection.
3. Add drawing/model comparison and source-region highlighting.
4. Ensure the viewer cannot show a stale mesh while downloading/exporting a newer version.

**Exit:** browser test and owner inspection of version-matched geometry.

### Gate F — Validate fit, printability and slicing on actual machines

1. Confirm exact printer models, firmware, nozzle/extruder and material variants.
2. Create printer profiles from manufacturer documentation.
3. Validate printability thresholds against those configurations.
4. Slice benchmark STLs and review layer previews and G-code.
5. Physically print representative parts; measure critical dimensions and record defects.

**Exit:** accepted profile-specific test reports and physical print records.

### Gate G — Run full UAT and prepare handover

1. Run the clean-account end-to-end workflow and negative-path tests.
2. Test quotas, permissions, privacy, retention, export and deletion.
3. Conduct user tests with the intended non-CAD audience.
4. Prepare user/admin guides, deployment/backup/restore instructions, architecture and known limitations.
5. Present pass/fail/deviation results to C-DAC and obtain written acceptance.

**Exit:** signed acceptance or a mutually agreed, documented deviation list.

## 7. Immediate technical queue

| Priority | Action | Reason | Do not do |
|---|---|---|---|
| P0 | Obtain and map the signed client acceptance scope | We cannot measure completion against an unknown target | Do not claim 65 features are implemented |
| P0 | Correct stale status/handoff docs | Current docs describe pre-merge main and outdated PR states | Do not use old PR tables as current status |
| P0 | Reconcile open PR #22 against main and merged #29 | Its branch is diverged and shared-file overlap exists | Do not merge #22 wholesale |
| P0 | Verify staging/production and data-handling decision | Green PR CI is not a client deployment test | Do not upload confidential drawings to unapproved hosted vision |
| P1 | Build approved drawing benchmark | No reliable accuracy number exists | Do not describe uncalibrated confidence as accuracy |
| P1 | Complete measurement-to-feature/parameter workflow | Current review confirms transcription only | Do not let visual candidates silently change geometry |
| P1 | Implement exact-version interactive viewer | No production web mesh-inspection component is evidenced | Do not call static screenshots an interactive viewer |
| P1 | Add real printer profiles, inspect G-code and print tests | Generic FDM smoke does not validate customer printers | Do not claim physical print readiness from Docker smoke |
| P1 | CATIA STEP verification and format-by-format web export test | Export code exists but client interoperability is unproven | Do not claim CATIA acceptance without a recorded open test |
| P2 | Complete local provider workflow if in current contract | A separate product/service integration | Do not silently include it in the current fixed fee without scope agreement |

## 8. Client communication and delivery control

- Report completed work as engineering progress with commit, test and artifact evidence.
- Clearly label capabilities that are partial, unsupported or awaiting client decisions.
- Record client-provided drawings, reference dimensions, printer details and approvals.
- Log every scope change, acceptance decision, defect and rework request.
- Do not promise “any drawing”, “any mechanical part”, “fully offline”, “ISO-certified”, “print-ready for every printer” or “all 65 features” without evidence.
- Keep client confidentiality and intellectual property controls in place.
- Keep payment/advance and acceptance obligations tied to the written contract. If wording is unclear, obtain independent professional advice rather than relying on a technical status document.

## 9. Release decision template

A client submission may be labelled one of the following only:

1. **Engineering progress demonstration** — selected supported cases, explicitly marked as a non-final demonstration.
2. **Controlled pilot** — staging deployment, approved test data, restricted users and known limitations accepted in writing.
3. **Release candidate for acceptance** — all contract-critical gates pass with benchmark, deployment, CATIA/printer and UAT evidence.
4. **Accepted production delivery** — client acceptance recorded in writing, with handover and operational obligations completed.

At the assessment date, the evidence supports an **engineering foundation / progress demonstration**, not a claim of completed C-DAC production acceptance.

## 10. Source files and evidence to maintain

- `Offline_AI3D_TEAM_EXECUTION_PLAN.md` — workstreams, task IDs and phase exit gates.
- `docs/DRAWING_TO_CAD_V1.md` — actual drawing pipeline and supported v1 geometry.
- `docs/MEASUREMENT_REVIEW_V1.md` — review ledger behavior and explicit engineering boundary.
- `docs/HARDWARE_FIT_CHECK.md` — fit-check scope and limitations.
- `docs/STORAGE_RETENTION.md` — storage/version retention behavior.
- `tests/` and `.github/workflows/` — automated verification.
- GitHub PRs #20, #23, #24, #25, #26, #28 and #29 — merged implementation evidence.
- GitHub issue #8 — slicing/print acceptance tracking; its older current-status narrative must be refreshed after #24 and the later mainline smoke.
