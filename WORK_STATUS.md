# Work Status

Updated: 21 October 2026 (local verification)

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
| OCR and full spec generation | NOT IMPLEMENTED | The backend returns explicit unavailable responses; text-to-CAD is the available flow. |
| Full npm audit | FAIL (8 high) | Remaining paths are `eslint-config-next -> fast-glob -> micromatch -> braces` and `prisma -> @prisma/config -> deepmerge-ts`. |
| Production npm audit | FAIL (3 high) | Only `prisma -> @prisma/config -> deepmerge-ts@7.1.5` remains. Updating to Prisma 7.10.1 is a breaking migration and needs separate compatibility testing. |
| Deployment / push | NOT RUN | No remote deployment, database migration, Git commit, or push was performed. |
