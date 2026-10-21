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

## Quick Deploy Checklist

### 1. Deploy Python Backend (Railway - Recommended)

```bash
# 1. Push to GitHub
git add python-backend/
git commit -m "Add Python CAD backend for Railway"
git push origin main

# 2. Go to Railway.app → New Project → Deploy from GitHub
#    - Select your repo
#    - Root Directory: repository root (leave blank/default)
#    - Dockerfile Path: python-backend/Dockerfile (build context must include src/)

# 3. Set Environment Variables in Railway:
#    APP_ENV=production
#    CAD_SERVICE_TOKEN=<same strong random token as Vercel>
#    CORS_ORIGINS=https://your-app.vercel.app
#    Do not set PORT manually; Railway injects it at runtime.


# 4. Get your Railway URL: https://cad-api-xxxx.railway.app
```

### 2. Deploy Frontend to Vercel

```bash
# 1. Go to Vercel → Import Project → Select GitHub repo
# 2. Configure:
#    - Framework Preset: Next.js
#    - Root Directory: repository root (leave blank/default)
#    - Build Command: cd web && npm run build
#    - Output Directory: web/.next
#    - Install Command: cd web && npm ci

# 3. Set Environment Variables in Vercel:
#    (Copy from web/.env.example and fill in)
#    - NEXT_PUBLIC_FIREBASE_* (from Firebase Console)
#    - FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY
#    - DATABASE_URL (Supabase pooled connection for the Vercel runtime)
#    - DIRECT_URL (Supabase direct/session connection for Prisma migrations)
#    - CAD_SERVICE_URL=https://your-railway-url.railway.app
#    - CAD_SERVICE_TOKEN (same value as Railway; generate locally with Python secrets.token_hex(32))
#    - INITIAL_ADMIN_EMAIL=your-email@example.com
#    - CRON_SECRET= (generate: openssl rand -hex 32)
#    - BLOB_READ_WRITE_TOKEN (from Vercel Blob storage)

# 4. Deploy!
```

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
| `CAD_SERVICE_URL` | ✅ | Your Railway/Render URL |
| `INITIAL_ADMIN_EMAIL` | ✅ | Your admin email |
| `CRON_SECRET` | ✅ | `openssl rand -hex 32` |
| `BLOB_READ_WRITE_TOKEN` | ✅ | Vercel Blob Storage |
| `NEXT_PUBLIC_APP_URL` | ✅ | Your Vercel URL |

### Railway (Python Backend)

| Variable | Required | Default |
|----------|----------|---------|
| `PORT` | ✅ | 8000 |
| `HOST` | ✅ | 0.0.0.0 |
| `CORS_ORIGINS` | ✅ | Your Vercel URL |

---

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
| POST | `/api/v1/ocr/extract` | Drawing → Spec (Phase 3+) |
| POST | `/api/v1/generate` | Spec → CAD files (Phase 3+) |

### Vercel Frontend (Proxied)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cad/text-to-cad` | Proxies to Python backend |
| GET | `/api/cad/health` | Proxies to Python backend |

---

## Troubleshooting

### "CAD Service Unavailable"
- Check Railway logs: `railway logs`
- Verify `CAD_SERVICE_URL` in Vercel matches Railway URL exactly
- Check CORS: Railway `CORS_ORIGINS` must include Vercel URL

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

## Next Steps (Phase 3+)

1. **OCR Pipeline**: Add Tesseract/OpenCV to Python backend
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
