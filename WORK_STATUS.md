# Work Status — Offline AI 3D Designer

Updated: 23 October 2026 — OCR Preview routing fix added; latest checks running

## Current repository state

- Repository: `DIGANTA2006/offline-ai-3d-designer` (private).
- Feature branch: `feat/cad-engine-reliability-upgrade-20261023`.
- Pull request: [#3 — Improve CAD engine reliability and safe slicing](https://github.com/DIGANTA2006/offline-ai-3d-designer/pull/3).
- PR is **open and Draft**, not merged. Production and `main` remain unchanged by this feature branch.
- Last fully verified source HEAD before the OCR Preview-routing fix: `8be700b0f435425313b6adef37f4f089b585142d`. The OCR routing, Preview-only environment selection, Railway Dockerfile configuration, and regression-test commits came after that SHA; the latest PR checks must pass before treating those additions as verified.
- Full current state and next steps: [`NEXT_SESSION_HANDOFF.md`](NEXT_SESSION_HANDOFF.md).

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
