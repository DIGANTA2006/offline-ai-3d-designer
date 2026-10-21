import { NextResponse } from "next/server";
import { getFirebaseAdminAuth } from "@/lib/firebase/admin";
import { prisma } from "@/lib/prisma";
import { getCurrentUser, SESSION_COOKIE_NAME } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";

export const runtime = "nodejs";
const SESSION_DURATION_MS = 5 * 24 * 60 * 60 * 1000;

/** Safe session diagnostic endpoint. It returns only the current user's own basic profile and role. */
export async function GET() {
  try {
    const user = await getCurrentUser();
    if (!user) return NextResponse.json(
      { authenticated: false, error: "No valid application session was found." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
    return NextResponse.json({
      authenticated: true,
      user: { id: user.id, email: user.email, displayName: user.displayName, role: user.role },
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "unknown";
    console.error("Session status check failed.", { code });
    return NextResponse.json({ authenticated: false, error: "Session status is temporarily unavailable." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }

  try {
    const body: unknown = await request.json();
    if (!body || typeof body !== "object" || !("idToken" in body) || typeof body.idToken !== "string") {
      return NextResponse.json({ error: "A Firebase ID token is required." }, { status: 400 });
    }
    const idToken = body.idToken;
    if (idToken.length > 20000) return NextResponse.json({ error: "Invalid ID token." }, { status: 400 });

    const auth = getFirebaseAdminAuth();
    const decoded = await auth.verifyIdToken(idToken, true);
    const firebaseUser = await auth.getUser(decoded.uid);
    if (firebaseUser.disabled) return NextResponse.json({ error: "This account is disabled." }, { status: 403 });

    const email = firebaseUser.email?.trim().toLowerCase() ?? null;
    const initialAdminEmail = process.env.INITIAL_ADMIN_EMAIL?.trim().toLowerCase();
    const bootstrapAdmin = Boolean(firebaseUser.emailVerified && email && initialAdminEmail && email === initialAdminEmail);
    const existing = await prisma.user.findUnique({ where: { firebaseUid: firebaseUser.uid } });
    if (existing?.deletedAt) {
      return NextResponse.json({ error: "This account is scheduled for deletion. Contact support to restore it." }, { status: 410 });
    }

    if (existing) {
      await prisma.user.update({
        where: { id: existing.id },
        data: {
          email,
          phone: firebaseUser.phoneNumber ?? null,
          displayName: firebaseUser.displayName ?? null,
          photoURL: firebaseUser.photoURL ?? null,
          role: bootstrapAdmin ? "ADMIN" : existing.role,
        },
      });
      await prisma.subscription.upsert({
        where: { userId: existing.id }, update: {},
        create: { userId: existing.id, tier: "FREE", status: "ACTIVE" },
      });
    } else {
      await prisma.user.create({
        data: {
          firebaseUid: firebaseUser.uid,
          email,
          phone: firebaseUser.phoneNumber ?? null,
          displayName: firebaseUser.displayName ?? null,
          photoURL: firebaseUser.photoURL ?? null,
          role: bootstrapAdmin ? "ADMIN" : "USER",
          subscription: { create: { tier: "FREE", status: "ACTIVE" } },
        },
      });
    }

    const sessionCookie = await auth.createSessionCookie(idToken, { expiresIn: SESSION_DURATION_MS });
    const response = NextResponse.json({ ok: true, redirectTo: "/dashboard" });
    response.cookies.set(SESSION_COOKIE_NAME, sessionCookie, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: Math.floor(SESSION_DURATION_MS / 1000),
    });
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch (error) {
    const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
    if (["auth/id-token-expired", "auth/invalid-id-token", "auth/id-token-revoked"].includes(code)) {
      return NextResponse.json({ error: "Your sign-in expired. Please sign in again." }, { status: 401 });
    }
    if (code === "P2002") {
      return NextResponse.json({ error: "This email address or phone number is already associated with another account." }, { status: 409 });
    }
    console.error("Unable to establish authenticated session:", { code: code || "unknown" });
    return NextResponse.json({ error: "Could not complete sign-in. Check Firebase and database configuration." }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
