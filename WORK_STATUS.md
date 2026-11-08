# Work Status — Offline AI 3D Designer

**Updated:** 8 November 2026  
**Repository:** \`DIGANTA2006/offline-ai-3d-designer\` (private)  
**Default branch:** \`main\`  
**Current main:** \`9c8707c89f6ae04607a4a77cd183ba1491ad18a8\`  
**Latest merged change:** PR #20 — drawing export provenance and provisional-dimension confirmation

See [Project Architecture, Status and Delivery — 8 November 2026](docs/PROJECT_ARCHITECTURE_STATUS_2026-11-08.md) for the verified architecture, contract boundaries, current PR evidence and release gaps.

## Current verified repository state

- The repository is **Private** and \`main\` is the default branch.
- PR #20 is merged. Effective CAD defaults are retained in the saved blueprint, drawing generation requires a saved structured blueprint, and the exact provisional height/wall value must be confirmed before export.
- No application rollback was performed. Authentication, private storage, billing, CAD, OCR, fit-check, printability, slicing and deployment work remain intact.
- The product is **Offline AI 3D Designer**, an engineering-grade CAD/manufacturing platform. A guided interface for non-specialists is a presentation layer, not a reduced CAD engine.
- The open Phase 1/2 PRs are not part of \`main\` until reviewed and merged. Green CI on a PR branch is evidence only for that exact branch head.

## Open pull requests and verification snapshot

| PR | Scope | Evidence / state |
|---|---|---|
| #15 | Accessible 3D-printing product roadmap | Open; documentation-only |
| #18 | Initial visual-dimension candidates | Closed as stale; implementation successor is #29 |
| #22 | Semantic drawing dimension evidence | Draft; recorded head passed 324 Python tests, web, Docker and CodeQL |
| #23 | Blueprint-native printability | Draft; 320 Python tests, web and CodeQL passed; its old Docker smoke reported 0.000 m filament |
| #24 | Positive G-code extrusion validation | Draft; 322 Python tests; test cube measured 0.345410 m E-axis filament and 2,962 deposition moves; web and CodeQL passed |
| #25 | OCR source selection using validated MIME metadata | Draft; 316 Python tests; OCR helper, web, Docker and CodeQL passed |
| #26 | Guided UX wording / advanced engineering mode | Draft, documentation-only; CI passed |
| #27 | Combined visual-dimension candidate work | Closed as superseded by #29 |
| #29 | Combined Phase 2 visual candidates plus persisted Phase 3 measurement-review ledger | Draft; head ee77ff2...; 327 Python tests, web, Docker/CAD-OCR and both CodeQL scans passed. Docker smoke still reports 0.000 m filament pending #24 integration |

PR #16, #17 and #19 were closed as superseded by #23, #24 and #25. PR #18 and #27 were closed as superseded by #29. PR #21 was closed as superseded by #22. PR #20 is merged. No PR #22–#26 or #29 change is claimed as merged or deployed. Issue #11 was closed as completed after verifying the authenticated printability-router mount; issue #8 remains open for extrusion, endpoint/upload verification and printer acceptance.

## Immediate priorities

1. Product-owner review of #15's refreshed roadmap, #26's guided/advanced wording, and #28's architecture/status document.
2. Review/merge smaller corrective PRs #22–#25 in the dependency order agreed with the owner; rerun combined CI after rebasing.
3. Review #29 (Phase 2 plus the first persisted Phase 3 ledger). A confirmed reading is a transcription decision only, not a CAD parameter or arrow-to-feature association.
4. Continue Phase 3 with manual measurement entry, explicit dimension-to-feature/CAD-field association, image-region highlighting and confirmation invalidation for geometry edits.
5. Implement a real interactive viewer from the exact validated geometry.
5. Establish the owner-approved golden drawing set and compare model dimensions/bounds against references.
6. Select printer/material profiles and inspect slicer previews before physical tests.
7. Resolve C-DAC scope, ISO 606 sprocket expectations, hosted-vision data rules, IP/licence and printer acceptance requirements.

## Evidence boundaries

- CI proves only the checks run on the recorded commit.
- No fresh full Production sign-in/database/private-Blob/payment/CAD-service journey was run in this documentation audit.
- No CATIA opening test, drawing-to-mesh accuracy benchmark, customer G-code inspection or physical print is claimed. PR #29's Docker smoke is a real CuraEngine slice but still reports 0.000 m filament; PR #24 remains required before trusting filament estimates.
- The current npm vulnerability count, IP/licence terms and branch-protection settings need a separate fresh review; old counts must not be presented as current.


## Historical implementation and verification notes

The sections below preserve October 2026 implementation history. Their earlier statements that PR #3 or PR #6 were open, Draft, unmerged, or awaiting the first Vercel build are **superseded by the current status above**. Use the current main branch and the current deployment guide for operational steps.

## Historical OCR/CAD reliability notes (23–24 October)

## New OCR deployment fix (23 October 2026)

- Confirmed root cause: the exact error `OCR not yet implemented. Use /api/v1/text-to-cad for natural language input.` is hard-coded in the legacy `main` branch's Python backend. The feature branch has the real Tesseract/PyMuPDF OCR route.
- Added `web/src/lib/cad-service-config.ts`. On Vercel Preview, text-to-CAD, drawing OCR, drawing CAD generation, and CAD health now require `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW`; they cannot silently fall back to the Production CAD backend. The earlier `fix: isolate Vercel Preview CAD backend configuration` commit added the helper but not all route wiring; manual Preview must use the newer branch tip. Local development and Production continue using `CAD_SERVICE_URL` / `CAD_SERVICE_TOKEN`.
- The drawing OCR route checks backend `/health` and requires the feature branch's OCR readiness fields before sending the file. It distinguishes the legacy stub from an OCR build missing Tesseract/dependencies, and maps service-token failures away from browser-login redirects.
- Hardened `python-backend/Dockerfile`: installs server requirements including build123d, installs root package metadata with `--no-deps` (avoids Windows/desktop-only dependencies), adds native runtime libraries, and fails image build unless CAD and OCR import smoke tests pass. CI now builds the same Docker image.
- `/health` now separates `cadRuntimeAvailable`, `serviceTokenConfigured`, and `cadRuntimeError` from overall `cadAvailable` so a missing Railway token is not misdiagnosed as a missing CAD dependency. Added tests for both failure modes.
- Updated `python-backend/railway.toml` for existing Config-as-Code services and added the Vercel/Railway Preview setup steps to `DEPLOYMENT.md` and `web/.env.example`. New Railway Preview services must be configured in the dashboard because Railway has deprecated Config as Code for new services.
- Added a regression test confirming `/health` reports the OCR runtime's actual availability.
- Required operator steps remain: deploy a separate Railway service from the feature branch with repository-root build context and Dockerfile path `python-backend/Dockerfile`; ensure `/health` shows `ocrAvailable: true`; then set the two Preview-only Vercel environment variables and redeploy Preview. Do not change Production variables.

## Implemented on the feature branch

- Geometry generation with explicit parameter-unit handling, feature dependency ordering, Boolean validation, extrusion, revolution, loft and sweep.
- Conservative dimension parser for supported shapes, through-bores and hollow tubes; ambiguous shapes/holes and missing dimensions are rejected instead of guessed.
- Parser security fixes: numeric pattern is bounded (1–8 integer digits, at most six decimals), numeric boundaries prevent prefix parsing, and descriptions over 4,000 characters are rejected before regex/LLM processing.
- Stronger STEP/STL export validation for non-finite, degenerate, non-watertight and invalid-manifold outputs.
- Watertight heightfield and lithophane mesh utilities. Single-image depth output remains approximate.
- CuraEngine-backed slicing only; no fake G-code fallback. A real printer/extruder definition is required. Desktop print approval is simulation-only; physical printer transport is not implemented.
- Bounded PDF/raster drawing OCR with Tesseract/PyMuPDF, recognition of visible engineering annotations, private project OCR result storage, and review-before-generation UI/API. Supported, reviewed text can generate validated private STEP/STL versions.
- Legacy package paths now forward to canonical model, geometry, validation, storage, licensing and worker APIs.
- Engineering usage guide and regression workflows have been added.

## Verification observed on code-tested HEAD `8be700b`

| Check | Result | Evidence |
| --- | --- | --- |
| Python compile + CAD regression suite | PASS — 75 tests, current PR HEAD | [CAD Engine Tests](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963730) |
| Web lint, TypeScript and production build | PASS, current PR HEAD | [Web Frontend Checks](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963698) |
| CodeQL Python + JavaScript/TypeScript analysis | PASS, current PR HEAD; both SARIF artifacts contain 0 results | [CodeQL Advanced](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963530) |

Because GitHub Code Scanning upload is unavailable for the current private-repository configuration, CodeQL SARIF is retained as downloadable Actions artifacts instead of appearing in the repository Security tab. The workflow gates high/critical security findings and regex-DoS/regex-injection findings. A passed CodeQL job means analysis and this gate completed; it is not a guarantee of absence of all vulnerabilities.

The linked run evidence below is historical for the pre-wiring-fix source HEAD only. Recheck the latest CAD/Web/CodeQL results at the current branch tip before manual Preview deployment or merge.

## Not complete / must be tested before release

- Full arbitrary engineering-drawing understanding, hidden-surface reconstruction, automated GD&T/tolerance interpretation, and guaranteed drawing-to-parametric-CAD accuracy.
- Automatic support generation and universal mesh repair.
- Physical printer communication through USB/network/OctoPrint/Klipper or another host.
- Manual Windows GUI testing and real-world CAD-viewer/slicer verification.
- End-to-end Vercel Preview validation of private upload, OCR persistence, review/edit, supported CAD generation, private exports, and subscription/admin entitlements.

Do not merge or deploy these changes until the final latest-head checks and manual Preview validation are reviewed. No production environment variables, live Razorpay configuration, database records, migration, or Production deployment were changed by this feature work.


## Structured Drawing-to-CAD v1 (24 October 2026)

- Code-tested source HEAD: `38ac1ed6470283494ec8bdb3d2f15c2e67d855e2`. The status/handoff updates being added after this are documentation-only; recheck the latest Actions run on the final branch tip.
- Added `src/ai3d_designer/drawing_to_cad/blueprint.py`, `extraction.py`, and `generator.py`.
- OCR now returns a typed Blueprint, grounded dimension inventory, page provenance, PDF vector circle/rectangle candidates and the selected vision model; FastAPI connects that extraction to the existing OCR API.
- Optional vision providers: Ollama (reachable from the Python service) or an OpenAI-compatible chat-completions provider with strict JSON-schema output. Without a configured vision endpoint the fallback is label-based OCR, not visual reconstruction. See `docs/DRAWING_TO_CAD_V1.md` and `DEPLOYMENT.md`.
- UI editor now displays an editable structured blueprint, defaulted values, ungrounded values, vector PDF candidates, warnings and unsupported geometry. The existing authenticated Vercel route accepts the reviewed blueprint directly without a free-text prompt and keeps STEP/STL outputs private.
- Deterministic generator checks OpenCASCADE validity, one-solid output, positive volume, dimensions where applicable, STEP/STL output and STL watertightness. Unsupported teeth, bends, threads, partial/uneven hole patterns, ungrounded profile coordinates and unsupported revolved-body cuts are blocked rather than silently substituted.
- Defaults are provisional: 10 mm solid height, 2.5 mm enclosure wall. They are highlighted and require user review. A watertight mesh is not proof of correct interpretation or manufacturing readiness.
- Verification at code-tested source HEAD `38ac1ed`: **294 Python tests passed after the fix round (see FIX_REPORT.md)**; Railway Docker image smoke test passed (`CAD_RUNTIME_AVAILABLE=true OCR_AVAILABLE=true`); Next.js lint/typecheck/production build passed; CodeQL Python and JS/TS passed with 0 results per SARIF report. GitHub Code Scanning upload remains unavailable in the current repository configuration, so SARIF is retained as Actions artifacts.
- Actions: [CAD Engine Tests](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/40062651779), [Web Frontend Checks](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/40062651924), [CodeQL Advanced](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/40062651755).
- Historical Preview checklist from 24 October (before PR #3 merged): configure a dedicated Railway Preview service and Preview-only Vercel CAD variables, then test upload → OCR → blueprint review → supported-part generation → private STEP/STL downloads. This is retained as implementation history; use the current status and deployment guide above for today's release work.
