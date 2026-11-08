# Next Session Handoff — Offline AI 3D Designer

**Updated:** 8 November 2026  
**Repository:** \`DIGANTA2006/offline-ai-3d-designer\` (private)  
**Default branch:** \`main\`  
**Current main:** \`9c8707c89f6ae04607a4a77cd183ba1491ad18a8\`  
**Last merged PR:** #20

## Product identity and engineering objective

Offline AI 3D Designer is an engineering-grade CAD and manufacturing platform. Its interface should guide people who do not know CAD; its feature program, CAD kernel, measurement provenance, geometry checks, export safeguards, printability requirements and manufacturing acceptance gates remain engineering-grade.

The intended journey is natural-language/drawing input → OCR and visual evidence → structured blueprint → missing-information questions → user-reviewed dimensions → deterministic CAD → geometry validation → printability → interactive 3D review → STEP/STL/3MF/ZIP and reports → printer-aware CuraEngine slicing → G-code/toolpath review → later local provider discovery.

AI proposes; deterministic code validates. Uncertain or unsupported geometry is blocked or routed to clarification. A photo without known scale is not an exact engineering drawing.

## Verified mainline baseline

- Main is PR #20's merge commit \`9c8707c...\`.
- PR #20 stores the effective dimensions used to create geometry, blocks drawing generation without the saved Blueprint, and requires exact provisional height/wall confirmation before export.
- Main already contains separate \`PartSpec\` and drawing \`Blueprint\` contracts. Do not merge or silently reinterpret these schemas.
- The repository is private. No Production deployment or secret change is included in the current draft PR work.

## Active drafts

- **#22:** semantic dimension evidence; recorded CI head passed 324 Python tests plus web, Docker and CodeQL.
- **#23:** saved drawing Blueprint printability; recorded head passed 320 Python tests plus web and CodeQL. Its Docker smoke reported 0.000 m because it predates #24's E-axis smoke gate.
- **#24:** positive E-axis extrusion/deposition validation; recorded 10 mm test cube measured 0.345410 m and 2,962 deposition moves; 322 Python tests, web and CodeQL passed.
- **#25:** OCR source selection from validated MIME/type; 316 Python tests and web/Docker/CodeQL passed.
- **#26:** documentation-only T73 wording change to guided UX / advanced engineering mode; CI passed.
- **#27:** combined image-read candidates, semantic grounding and MIME-aware drawing review; latest head \`f35d69d...\` is undergoing a fresh CI run after two test corrections.

PR #18 is the stale predecessor to #27. PRs #16/#17/#19 and #21 are closed as superseded. PR #20 is merged.

## Actual architecture

- Web: Next.js 15 App Router / TypeScript in \`web/\`, hosted on Vercel.
- Authentication: Firebase with server-side session validation.
- Database: PostgreSQL through Prisma; Supabase is the hosted service.
- Files: private Vercel Blob storage.
- Service boundary: Next.js routes call Railway FastAPI using a server-side CAD service token.
- CAD: Python, build123d and OpenCASCADE; general \`PartSpec\`/GeometryEngine and separate drawing \`Blueprint\` generator.
- Drawing: PyMuPDF/Tesseract plus optional vision adapter. Hosted vision remains blocked unless the server-side policy explicitly allows it.
- Manufacturing: CuraEngine and printer/extruder definitions, plus G-code validation.
- Billing: Razorpay subscription integration.

## Critical limitations

- Drawing Blueprint currently has four body types and seven feature types; it is not universal drawing-to-CAD.
- The broader PartSpec feature engine is not proof that every operation is exposed in each drawing/web path.
- The dedicated sprocket builder uses circular seat cuts; it is not an ISO 606 involute chain-sprocket profile.
- OCR value matches and visual candidates do not prove dimension-arrow/feature association.
- Full measurement ledger, image-region highlighting, candidate confirmation and provenance-preserving edit workflow remain incomplete.
- No interactive browser 3D viewer was found in the current main component tree.
- Printer-specific profiles, layer preview and physical print evidence remain open.
- Hardware fit-check is axis-aligned; it does not certify arbitrary 3D interference, thermal or structural performance.
- Physical printer control is not implemented and must remain disabled.

## Next engineering order

1. Review and integrate approved Phase 1 PRs after current-head CI, rebases and product-owner approval.
2. Finish #27 on the integrated #22/#25 baseline; do not merge a failed or stale head.
3. Build the measurement editor with source, unit, value, tolerance, page/view/region, feature association, confidence and confirmation state; edits invalidate previous confirmation.
4. Build a real interactive viewer from the exact validated generated solid/mesh.
5. Establish the golden drawing set and dimension/feature/bounding-box accuracy metrics.
6. Add printer-specific profiles, layer/toolpath review and physical print records after owner selects printer models.
7. Update status documents after each merge and live test.

## Owner inputs and acceptance decisions

No separate, authoritative 65-feature C-DAC acceptance catalogue was found in the current repository or supplied status material. In the existing team plan **T65** means opening the exported STEP in CATIA and logging the findings; the wider task plan includes IDs beyond T65. Obtain the actual C-DAC 65-item specification before turning it into an implementation checklist or claiming coverage.

Also confirm signed C-DAC scope, ISO 606 sprocket requirement, vision/data policy, printer/material profiles, IP/licence terms and the golden drawing artifacts.

## Safe operating rules

- Work in focused branches and draft PRs.
- Do not commit directly to main, merge, or deploy without Diganta's approval.
- Do not change Production secrets, databases, hosted-vision settings or payment settings.
- Prefer Vercel/Railway/Supabase Preview and CI for cloud verification; do not require a local Docker/Linux setup when cloud verification suffices.
- For work needing local Windows execution, provide a complete PowerShell script with backups, path checks, bracket-safe paths, tests and explicit PASS/FAIL output.
