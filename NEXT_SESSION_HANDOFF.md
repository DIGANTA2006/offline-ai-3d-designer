# Next Session Handoff — CAD Engine Reliability / Drawing OCR

**Last updated:** 2026-10-23  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Feature branch:** `feat/cad-engine-reliability-upgrade-20261023`  
**Pull request:** https://github.com/DIGANTA2006/offline-ai-3d-designer/pull/3  
**PR title:** feat: improve CAD engine reliability and safe slicing  
**PR state:** Open, Draft, not merged  
**Branch HEAD when this note was written:** `fb93a42b644620fe81489d5b1435a0d6b2346d82`

## Important: do not merge yet

The reliability branch has meaningful work, but the latest CI is **not green**. Do not merge into `main`, and do not deploy these changes to Production, until the failing test and CodeQL configuration are handled and the final PR checks pass.

## Changes made on the feature branch

- Geometry engine: more explicit validation of parameters and dependencies; profile-based extrusion, revolution, loft and sweep work; reject invalid/empty boolean results.
- Natural language to CAD: parse more explicit dimensions, support a centered through-bore for limited box/cylinder cases and tube/pipe inner bores; reject missing dimensions and unpositioned multiple-hole patterns instead of inventing geometry.
- Export and compatibility: stronger STL watertight/manifold checks; unify older import paths to share canonical specification, geometry, validation, storage, licensing and worker classes.
- Image mesh generation: add closed heightfield construction and lithophane improvements; explicitly treat single-view depth as approximate.
- Slicer: remove placeholder/demo G-code as a successful output. Real slicing requires a compatible CuraEngine and actual printer/extruder definitions. Desktop print approval is explicitly simulation-only; no printer transport exists.
- Drawing OCR: add `src/ai3d_designer/ocr/pipeline.py`, OCR package exports, bounded PDF/raster processing through Tesseract + PyMuPDF, extraction of visible text and recognizable dimensions/tolerances/fits/threads/material/surface-finish annotations, and OCR confidence provenance.
- Backend: `python-backend/main.py` exposes OCR extraction and guarded OCR-to-CAD. OCR-derived CAD requires a reviewed dimensioned description and an explicit supported shape; output is still approximate and is not a certified drawing interpretation.
- Web workflow: drawing upload UI now links to an OCR panel on project detail. Authenticated routes store OCR results against private project versions and create STEP/STL versions only after user review. Per-file source storage remains private.
- CI/docs: added CAD Engine Tests, Web Frontend Checks, geometry/OCR/API regression tests, README and engineering guide updates.

Useful docs: `docs/CAD_ENGINE_RELIABILITY.md`, `WORK_STATUS.md`.

## Blocker 1 — fix the current Python regression failure

Latest observed CAD Engine Tests run on the then-current head collected **70 tests: 69 passed, 1 failed**. Failure:

`tests/test_ocr_api.py::test_reviewed_dimensions_generate_real_step_and_stl_exports`

It returned: “Specify the primary shape explicitly…” for the reviewed prompt `A 40 x 20 x 10 mm box`.

Likely direct cause in `python-backend/main.py` around the shape guard near line 304: the regular expression currently appears as a raw pattern containing **double-escaped** word boundaries, `r"\\b(box|... )\\b"`, so it looks for a literal backslash rather than regex word boundaries. Correct the expression to use single regex escapes inside the raw string, then rerun all tests and add/keep a regression test that the explicit shape phrase “box” is recognized. Recheck parser behavior and STEP/STL generation; do not simply weaken the safety guard.

Latest failing run link at the time: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39952268258  
The failure was in the Python test step; Python compileall passed.

## Blocker 2 — CodeQL configuration

Both CodeQL Advanced language jobs failed during SARIF/report upload with:
“Code scanning is not enabled for this repository. Please enable code scanning in the repository settings.”

This was an account/repository feature configuration error, not evidence that the scanner discovered a code vulnerability. The repository is private, which may affect CodeQL availability on the current plan. Next session:
1. Check **Settings → Security → Code security and analysis** and confirm whether code scanning is available/enabled for this private repository.
2. If the plan supports it, enable code scanning and rerun the workflow.
3. Otherwise decide deliberately whether to replace/adjust the CodeQL Advanced workflow for a supported scanner or leave CodeQL failing and keep the PR unmergeable. Do not claim CodeQL passed, and do not disable security checks just to make the PR green without choosing an appropriate replacement.

Latest observed CodeQL run: https://github.com/DIGANTA2006/offline-ai-3d-designer/actions/runs/39952268268

## Checks last observed

- Web Frontend Checks: **passed** on the previous observed HEAD, including ESLint, TypeScript typecheck and Next.js production build. Re-run on final HEAD after fixes.
- CAD Engine Tests: **failed** on the previous observed HEAD as described above.
- CodeQL Advanced: **failed** because code scanning was disabled for the private repository.
- These are snapshots from the last check; newer commits rerun CI, so inspect current Actions before relying on any status.

## Next-session sequence

1. Open this handoff and PR #3; confirm the feature branch and HEAD before editing.
2. Fix the double-escaped regex and add a focused test. Run CAD Engine Tests until the suite passes.
3. Inspect the next failure(s), if any, and fix those rather than marking a failed test as acceptable.
4. Resolve the CodeQL configuration safely; verify the status of both language jobs.
5. Run/inspect the latest Web Frontend Checks on the final branch head.
6. Review the diff for any accidental regression from the compatibility-wrapper changes.
7. Only after all required checks pass, review the draft PR and decide separately whether to mark it ready/merge. Do not merge automatically.
8. After merge is explicitly approved, verify the Vercel Preview/Production behavior and Railway service before claiming the OCR workflow works end-to-end.

## Limitations still acknowledged

- OCR extracts text and visible annotations; it does not understand every drawing view or reconstruct arbitrary mechanical geometry.
- OCR-to-CAD currently asks for user review and delegates to the conservative supported text parser. Unsupported or underspecified prompts should fail; no guessed solid should be returned.
- Single-view image-to-3D remains approximate relief generation, not exact parametric/mechanical reconstruction.
- Automatic supports, universal mesh repair, full GD&T/fit interpretation, multi-view reconstruction, and physical printer-host integration remain unimplemented.
- CI does not replace testing the GUI on Windows or validating output against real engineering drawings, the user's printer profile, and slicer preview.

No production environment variables, live Razorpay configuration, database records, or Production deployment were changed by this work session.
