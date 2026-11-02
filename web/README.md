# Offline AI 3D Designer — Web Platform

This is the Next.js 15 web platform paired with the repository's Python FastAPI CAD service. The hosted application uses Firebase Authentication, PostgreSQL through Prisma, private Vercel Blob storage, and the authenticated CAD-service API. The excluded Xbox/XboxGames directory is not used by this web setup.

## Requirements

- Node.js 20.9+ and npm
- PostgreSQL
- A Firebase project with Google, Email/Password, and Phone sign-in providers enabled
- Firebase Admin service-account credentials for server-side session verification

## Setup

1. Copy values from `.env.example` into `.env` and fill in all `NEXT_PUBLIC_FIREBASE_*` values from Firebase project settings.
2. Set server-only Firebase Admin values: `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, and `FIREBASE_PRIVATE_KEY`. For the private key, preserve newlines as `\n` in the `.env` file.
3. Set `DATABASE_URL` to the Supabase pooled connection string for the Vercel runtime, and `DIRECT_URL` to a direct or session-pooler connection string for Prisma migrations. Copy the exact strings from Supabase Connect; URL-encode special password characters.
4. Optionally set `INITIAL_ADMIN_EMAIL` to the exact, verified email address that should receive the initial ADMIN role. This is server-only; the browser cannot assign itself a role.
5. Set a long random `CRON_SECRET` for the account deletion cleanup endpoint. Configure the same secret in deployment.
6. Configure `CAD_SERVICE_URL` and the same random `CAD_SERVICE_TOKEN` in the web service and Python CAD service. The token must never use a `NEXT_PUBLIC_` prefix.
7. In Firebase Console > Authentication > Settings, set authorized domains for local and deployed origins. Under Sign-in method, enable Google, Email/Password, and Phone; configure phone test numbers for safe development testing.
8. Run `npm run prisma:generate` then `npx prisma migrate deploy` after confirming both database URLs point to the intended database. The checked-in migrations create the PostgreSQL tables; do not run migrations against an unverified production database.
9. Run `npm run dev` and open `http://localhost:3000`.

For Vercel, set **Root Directory** to `web`, Install Command to `npm ci`, Build Command to `npm run build`, and Output Directory to `.next`. Do not prefix commands with `cd web &&` when the Root Directory is already `web`. See the repository-root `DEPLOYMENT.md` for Railway/Preview isolation and the full environment-variable checklist.

## Authentication and sessions

- Firebase client SDK performs Google popup, email/password, and phone OTP sign-in.
- The server validates the Firebase ID token, synchronizes a minimal user record, and issues a 5-day HTTP-only `offline_ai_session` cookie.
- Server-rendered dashboard, profile, and admin routes validate the session using Firebase Admin and read the role from PostgreSQL.
- Account deletion cancels a known active Pro Razorpay subscription immediately before soft deletion. If cancellation cannot be confirmed, deletion is stopped.
- Soft-deleted accounts are inaccessible immediately and receive a hard-delete deadline 30 days later. The `/api/cron/account-deletion` route must be invoked daily using the configured bearer `CRON_SECRET`; `vercel.json` configures a daily Vercel cron. For non-Vercel hosting, set up an equivalent scheduler.

## Important

The environment template contains placeholders, not working credentials. Put local web variables in `web/.env.local` or `web/.env`. Do not commit `.env`, database URLs, Firebase service-account keys, CAD service tokens, or Razorpay secrets. Set provider credentials in the deployment secret manager. Razorpay recurring subscriptions are integrated for the ₹500/month Pro plan. Only users with an active verified subscription can generate CAD; ADMIN accounts bypass billing. Before enabling checkout, create a Razorpay Subscriptions Plan for INR 500 per month and set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_PLAN_ID, and RAZORPAY_WEBHOOK_SECRET in Vercel. Configure the Razorpay webhook at https://YOUR-PRODUCTION-DOMAIN/api/billing/webhook for subscription.activated, subscription.charged, subscription.pending, subscription.halted, subscription.paused, subscription.resumed, subscription.cancelled, and subscription.completed.

## Project storage retention

- PDF page rendering, OCR preprocessing, and vision image preparation are in-memory; CAD exporters use scoped `tempfile.TemporaryDirectory` contexts. Scratch STEP/STL files are removed after success or failure.
- Persisted project JSON is compacted to remove Base64 exports, data URLs, and raw mesh/vertex/face arrays. Array placeholders preserve source/OCR indexes instead of shifting them when a heavy payload is stripped.
- Each project keeps its two newest **unprotected** generated output versions; each version's STEP/STL files are one output pair. Protected versions remain until manually deleted.
- The Free plan allows one saved project. Active Pro subscriptions and ADMIN accounts have unlimited projects.
- Projects are never pruned automatically. Users explicitly delete a project; queued/processing projects cannot be deleted while work is active.
- Each project retains its two newest unprotected generated output versions; protected versions remain until manually deleted. Failed text-to-CAD attempts run best-effort cleanup so failed jobs do not leave unnecessary output records.
- Export Protect/Delete controls are on project details. Mark/unmark Important is per project. Cleanup failures are logged and surfaced as warnings instead of being silently reported as successful.
- Run `npm run test:retention` for pure policy tests without Supabase or Vercel Blob credentials.
