import { NextResponse } from "next/server";
import { getFirebaseAdminAuth } from "@/lib/firebase/admin";
import { prisma } from "@/lib/prisma";
import { SESSION_COOKIE_NAME } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";

export const runtime = "nodejs";
const SESSION_DURATION_MS = 5 * 24 * 60 * 60 * 1000;

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
    if (idToken.length > 20000) {
      return NextResponse.json({ error: "Invalid ID token." }, { status: 400 });
    }

    const auth = getFirebaseAdminAuth();
    const decoded = await auth.verifyIdToken(idToken, true);
    const firebaseUser = await auth.getUser(decoded.uid);
    if (firebaseUser.disabled) return NextResponse.json({ error: "This account is disabled." }, { status: 403 });

    const email = firebaseUser.email?.trim().toLowerCase() ?? null;
    const initialAdminEmail = process.env.INITIAL_ADMIN_EMAIL?.trim().toLowerCase();
    const bootstrapAdmin = Boolean(email && initialAdminEmail && email === initialAdminEmail);
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
        where: { userId: existing.id },
        update: {},
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
    return response;
  } catch (error) {
    const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
    if (code === "auth/id-token-expired" || code === "auth/invalid-id-token" || code === "auth/id-token-revoked") {
      return NextResponse.json({ error: "Your sign-in expired. Please sign in again." }, { status: 401 });
    }
    if (code === "P2002") {
      return NextResponse.json({ error: "This email address or phone number is already associated with another account." }, { status: 409 });
    }
    console.error("Unable to establish authenticated session:", error);
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
  return response;
}