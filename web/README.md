# Offline AI 3D Designer — Web Platform

This Next.js 15 application is being built beside the existing Python CAD engine. The excluded Xbox/XboxGames directory is not used by this web setup script.

## Requirements

- Node.js 20.9+ and npm
- PostgreSQL
- A Firebase project with Google, Email/Password, and Phone sign-in providers enabled
- Firebase Admin service-account credentials for server-side session verification

## Phase 2 setup

1. Copy values from `.env.example` into `.env` and fill in all `NEXT_PUBLIC_FIREBASE_*` values from Firebase project settings.
2. Set server-only Firebase Admin values: `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, and `FIREBASE_PRIVATE_KEY`. For the private key, preserve newlines as `\n` in the `.env` file.
3. Set `DATABASE_URL` to the Supabase pooled connection string for the Vercel runtime, and `DIRECT_URL` to a direct or session-pooler connection string for Prisma migrations. Copy the exact strings from Supabase Connect; URL-encode special password characters.
4. Optionally set `INITIAL_ADMIN_EMAIL` to the exact, verified email address that should receive the initial ADMIN role. This is server-only; the browser cannot assign itself a role.
5. Set a long random `CRON_SECRET` for the account deletion cleanup endpoint. Configure the same secret in deployment.
6. Configure `CAD_SERVICE_URL` and the same random `CAD_SERVICE_TOKEN` in the web service and Python CAD service. The token must never use a `NEXT_PUBLIC_` prefix.
7. In Firebase Console > Authentication > Settings, set authorized domains for local and deployed origins. Under Sign-in method, enable Google, Email/Password, and Phone; configure phone test numbers for safe development testing.
8. Run `npm run prisma:generate` then `npx prisma migrate deploy` after confirming both database URLs point to the intended database. The checked-in migrations create the PostgreSQL tables; do not run migrations against an unverified production database.
9. Run `npm run dev` and open `http://localhost:3000`.

## Authentication and sessions

- Firebase client SDK performs Google popup, email/password, and phone OTP sign-in.
- The server validates the Firebase ID token, synchronizes a minimal user record, and issues a 5-day HTTP-only `offline_ai_session` cookie.
- Server-rendered dashboard, profile, and admin routes validate the session using Firebase Admin and read the role from PostgreSQL.
- Account deletion cancels a known active Pro Razorpay subscription immediately before soft deletion. If cancellation cannot be confirmed, deletion is stopped.
- Soft-deleted accounts are inaccessible immediately and receive a hard-delete deadline 30 days later. The `/api/cron/account-deletion` route must be invoked daily using the configured bearer `CRON_SECRET`; `vercel.json` configures a daily Vercel cron. For non-Vercel hosting, set up an equivalent scheduler.

## Important

The environment template contains placeholders, not working credentials. Put local web variables in `web/.env.local` or `web/.env`. Do not commit `.env`, database URLs, Firebase service-account keys, CAD service tokens, or Razorpay secrets. Set provider credentials in the deployment secret manager. Phase 2 adds authentication/account management; CAD processing, billing checkout/webhooks, upload processing, and paid-tier enforcement are delivered in later phases.
