# Work Status — Offline AI 3D Designer

**Updated:** 8 November 2026  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Client:** C-DAC Kolkata  
**Default branch:** `main`  
**Current main:** `06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80`  
**Latest merged change:** PR #26

**Submission status: not yet evidenced as a production acceptance candidate.**  
The internal gate register is [C-DAC Client Submission Readiness](docs/CLIENT_SUBMISSION_READINESS_2026-11-08.md). It supersedes the historical PR-status notes below and older handoff snapshots.

## Current verified state

- The product is an engineering-grade CAD/manufacturing platform. Guided UX is only a presentation layer.
- Merged implementation increments: #20, #23, #24, #25 and #29. Documentation increments: #26 and #28.
- PR #29 includes visual measurement candidates and the first persisted measurement-review ledger. A confirmed reading is a transcription decision only; it does not bind a dimension to a CAD parameter or prove arrow-to-feature association.
- PR #24 validates positive E-axis extrusion. Latest mainline Docker smoke measured 0.345410 m filament length and 2,962 deposition moves; filament mass is not measured.
- Current drawing Blueprint remains narrower than the general PartSpec engine: four body types and seven feature types. Sprocket seat cuts are a preview approximation, not an ISO 606 involute chain profile.
- Hardware fit checking remains axis-aligned. Printability uses generic FDM guidance and is not physical/material certification.
- No production WebGL viewer, CATIA-open evidence, drawing-accuracy benchmark, physical-print record or complete client acceptance run is evidenced.

## Latest mainline verification

- Python CAD/mesh tests: **337 passed, 2 warnings**.
- Next.js lint, TypeScript and production build: passed.
- CodeQL Python and JavaScript/TypeScript: passed.
- Docker CAD/OCR runtime smoke: passed.
- Real CuraEngine smoke: passed with positive E-axis extrusion.
- Vercel and Railway status contexts for the recorded main SHA are successful. These do not replace a fresh full production user-journey test.

Evidence:
- [CAD Engine Tests](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/42444037349)
- [Web Frontend Checks](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/42444037367)
- [CodeQL Advanced](https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/42444037363)

## Pull request state

| PR | Current state | Required handling |
|---|---|---|
| #15 — Accessible 3D-printing roadmap | Open, documentation-only, diverged 11 ahead / 29 behind at assessment | Refresh against current main; update roadmap status and gates |
| #22 — Semantic dimension evidence | Open, diverged 3 ahead / 18 behind at assessment | Shared drawing files overlap with merged #29; inspect exact unique hunks and selectively port only missing changes. Do not merge wholesale |
| #23 — Blueprint-native printability | Merged | Current code path is present; does not prove source-drawing accuracy |
| #24 — Positive extrusion validation | Merged | Current smoke proves positive E-axis deposition, not real printer acceptance |
| #25 — MIME-aware OCR source selection | Merged | Included in current OCR-source selection path |
| #26 — Engineering-grade guided UX terminology | Merged | Documentation change |
| #28 — Architecture/status documentation | Merged | Original PR-status snapshot became stale after later same-day merges; corrected snapshot is in review |
| #29 — Measurement-review ledger | Merged | First persisted review stage; measurement-to-geometry association remains future work |
| #30 — Client submission readiness gates | Draft PR | Documentation-only control register; not a release certificate |

## Immediate delivery priorities

1. Obtain the signed C-DAC scope and authoritative acceptance catalogue. The separate 65-item list has not been found; do not invent feature coverage.
2. Confirm written data-handling, hosted-vision, deployment, hosting and offline requirements before using confidential drawings.
3. Establish the approved golden drawing set and benchmark OCR, dimensions, feature association and generated geometry against references.
4. Complete measurement-to-feature/CAD-parameter workflow, including source-region review and confirmation invalidation.
5. Implement the actual web 3D viewer for the exact saved model version.
6. Validate selected printer/material profiles, G-code, CATIA STEP interoperability and physical prints.
7. Run full staging end-to-end, security, backup/restore and non-technical user acceptance tests.
8. Prepare handover and obtain written C-DAC acceptance or an agreed, documented deviation list.

## Release boundary

Do not claim arbitrary drawing accuracy, all 65 features, ISO 606 engagement certification, fully offline operation, universal printer support, CATIA acceptance or physical print readiness without corresponding evidence. CI success and merged PRs are engineering progress, not client acceptance.

No production secrets, databases, hosted-vision settings or deployments were changed by the readiness documentation work.


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
