# Work Status — Offline AI 3D Designer

Updated: 2 November 2026 — PR #3 and PR #6 merged; Vercel deployment completed for `main` commit `f6a0449`

## Current main status

- Repository: `DIGANTA2006/offline-ai-3d-designer` (private); default branch: `main`.
- PR #3 — drawing-to-CAD/OCR workflow: **merged 25 October 2026**. Merge commit: `36992adfa34d30a70df3147eac725b9dfffebc1d`.
- PR #6 — hardware fit-check and CuraEngine/CAD deployment fixes: **merged 1 November 2026**. Merge commit: `806b7b55b6f57c8a96546cafaf77fe3ab334bea1`. [PR #6](https://github.com/DIGANTA2006/offline-ai-3d-designer/pull/6)
- PR #6 integrated the authenticated fit-check endpoints/dashboard flow, axis-aligned mounting-hole/boss checks, conservative preset confirmation, separate removable enclosure lid geometry, and the CuraEngine image capability smoke check.
- **Vercel deployment:** the supplied deployment log shows `main` commit `f6a0449` completed successfully on 2 November 2026. `npm ci`, Prisma Client generation (6.19.3), Next.js 15.5.28 compilation, lint/type validation, 10/10 static page generation, serverless-function creation, output collection, and deployment all completed.
- **Vercel project layout:** Root Directory `web`; Install Command `npm ci`; Build Command `npm run build`; Output Directory `.next`. Both root and `web/vercel.json` should remain consistent with the configured project root.
- The successful build confirms compilation and deployment packaging. It does **not** establish that authentication, Supabase/PostgreSQL operations, private Blob access, Railway CAD/OCR calls, billing webhooks, or the cron route have passed end-to-end runtime testing.
- **Build warnings to review separately:** npm reported 29 vulnerabilities (22 moderate, 7 high), deprecated package warnings, the unknown `cache-dir` npm configuration, and install scripts not yet covered by `allowScripts` for `prisma`, `protobufjs`, and `unrs-resolver`. These warnings did not stop this deployment. Review the dependency audit and package install scripts deliberately; do not run `npm audit fix --force` blindly.
- **Free-plan retention:** one saved project. Active Pro subscriptions and ADMIN accounts have unlimited projects. Projects are not deleted automatically; users must explicitly delete them. Each project keeps its two newest unprotected output versions, while protected versions are retained.
- **Engineering boundary:** fit-check is axis-aligned and does not provide arbitrary-rotation placement, complete 3D interference/keep-out analysis, thermal or structural analysis, or manufacturing certification. Drawing OCR/vision also requires human review and only supports the implemented geometry set.

## Current next steps

1. Run live smoke tests against the deployed URL: signup/login/session refresh, dashboard, project create/delete, private upload/download, and database persistence.
2. Verify the configured Production CAD backend `/health` and service-token pairing. Test supported text-to-CAD, drawing OCR/blueprint review, STEP/STL generation, and the hardware fit-check flow.
3. Verify Razorpay only if checkout is enabled, including webhook handling and subscription entitlements. Verify the daily account-deletion cron with the configured `CRON_SECRET`.
4. Review the 29 npm audit findings and the three install-script approval warnings before changing dependency versions or allowing scripts.
5. Keep representative CAD exports and slicing checks subject to independent CAD-viewer/Cura review; do not treat a green web build as engineering validation.

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
