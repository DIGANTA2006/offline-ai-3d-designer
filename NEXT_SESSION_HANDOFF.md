# Next Session Handoff — CAD Engine Reliability / Drawing OCR

**Updated:** 2026-10-23 (OCR Preview routing fix added; recheck latest CI)  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Feature branch:** `feat/cad-engine-reliability-upgrade-20261023`  
**Pull request:** https://github.com/DIGANTA2006/offline-ai-3d-designer/pull/3  
**PR status:** Open, Draft, not merged  
**Code-tested HEAD:** `8be700b0f435425313b6adef37f4e089b585142d`

## OCR Preview backend wiring fix

The manual Preview test uncovered the legacy backend placeholder. The exact message `OCR not yet implemented. Use /api/v1/text-to-cad for natural language input.` is hard-coded in the Python backend on `main`; the feature branch's `python-backend/main.py` contains a real `/api/v1/ocr/extract` route. The previous Preview used generic `CAD_SERVICE_URL`, so it could call that older backend.

The feature branch now:
- Requires `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW` when `VERCEL_ENV=preview`; Preview routes no longer fall back to the Production backend.
- Checks backend `/health` for the feature-branch OCR capability contract before processing a drawing.
- Configures Railway to use `python-backend/Dockerfile` (Tesseract system package + Python OCR dependencies) rather than Nixpacks.
- Documents the separate Railway Preview service setup in `DEPLOYMENT.md`.

**Required manual setup:** create an isolated Railway Preview service connected to `feat/cad-engine-reliability-upgrade-20261023`, with repository-root build context and Dockerfile path `python-backend/Dockerfile`. Set a new server-only `CAD_SERVICE_TOKEN`. Confirm its `/health` returns both `cadAvailable: true` and `ocrAvailable: true`. In Vercel, set Preview-only `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW` to that service and token, then redeploy the Preview. Leave Production's `CAD_SERVICE_URL` and `CAD_SERVICE_TOKEN` unchanged.

## Release safety

Do **not** merge automatically. Production and `main` have not been changed by this feature branch. Keep the PR in Draft until final review and an explicit merge decision.

## What was changed

- **Geometry core:** consistent millimeter handling with explicit parameter units; stable dependency sorting; clear errors for duplicate IDs, missing parents, cycles, invalid dimensions and empty boolean results.
- **Profile-based features:** polygon extrusion, revolution (radius/height profiles in XZ), loft with section offsets, and profile/path sweep.
- **Conservative text-to-CAD:** dimension triplets and common units; centered Boolean through-bore for supported box/cylinder descriptions; tube/pipe inner bore from inner diameter or wall thickness. Missing dimensions and unspecified multiple-hole layouts fail instead of receiving guessed geometry.
- **Regex/input hardening:** fixed the double-escaped shape-recognition word-boundary regex that rejected “A 40 x 20 x 10 mm box.” Numeric tokens are bounded to 1–8 integer digits and up to six decimals with numeric boundaries; the public parser rejects descriptions longer than 4,000 characters. New regression tests cover these cases.
- **Export validation:** canonical STEP/STL exporter paths and stronger checks for empty/non-finite/open/degenerate meshes and manifold validity.
- **Image relief:** closed watertight heightfield meshes and improved lithophane construction. Single-view depth/lithophane output remains approximate, not exact mechanical reconstruction.
- **Slicing safety:** removed the placeholder G-code success path. Real slicing requires CuraEngine plus compatible printer/extruder definitions. The desktop approval action is explicitly simulation-only; no physical printer transport exists.
- **Drawing OCR:** Tesseract + PyMuPDF OCR for supported PDF/raster inputs with limits on input size/page count/image pixels, extraction of visible dimension/tolerance/fit/thread/material/surface-finish annotations, confidence provenance and review warnings.
- **OCR-to-CAD web/backend workflow:** authenticated project OCR route stores the extraction privately; user edits/reviews a dimensioned description before supported CAD generation. STEP/STL are stored as private version outputs only after validation. Unsupported/underspecified shapes fail rather than guessed geometry.
- **Compatibility APIs and CI:** legacy imports forward to canonical specification/geometry/validation/storage/licensing/worker classes. Added CAD Engine Tests, Web Frontend Checks, OCR/geometry/export/slicer regression tests, and engineering documentation.

Guides: `docs/CAD_ENGINE_RELIABILITY.md`, `WORK_STATUS.md`.

## Previous verification before OCR Preview-routing fix (`8be700b`)

- **CAD Engine Tests on that earlier source HEAD:** PASS; 75 tests passed and Python compilation passed. Run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963730
- **Web Frontend Checks on that earlier source HEAD:** PASS; ESLint, TypeScript typecheck and Next.js production build passed. Run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963698
- **CodeQL Advanced on that earlier source HEAD:** PASS; both JavaScript/TypeScript and Python jobs succeeded. Both SARIF artifacts were downloaded and inspected: **0 findings** in Python and **0 findings** in JavaScript/TypeScript. Run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963530
- **Private-repository constraint:** this repository could not upload SARIF to GitHub's Code Scanning UI. The CodeQL workflow now saves reports as downloadable Actions artifacts, and its gate fails on high/critical security results plus regex-DoS / regex-injection findings. A green CodeQL job means the analysis/gate completed; it does not mean results are visible in the repository Security tab.
- The OCR Preview-routing fix and its regression test were committed after this historical verified SHA. Verify all three checks on the current latest branch head before manual Preview testing; earlier green runs do not cover this follow-up fix.

## Next steps

1. Check the latest PR #3 CAD/Web/CodeQL workflows after all routing changes commit; do not rely on checks for an earlier branch head.
2. Create an isolated Railway Preview backend from the feature branch using the repository root and Dockerfile path `python-backend/Dockerfile`; verify `/health` reports `ocrAvailable: true`.
3. Set Vercel Preview-only `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW` to the dedicated backend, then redeploy Preview. Do not change Production variables.
4. Test a supported PDF/image upload, OCR persistence, review/edit, supported-part generation, private STEP/STL downloads, ambiguous prompt rejection, private file access, and Pro/admin entitlements.
5. Test exports in an independent CAD viewer; test slicing in Cura with the actual printer/extruder profile, and preview before any physical print. Keep PR #3 Draft until all checks and manual Preview tests pass. Never merge automatically.

## Known limitations

- OCR finds visible text and recognizable annotations; it does not semantically reconstruct every drawing view, hidden surface, GD&T scheme, fit, tolerance or manufacturing intent.
- The OCR-to-CAD path currently depends on human-reviewed text and the conservative supported primitive parser; arbitrary dimensioned mechanical drawings are not guaranteed to convert.
- Single-view image-to-3D remains approximate relief generation, not exact parametric CAD.
- Automatic support generation, universal mesh repair, exact multi-view reconstruction, and physical printer-host/USB/network integration are not complete.
- Passing CI is not a substitute for Windows GUI testing, representative engineering-drawing validation or printer-specific verification.

No production environment variables, live Razorpay configuration, database records, or Production deployment were changed by this work session.
