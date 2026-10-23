# Work Status

Updated: 23 October 2026 (CAD reliability feature branch; CI validation in progress)

## CAD engine reliability review
- Branch: `feat/cad-engine-reliability-upgrade-20261023` (based on the deployed `main`; this branch is not merged).
- Geometry: canonical engine now normalizes explicit per-parameter units, validates feature dependency DAGs, supports profile extrusion/revolution/loft/sweep, and rejects invalid/empty boolean results.
- Rule parser: dimensions normalize to mm; supported boxes/cylinders can have a specified centered through-bore; tubes require outer and inner dimensions/wall thickness; ambiguous multiple-hole layouts and missing dimensions are rejected.
- Exports: STEP/STL paths now share canonical exporters; STL validation treats open surfaces, invalid manifold status, degenerate faces and non-positive volume as errors.
- Image meshes: closed watertight heightfield helper with tests; image-depth is explicitly approximate and not a substitute for exact multi-view reconstruction.
- Slicing: removed dummy preview G-code success path. Real slicing requires CuraEngine and printer/extruder definitions. G-code structure/bounds checks remain heuristic.
- Print UI: approval action now explicitly says simulation-only; no physical printer connection has been implemented.
- Regression automation: `.github/workflows/cad-engine-tests.yml` compiles Python modules and runs tests for geometry, parser, image meshes, export validation and slicing. Check the latest feature-branch Actions run before considering the code ready.
- Drawing OCR: implemented with Tesseract/PyMuPDF, file/page/pixel/size limits, annotation extraction, authenticated project API, private result storage, and a review-before-generation UI. OCR tests are included in CI. It still does not infer arbitrary solids directly from multi-view drawings.
- Not completed in this pass: exact image-to-parametric CAD, general-purpose engineering drawing understanding/GD&T interpretation, automatic supports/repair for all meshes, printer-host transport (OctoPrint/Klipper/USB), full web runtime/E2E checks, and runtime testing against the user's actual printer/profile.

---



| Area | Status | Evidence / next action |
| --- | --- | --- |
| Secret handling | PASS (local) | Prisma uses `DATABASE_URL`/`DIRECT_URL`; the credential-pattern scan found only documented/template placeholders, not a working credential. Rotate the formerly public Supabase password and any exposed Firebase Admin / cron secrets in their dashboards. |
| Git hygiene | PASS (local) | `.gitignore` is plain text and ignores timestamped backup directories. The untracked `d`, repair script, and `web/audit.json` were preserved rather than deleted. |
| Python unit tests | PASS | `python -m compileall -q src python-backend tests` and `python -m pytest`: 20 passed. |
| Local CAD API smoke test | PASS | `/health` reported `healthy`; invalid text returned `success: false`; a 40x20x10 mm box returned a 15,404-byte STEP file with an `ISO-10303` header and a 684-byte STL file. |
| CAD container | BLOCKED | Docker is not installed on this machine, so the production Docker build/container health check could not run. |
| CAD proxy | BLOCKED (end-to-end) | Browser helper calls only `/api/cad/...`; the server proxy owns upstream URL/token access, verified user identity, request/response size limits, and a 30-second timeout. The route builds successfully, but a local Next.js `start` smoke process did not become reachable; verify `/api/cad/health` on a configured preview deployment. |
| Web quality | PASS | Clean `npm ci`, `npm run lint`, and `npm run build` completed successfully. |
| Authentication / database / storage | BLOCKED | Requires real Firebase, PostgreSQL, Vercel Blob, and deployed-service credentials. No migration or remote mutation was run. |
| Drawing OCR | IMPLEMENTED WITH LIMITS | Tesseract/PyMuPDF extraction, dimensions/tolerances/fits/threads/material annotations, private result storage and review-before-generation UI; arbitrary-drawing interpretation remains incomplete. |
| Full npm audit | FAIL (8 high) | Remaining paths are `eslint-config-next -> fast-glob -> micromatch -> braces` and `prisma -> @prisma/config -> deepmerge-ts`. |
| Production npm audit | FAIL (3 high) | Only `prisma -> @prisma/config -> deepmerge-ts@7.1.5` remains. Updating to Prisma 7.10.1 is a breaking migration and needs separate compatibility testing. |
| Deployment / push | NOT RUN | No remote deployment, database migration, Git commit, or push was performed. |
