# Multi-Service Deployment Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        VERCEL (Frontend)                                │
│  https://your-app.vercel.app                                            │
│  ├── Next.js 15 App Router                                              │
│  ├── Authentication (Firebase Auth)                                     │
│  ├── Dashboard, Profile, Admin pages                                    │
│  ├── File Upload → Vercel Blob                                          │
│  └── API Routes → Proxy to Python Backend                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS /api/cad/*
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     PYTHON BACKEND (Railway/Render/Fly.io)             │
│  https://cad-api.railway.app (or your domain)                          │
│  ├── FastAPI + Uvicorn                                                  │
│  ├── build123d CAD Engine                                               │
│  ├── Natural Language → 3D (text-to-cad)                                │
│  ├── STEP/STL Export                                                    │
│  ├── Geometry Validation                                                │
│  └── Health Check /health                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Preview backend isolation (for branch testing)

Preview deployments must not silently reuse the Production CAD backend. Keep Production connected to the deployed `main` backend and configure a separate Preview service for any feature branch that needs isolated OCR/CAD testing.

1. In Railway, create a **separate Preview service/environment** connected to the branch being tested. Keep the existing Production service connected to `main`.
2. Set the service root directory to the **repository root** (not `python-backend`), so the Docker build can copy the shared `src/` package. In **Railway → Service → Settings → Build**, choose the Dockerfile builder and set Dockerfile path to `python-backend/Dockerfile`. Do not rely on the tracked `python-backend/railway.toml` alone for a new service: Railway's Config as Code is deprecated for new services. See [Railway's current Config as Code notice](https://docs.railway.com/config-as-code). Do not use Railpack/Nixpacks for this service: the Dockerfile installs Tesseract, Python OCR dependencies, and CAD runtime dependencies.
3. Configure the Preview Railway service with `APP_ENV=production` and a new random `CAD_SERVICE_TOKEN`. Keep the token server-side only. Let Railway inject `PORT`.
4. Open the Preview backend's `/health` URL. Confirm `"status": "healthy"`, `"cadAvailable": true`, `"cadRuntimeAvailable": true`, `"serviceTokenConfigured": true`, and `"ocrAvailable": true`. The Docker build now fails before deployment if either `build123d` or the OCR runtime cannot import. If `cadRuntimeAvailable` is false, inspect Railway build logs for `CAD runtime import check failed`; if `serviceTokenConfigured` is false, configure a server-only `CAD_SERVICE_TOKEN` on the backend. Do not proceed while the service reports `degraded`.

For visual blueprint extraction (needed for automatic model interpretation from the pixels, rather than only labelled OCR text), configure one provider on the same Railway Preview service:

- **Reachable Ollama server:** `DRAWING_VISION_PROVIDER=ollama`, `DRAWING_VISION_URL=<Ollama base URL>`, and `DRAWING_VISION_MODEL=<vision-capable model>` (for example `qwen2.5vl:7b`). The service appends `/api/chat`.
- **OpenAI-compatible vision API:** `DRAWING_VISION_PROVIDER=openai_compatible`, `DRAWING_VISION_URL=<provider base URL ending in /v1>`, `DRAWING_VISION_MODEL=<vision model>`, and the server-only `DRAWING_VISION_API_KEY` if required. The provider must support image inputs and strict JSON-schema responses.

Do not use `localhost` for a model server running on your laptop; from Railway, localhost is the Railway container. After configuration, `/health` should show `"drawingVisionAvailable": true`. If it is false or the endpoint rejects the schema, extraction falls back to explicitly labelled text and may leave the body/dimensions unresolved; that is not full visual reconstruction. Full variable examples and the v1 support matrix are in `docs/DRAWING_TO_CAD_V1.md`.
5. In **Vercel → Project → Settings → Environment Variables**, add `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW` scoped to **Preview**. Use the new Railway Preview URL and the matching token from step 3. Do not replace Production's `CAD_SERVICE_URL` or `CAD_SERVICE_TOKEN`.
6. Redeploy the Vercel Preview from the feature branch. The Preview routes now require the Preview-specific variables and check backend OCR readiness before accepting an OCR request.

Use an isolated test account and verify that Preview's database and private Blob storage are not unintentionally sharing live user data. Before merging a future feature branch, test OCR extraction, reviewed CAD generation, private STEP/STL downloads, and the relevant refusal/error paths.

---

## Quick Deploy Checklist

### 1. Deploy Python Backend (Railway - Recommended)

For a **Production release**, deploy from `main` only after the pull request has been reviewed and approved. For PR testing, follow the isolated Preview deployment section above; do not push unreviewed feature code into `main`.

```bash
# Backend build context is the repository root so the image can copy both src/ and python-backend/.
# Configure the Railway service's Dockerfile builder with path: python-backend/Dockerfile.
# Do not force Nixpacks; OCR needs the system tesseract-ocr package installed by this Dockerfile.

# Set Environment Variables in Railway:
#    APP_ENV=production
#    CAD_SERVICE_TOKEN=<same strong random token as Vercel>
#    CORS_ORIGINS=https://your-app.vercel.app
#    Do not set PORT manually; Railway injects it at runtime.


# 4. Get your Railway URL: https://cad-api-xxxx.railway.app
```

### 2. Deploy Frontend to Vercel

Configure the Vercel project for the repository's actual monorepo layout:

| Setting | Value |
|---|---|
| Framework Preset | Next.js |
| Root Directory | `web` |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `.next` |

The root directory is already `web`, so commands must **not** start with `cd web &&`. The Next.js build writes to `web/.next`; from Vercel's configured root this directory is `.next`. Keep `web/vercel.json` aligned with these commands and output directory. If the Output Directory override is enabled in the dashboard, enter the literal value `.next` (not the UI label `Next.js default`).

Set Environment Variables in Vercel, using `web/.env.example` as the checklist:

- `NEXT_PUBLIC_FIREBASE_*` (from Firebase Console)
- `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY`
- `DATABASE_URL` (Supabase pooled connection for the Vercel runtime)
- `DIRECT_URL` (direct/session connection for Prisma migrations)
- `CAD_SERVICE_URL` and `CAD_SERVICE_TOKEN` for Production
- `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW` for isolated Preview deployments
- `INITIAL_ADMIN_EMAIL` (must match a verified Firebase email)
- `CRON_SECRET`
- `PRIVATE_BLOB_READ_WRITE_TOKEN` from a Vercel Blob store configured as Private
- Razorpay variables only when recurring checkout is enabled

Never put service tokens, database credentials, Firebase service-account keys, private Blob tokens, or Razorpay secrets in `NEXT_PUBLIC_*` variables or commit them to Git.

The Vercel deployment log for `main` commit `f6a0449` confirmed `npm ci`, Prisma Client generation, Next.js build, serverless-function generation, and deployment completion. This is a build/deployment check, not an end-to-end runtime test.

### 3. Connect Them

After both deploy:
1. Copy Railway URL → Vercel `CAD_SERVICE_URL` env var
2. Set the same `CAD_SERVICE_TOKEN` in Vercel and Railway; keep it server-only.
3. Set Railway `CORS_ORIGINS` to the exact Vercel origin only if calling the backend directly from a browser.
4. Redeploy both services

---

## Environment Variables Reference

### Vercel (Frontend)

| Variable | Required | Source |
|----------|----------|--------|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | ✅ | Firebase Console |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | ✅ | Firebase Console |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | ✅ | Firebase Console |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | ✅ | Firebase Console |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | ✅ | Firebase Console |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | ✅ | Firebase Console |
| `FIREBASE_PROJECT_ID` | ✅ | Firebase Console (Service Account) |
| `FIREBASE_CLIENT_EMAIL` | ✅ | Firebase Console (Service Account) |
| `FIREBASE_PRIVATE_KEY` | ✅ | Firebase Console (Service Account) |
| `DATABASE_URL` | ✅ | Supabase/Neon/Railway PostgreSQL |
| `CAD_SERVICE_URL` | ✅ Production/local | Production backend URL; not used as a Preview fallback |
| `CAD_SERVICE_TOKEN` | ✅ Production/local | Server-only token matching the Production/local backend |
| `CAD_SERVICE_URL_PREVIEW` | ✅ Preview | Dedicated feature-branch backend URL; must report `ocrAvailable: true` |
| `CAD_SERVICE_TOKEN_PREVIEW` | ✅ Preview | Server-only token matching the Preview backend |
| `INITIAL_ADMIN_EMAIL` | ✅ | Your admin email |
| `CRON_SECRET` | ✅ | `openssl rand -hex 32` |
| `BLOB_READ_WRITE_TOKEN` | Optional | Existing public assets only |
| `PRIVATE_BLOB_READ_WRITE_TOKEN` | Yes | Separate Vercel Blob store configured with Private access |
| `NEXT_PUBLIC_APP_URL` | ✅ | Your Vercel URL |

### Railway (Python Backend)

| Variable | Required | Default |
|----------|----------|---------|
| `PORT` | ✅ | 8000 |
| `HOST` | ✅ | 0.0.0.0 |
| `CORS_ORIGINS` | ✅ | Your Vercel URL |

---


### Private user files (important)

Create a **separate Vercel Blob store with access set to Private** and configure its token in Vercel as `PRIVATE_BLOB_READ_WRITE_TOKEN`. The web application passes that token explicitly when saving CAD exports and drawing uploads; do not place it in a `NEXT_PUBLIC_*` variable and never share it in support messages. The current server upload endpoint accepts up to 3 MiB per batch to stay below the Vercel Function body limit. Larger files need a dedicated authenticated direct-upload flow.

Files uploaded before this patch to the previous **public** Blob store remain publicly readable by URL. Changing code does not convert existing objects to private. Review that store and delete or migrate sensitive legacy uploads separately.
## Local Development

### Terminal 1: Python Backend
```bash
cd python-backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # Edit with local values
uvicorn main:app --reload --port 8000
```

### Terminal 2: Next.js Frontend
```bash
cd web
npm install
cp .env.example .env.local  # Edit with local values
npm run dev
```

### Test Integration
```bash
# Health check
curl http://localhost:8000/health

# Text-to-CAD
curl -X POST http://localhost:8000/api/v1/text-to-cad \
  -H "Content-Type: application/json" \
  -d '{"text": "40x20x10mm box with 5mm hole", "userId": "test", "unitSystem": "mm", "exportFormats": ["step", "stl"]}'
```

---

## API Endpoints

### Python Backend

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/text-to-cad` | Natural language → 3D model |
| POST | `/api/v1/ocr/extract` | Extract visible drawing text/annotations using Tesseract + PyMuPDF |
| POST | `/api/v1/generate` | Generate STEP/STL from reviewed descriptions for supported part types |

### Vercel Frontend (Proxied)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cad/text-to-cad` | Proxies to Python backend |
| GET | `/api/cad/health` | Proxies to Python backend |

---

## Troubleshooting

### Vercel cannot find `web` or reports `cd: web: No such file or directory`

- Check that Root Directory is `web`.
- With that Root Directory, use `npm ci` and `npm run build`; do not prefix either command with `cd web &&`.

### Vercel reports `NEXT_OUTPUT_DIR_MISSING`

- Keep Root Directory set to `web`.
- Set Output Directory to the literal `.next` when the dashboard override is enabled.
- Do not enter `web/.next` (that would duplicate the configured root) or the UI label `Next.js default` as a literal directory.

### OCR still returns "OCR not yet implemented"
- Confirm the Vercel deployment is using the intended current backend and that `CAD_SERVICE_URL` (Production) or `CAD_SERVICE_URL_PREVIEW` (Preview) points to it.
- Do not work around a Preview readiness problem by pointing Preview at the Production backend.
- Check the dedicated Preview Railway service's `/health` endpoint; it must report `status: "healthy"`, `cadAvailable: true`, `cadRuntimeAvailable: true`, `serviceTokenConfigured: true`, and `ocrAvailable: true`.
- In Railway Build settings, use repository-root build context and Dockerfile path `python-backend/Dockerfile`; check the build log for the Docker smoke-test line `CAD_RUNTIME_AVAILABLE=true OCR_AVAILABLE=true`.
- In Vercel Preview variables, set `CAD_SERVICE_URL_PREVIEW` and `CAD_SERVICE_TOKEN_PREVIEW`, then redeploy the latest Preview.
- The Next.js OCR route now checks the backend health contract first. If an older backend is reached, it should return a clear readiness error rather than sending the drawing to the mock endpoint.

### `cadAvailable: false` or status is degraded
- Read the diagnostic fields: `cadRuntimeAvailable` distinguishes a build123d import failure from `serviceTokenConfigured: false`.
- If CAD runtime is false, inspect Railway logs for `CAD runtime import check failed`. The Dockerfile installs the project package without the desktop-only dependencies and executes a build-time import smoke test.
- If the token is not configured, add a new strong `CAD_SERVICE_TOKEN` on Railway and the matching server-only `CAD_SERVICE_TOKEN_PREVIEW` in Vercel Preview.

### "CAD Service Unavailable"
- Check Railway logs: `railway logs`
- Confirm the appropriate Vercel environment URL is set: Preview uses `CAD_SERVICE_URL_PREVIEW`; Production uses `CAD_SERVICE_URL`.
- Confirm the matching server-only service token is set in both environments.

### "Prisma Client Not Generated"
- Vercel build runs `prisma generate && next build` automatically
- Check Vercel build logs for Prisma errors

### "Firebase Admin Init Failed"
- Verify `FIREBASE_PRIVATE_KEY` has actual newlines (`\n` in env var)
- Check service account has proper permissions

### "Database Connection Failed"
- Verify `DATABASE_URL` format: `postgresql://user:pass@host:port/db?pgbouncer=true`
- Run `npx prisma migrate deploy` in Vercel build or locally

---

## Cost Estimate (Monthly)

| Service | Plan | Cost |
|---------|------|------|
| Vercel | Hobby/Pro | Free - $20 |
| Railway | Starter | $5 |
| PostgreSQL (Supabase/Neon) | Free tier | Free |
| Firebase Auth | Spark | Free |
| Vercel Blob | Pay-as-you-go | ~$0-5 |

**Total: ~$5-25/month**

---

## Further work

1. Validate extraction quality across representative multi-page engineering PDFs and raster drawings; OCR is text/annotation extraction, not complete drawing-view reconstruction.
2. **File Storage**: S3/R2 for generated STEP/STL files
3. **Job Queue**: Redis + Celery for async processing
4. **WebSocket**: Real-time progress updates
5. **Billing**: Razorpay webhooks for Pro tier

---

## Support

- Railway Docs: https://docs.railway.app
- Vercel Docs: https://vercel.com/docs
- Firebase Docs: https://firebase.google.com/docs
- Prisma Docs: https://www.prisma.io/docs
