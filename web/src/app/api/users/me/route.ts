import { NextResponse } from "next/server";
import { getFirebaseAdminAuth } from "@/lib/firebase/admin";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });

  try {
    const firebaseUser = await getFirebaseAdminAuth().getUser(user.firebaseUid);
    return NextResponse.json({
      user: {
        id: user.id,
        displayName: firebaseUser.displayName ?? user.displayName,
        email: firebaseUser.email ?? user.email,
        phone: firebaseUser.phoneNumber ?? user.phone,
        photoURL: firebaseUser.photoURL ?? user.photoURL,
        role: user.role,
        createdAt: user.createdAt.toISOString(),
        linkedProviders: firebaseUser.providerData.map((provider) => ({
          providerId: provider.providerId,
          email: provider.email,
          phoneNumber: provider.phoneNumber,
          displayName: provider.displayName,
        })),
      },
    });
  } catch (error) {
    console.error("Unable to load account profile:", error);
    return NextResponse.json({ error: "Could not load account profile." }, { status: 500 });
  }
}

export async function PATCH(request: Request) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });

  try {
    const body: unknown = await request.json();
    if (!body || typeof body !== "object" || !("displayName" in body) || typeof body.displayName !== "string") {
      return NextResponse.json({ error: "A display name is required." }, { status: 400 });
    }
    const displayName = body.displayName.trim();
    if (displayName.length < 1 || displayName.length > 80) {
      return NextResponse.json({ error: "Name must be between 1 and 80 characters." }, { status: 400 });
    }

    await getFirebaseAdminAuth().updateUser(user.firebaseUid, { displayName });
    const updated = await prisma.user.update({ where: { id: user.id }, data: { displayName } });
    return NextResponse.json({ ok: true, displayName: updated.displayName });
  } catch (error) {
    console.error("Unable to update account profile:", error);
    return NextResponse.json({ error: "Could not update your profile." }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });

  try {
    const account = await prisma.user.findUnique({
      where: { id: user.id },
      include: { subscription: true },
    });
    if (!account || account.deletedAt) return NextResponse.json({ error: "Account not found." }, { status: 404 });

    const subscription = account.subscription;
    const requiresCancellation = Boolean(
      subscription?.tier === "PRO" && ["ACTIVE", "PAST_DUE", "HALTED"].includes(subscription.status),
    );
    if (requiresCancellation && !subscription?.razorpaySubscriptionId) {
      return NextResponse.json({ error: "The paid subscription could not be verified for cancellation. Contact support before deleting this account." }, { status: 409 });
    }

    if (requiresCancellation && subscription?.razorpaySubscriptionId) {
      const keyId = process.env.RAZORPAY_KEY_ID;
      const keySecret = process.env.RAZORPAY_KEY_SECRET;
      if (!keyId || !keySecret) {
        return NextResponse.json({ error: "Billing cancellation is not configured. The account was not deleted; contact support." }, { status: 503 });
      }
      const response = await fetch(`https://api.razorpay.com/v1/subscriptions/${encodeURIComponent(subscription.razorpaySubscriptionId)}/cancel`, {
        method: "POST",
        headers: {
          Authorization: `Basic ${Buffer.from(`${keyId}:${keySecret}`).toString("base64")}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cancel_at_cycle_end: false }),
        cache: "no-store",
      });
      if (!response.ok) {
        console.error("Razorpay cancellation failed with status:", response.status);
        return NextResponse.json({ error: "Billing could not confirm subscription cancellation. The account was not deleted; please retry or contact support." }, { status: 502 });
      }
      await prisma.subscription.update({ where: { userId: user.id }, data: { status: "CANCELLED", cancelAtPeriodEnd: false } });
    }

    const now = new Date();
    const hardDeleteAt = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    await prisma.user.update({ where: { id: user.id }, data: { deletedAt: now, hardDeleteAt } });
    try {
      await getFirebaseAdminAuth().revokeRefreshTokens(user.firebaseUid);
    } catch (revokeError) {
      console.error("Could not revoke refresh tokens after account soft-delete:", revokeError);
    }

    const result = NextResponse.json({ ok: true, hardDeleteAt: hardDeleteAt.toISOString() });
    result.cookies.set("offline_ai_session", "", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 0,
      expires: new Date(0),
    });
    return result;
  } catch (error) {
    console.error("Unable to schedule account deletion:", error);
    return NextResponse.json({ error: "Could not schedule account deletion." }, { status: 500 });
  }
}