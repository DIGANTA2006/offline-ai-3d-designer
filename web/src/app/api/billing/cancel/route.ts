import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  const user = await getCurrentUser().catch(() => null);
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  const keyId = process.env.RAZORPAY_KEY_ID?.trim();
  const keySecret = process.env.RAZORPAY_KEY_SECRET?.trim();
  if (!keyId || !keySecret) return NextResponse.json({ error: "Billing cancellation is not configured." }, { status: 503 });

  try {
    const subscription = await prisma.subscription.findUnique({ where: { userId: user.id } });
    if (!subscription?.razorpaySubscriptionId || subscription.tier !== "PRO" || subscription.status !== "ACTIVE") {
      return NextResponse.json({ error: "There is no active Pro subscription to cancel." }, { status: 409 });
    }
    if (subscription.cancelAtPeriodEnd) return NextResponse.json({ ok: true, cancelAtPeriodEnd: true });
    const response = await fetch(`https://api.razorpay.com/v1/subscriptions/${encodeURIComponent(subscription.razorpaySubscriptionId)}/cancel`, {
      method: "POST",
      headers: {
        Authorization: `Basic ${Buffer.from(`${keyId}:${keySecret}`).toString("base64")}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ cancel_at_cycle_end: true }),
      cache: "no-store",
    });
    if (!response.ok) {
      console.error("Razorpay subscription cancellation failed with status:", response.status);
      return NextResponse.json({ error: "Razorpay could not schedule cancellation. Your subscription settings have not been changed." }, { status: 502 });
    }
    await prisma.subscription.update({ where: { userId: user.id }, data: { cancelAtPeriodEnd: true } });
    return NextResponse.json({ ok: true, cancelAtPeriodEnd: true });
  } catch (error) {
    console.error("Unable to cancel Razorpay renewal.", error);
    return NextResponse.json({ error: "Could not schedule cancellation. Retry later." }, { status: 500 });
  }
}