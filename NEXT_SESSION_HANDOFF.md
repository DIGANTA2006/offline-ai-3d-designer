# Next Session Handoff — Offline AI 3D Designer

**Updated:** 8 November 2026  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Client:** C-DAC Kolkata  
**Default branch:** `main`  
**Current main at audit:** `06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80`

## Read this first

The internal source of truth for pre-submission work is [C-DAC Client Submission Readiness and Verified Gap Register](docs/CLIENT_SUBMISSION_READINESS_2026-11-08.md).

**Do not claim the product is production-accepted or ready for arbitrary engineering drawings.** This is an engineering-grade project, but the current repository evidence is an engineering foundation—not a completed client acceptance package.

## Current mainline evidence

Merged implementation increments:
- PR #20 — drawing export provenance and provisional-dimension confirmation.
- PR #23 — Blueprint-native printability against generated solids.
- PR #24 — real positive G-code extrusion measurement/validation.
- PR #25 — MIME-aware OCR source selection.
- PR #29 — visual measurement candidates and persisted review decisions.

Merged documentation increments:
- PR #26 — engineering-grade guided UX wording.
- PR #28 — architecture/status baseline. Its original PR table became stale after subsequent same-day merges; current status is recorded in the new readiness register.

Latest main SHA: `06a3f2b0c60896cfc2c18d0d26d55e4b1da08c80`.

Latest main checks: 337 Python tests passed (2 warnings), web lint/typecheck/build passed, CodeQL Python and JS/TS passed, Docker CAD/OCR smoke passed, and the actual CuraEngine test slice reported 0.345410 m E-axis filament length and 2,962 deposition moves. Filament mass is not measured.

## Open PRs

- **#15 roadmap:** documentation-only, stale/diverged. Refresh to current main before relying on its status claims.
- **#22 semantic dimension evidence:** diverged from current main and overlaps drawing extraction/docs/tests changed by #29. Do not merge the branch wholesale. Compare exact hunks and selectively port only demonstrably missing changes; rerun CI on a main-based branch.

## Architecture boundaries

- Web: Next.js 15 App Router / TypeScript in `web/`.
- Authentication: Firebase sessions.
- Database: PostgreSQL via Prisma / Supabase.
- Files: private Vercel Blob.
- CAD service: FastAPI/Python, Railway, server-side service-token proxy.
- CAD kernel: build123d/OpenCASCADE.
- General `PartSpec` and drawing-specific `Blueprint` are different contracts.
- Drawing Blueprint currently supports four body types and seven feature types. It is not universal drawing-to-CAD.
- Sprocket builder uses circular seat cuts; it is not an ISO 606 involute chain-sprocket profile.
- Measurement review currently confirms transcription only; it does not map the measurement to a CAD parameter or prove arrow-to-feature association.
- Hardware fit check is axis-aligned, not full 3D interference/keep-out analysis.
- Printability thresholds are generic guidance, not printer/material certification.
- Positive E-axis G-code parsing exists; selected printer profiles, physical print evidence and measured filament mass remain open.
- No production WebGL viewer, CATIA opening evidence, drawing accuracy benchmark or physical-print acceptance artifact is currently evidenced.

## Required execution order before client submission

1. Freeze signed C-DAC scope, exact 65-item acceptance list (if applicable), tolerance requirements, printers/materials, privacy/offline boundary and acceptance terms.
2. Establish a C-DAC-approved golden drawing/reference-model benchmark; define acceptance thresholds before measuring accuracy.
3. Finish measurement source-region review, manual entry, dimension-to-feature/CAD-field association and geometry-change invalidation.
4. Complete only feature operations mapped to the signed acceptance scope; block unsupported geometry.
5. Implement a version-correct interactive 3D viewer with dimensions/features and drawing comparison.
6. Validate actual printer/material profiles, inspect G-code and perform documented physical prints.
7. Verify STEP/3MF/STL exports through CATIA and the agreed slicer, as required by the contract.
8. Run clean-account staging end-to-end, permissions/quota/error paths, security, backup/restore and user acceptance.
9. Deliver user/admin/deployment/restore documentation and a signed pass/fail/deviation matrix.

## Safe operating rules

- Work in focused branches and draft PRs; keep main and Production protected from experimental work.
- Do not merge or deploy without explicit product-owner approval.
- Do not send client-confidential drawings to an unapproved hosted vision provider.
- Do not turn a passing test or a generated file into an engineering acceptance claim.
- Keep unsupported geometry, uncertain dimensions and unconfirmed defaults blocked from misleading export/print-ready claims.
- Record every benchmark, defect, deviation, owner decision and acceptance result.
