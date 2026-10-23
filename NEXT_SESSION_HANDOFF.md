# Next Session Handoff — CAD Engine Reliability / Drawing OCR

**Updated:** 2026-10-23 (refreshed after current-head CI completed)  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Feature branch:** `feat/cad-engine-reliability-upgrade-20261023`  
**Pull request:** https://github.com/DIGANTA2006/offline-ai-3d-designer/pull/3  
**PR status:** Open, Draft, not merged  
**Code-tested HEAD:** `8be700b0f435425313b6adef37f4e089b585142d`

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

## Verification as of code-tested HEAD `8be700b`

- **CAD Engine Tests on current PR HEAD:** PASS; 75 tests passed and Python compilation passed. Run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963730
- **Web Frontend Checks on current PR HEAD:** PASS; ESLint, TypeScript typecheck and Next.js production build passed. Run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963698
- **CodeQL Advanced on current PR HEAD:** PASS; both JavaScript/TypeScript and Python jobs succeeded. Both SARIF artifacts were downloaded and inspected: **0 findings** in Python and **0 findings** in JavaScript/TypeScript. Run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39957963530
- **Private-repository constraint:** this repository could not upload SARIF to GitHub's Code Scanning UI. The CodeQL workflow now saves reports as downloadable Actions artifacts, and its gate fails on high/critical security results plus regex-DoS / regex-injection findings. A green CodeQL job means the analysis/gate completed; it does not mean results are visible in the repository Security tab.
- The PR-triggered CAD Engine run on the same `8be700b` HEAD was still completing setup at the time this note was refreshed; the matching push test run had already passed. Recheck the current PR check state before merge.

## Next steps

1. Refresh PR #3 and verify the latest branch head plus the latest CAD/Web/CodeQL checks (new handoff-only commit may retrigger them).
2. Keep PR #3 as Draft while reviewing the full diff, particularly the CAD profile geometry and new project OCR routes.
3. Perform a manual Vercel Preview deployment only after checks are complete; test a supported PDF/image upload, OCR result persistence, editing/review, successful supported-part generation, private STEP/STL download, failed ambiguous prompt behavior and Pro/admin entitlement behavior.
4. Test real STEP/STL outputs in an independent CAD viewer. For slicing, test in Cura with the actual printer/extruder profile and preview before any physical print.
5. Only after preview validation should the PR be marked ready. Do not merge automatically; Production deployment is a separate explicit decision.

## Known limitations

- OCR finds visible text and recognizable annotations; it does not semantically reconstruct every drawing view, hidden surface, GD&T scheme, fit, tolerance or manufacturing intent.
- The OCR-to-CAD path currently depends on human-reviewed text and the conservative supported primitive parser; arbitrary dimensioned mechanical drawings are not guaranteed to convert.
- Single-view image-to-3D remains approximate relief generation, not exact parametric CAD.
- Automatic support generation, universal mesh repair, exact multi-view reconstruction, and physical printer-host/USB/network integration are not complete.
- Passing CI is not a substitute for Windows GUI testing, representative engineering-drawing validation or printer-specific verification.

No production environment variables, live Razorpay configuration, database records, or Production deployment were changed by this work session.
