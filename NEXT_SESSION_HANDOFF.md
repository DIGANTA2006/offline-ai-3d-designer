# Next Session Handoff — Offline AI 3D Designer

**Updated:** 2 November 2026  
**Repository:** `DIGANTA2006/offline-ai-3d-designer` (private)  
**Default branch:** `main`  
**Latest recorded successful Vercel deployment:** commit `f6a0449` (2 November 2026)

## Current repository state

- PR #3 (drawing-to-CAD/OCR workflow) merged on 25 October 2026. Merge commit: `36992adfa34d30a70df3147eac725b9dfffebc1d`.
- PR #6 (hardware fit-check and CuraEngine/CAD deployment fixes) merged on 1 November 2026. Merge commit: `806b7b55b6f57c8a96546cafaf77fe3ab334bea1`. [PR #6](https://github.com/DIGANTA2006/offline-ai-3d-designer/pull/6)
- The Vercel log for main commit `f6a0449` shows a successful build and deployment. Next.js 15.5.28 compiled, lint/type validation completed, static generation reached 10/10, serverless functions were created, and Vercel reported `Deployment completed`.
- This is build/deployment evidence only. It does not prove end-to-end runtime integration for Firebase, Supabase/PostgreSQL, private Blob storage, Railway CAD/OCR, Razorpay, or cron.

## Vercel configuration that succeeded

| Setting | Value |
|---|---|
| Framework | Next.js |
| Root Directory | `web` |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `.next` |

The root directory is already `web`; do not prefix install/build commands with `cd web &&`. Keep `web/vercel.json` and the Vercel dashboard settings aligned. If the Output Directory override is enabled, the literal value is `.next`, not `Next.js default` or `web/.next`.

## Build warnings observed on the successful deployment

- npm audit reported 29 vulnerabilities: 22 moderate and 7 high.
- Deprecated package warnings included `node-domexception`, `uuid@9`, and `eslint@9.39.5`.
- npm warned about an unknown `cache-dir` configuration.
- npm's install-script policy listed `prisma`, `protobufjs`, and `unrs-resolver` as scripts not yet covered by `allowScripts`.

These warnings did not prevent the deployment. Review the audit and each install script deliberately; do not run `npm audit fix --force` without assessing breaking changes.

## Immediate next steps

1. Open the deployed application and test signup, login, session persistence, dashboard navigation, and profile/admin access.
2. Test project creation/deletion and verify the Free-plan one-project cap. Active Pro and ADMIN accounts have unlimited projects.
3. Verify private Vercel Blob upload/download and Supabase/PostgreSQL persistence.
4. Check the Production CAD backend `/health`, the matching server-only service token, and the `CAD_SERVICE_URL` configuration. Test supported text-to-CAD and drawing OCR/blueprint review.
5. Test the dashboard hardware fit-check flow with a real, verified component revision and reviewed enclosure dimensions.
6. Verify billing/webhooks only if checkout is enabled, and check the account-deletion cron with `CRON_SECRET`.
7. Review npm audit findings and the three install-script warnings before updating packages or approving scripts.

## Current engineering limitations

- Hardware fit-check is axis-aligned; it does not cover arbitrary rotation, full 3D collision/keep-out analysis, thermal or structural analysis, or automatic datasheet verification.
- Drawing OCR/vision extracts visible evidence and candidate parameters; it does not guarantee reconstruction of every drawing view, hidden geometry, GD&T, tolerance intent, or manufacturing requirements. Users must review the blueprint and generated dimensions.
- Single-image depth relief/lithophane is approximate and is not exact mechanical reconstruction.
- CuraEngine slicing requires a real compatible engine and printer/extruder definitions. A successful slice and mesh validation still require independent Cura preview and printer-specific review.
- The desktop `Approve Print` action is simulation-only; physical printer communication is not implemented.

## Documentation index

- [README](README.md) — project overview and local quick start.
- [Web platform setup](web/README.md) — frontend environment and data/session behavior.
- [Deployment guide](DEPLOYMENT.md) — Vercel, Railway, Supabase/PostgreSQL, private storage, and environment variables.
- [Work status](WORK_STATUS.md) — merged work, build state, warnings, and pending validation.
- [CAD Engine Reliability Guide](docs/CAD_ENGINE_RELIABILITY.md) — geometry contracts and limitations.
- [Drawing-to-CAD v1](docs/DRAWING_TO_CAD_V1.md) — extraction schema, supported features, provider setup, and limits.
- [Hardware Fit Check](docs/HARDWARE_FIT_CHECK.md) — preset confirmation and axis-aligned fit-check behavior.

## Safety and deployment notes

- Never commit `.env` files, database URLs, Firebase service-account credentials, CAD service tokens, private Blob tokens, or Razorpay secrets.
- Do not run database schema changes against an unverified target. Apply checked-in Prisma migrations as a controlled deployment step; do not use `prisma db push` as an automatic Vercel build command.
- Do not infer runtime health from a successful frontend build. Verify each external service independently before treating the whole application as operational.
