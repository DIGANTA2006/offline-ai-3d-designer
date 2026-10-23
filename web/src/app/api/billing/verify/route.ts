import { createHmac, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RazorpaySubscription = {
  id?: string; status?: string; plan_id?: string;
  current_start?: number | null; current_end?: number | null;
  notes?: Record<string, string>;
};
function safeSignatureEqual(received: string, expected: string): boolean {
  if (!/^[a-f0-9]{64}$/i.test(received) || !/^[a-f0-9]{64}$/i.test(expected)) return false;
  return timingSafeEqual(Buffer.from(received, "hex"), Buffer.from(expected, "hex"));
}
function mapStatus(status: string | undefined): "ACTIVE" | "PAST_DUE" | "HALTED" | "CANCELLED" | "EXPIRED" | "INCOMPLETE" {
  switch (status) {
    case "active": return "ACTIVE";
    case "pending": return "PAST_DUE";
    case "halted": case "paused": return "HALTED";
    case "cancelled": return "CANCELLED";
    case "completed": case "expired": return "EXPIRED";
    default: return "INCOMPLETE";
  }
}
function asDate(value: number | null | undefined): Date | undefined {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? new Date(value * 1000) : undefined;
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  const user = await getCurrentUser().catch(() => null);
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  const keyId = process.env.RAZORPAY_KEY_ID?.trim();
  const keySecret = process.env.RAZORPAY_KEY_SECRET?.trim();
  const planId = process.env.RAZORPAY_PLAN_ID?.trim();
  if (!keyId || !keySecret || !planId) return NextResponse.json({ error: "Billing is not configured." }, { status: 503 });

  try {
    const body: unknown = await request.json();
    if (!body || typeof body !== "object") return NextResponse.json({ error: "Invalid payment verification request." }, { status: 400 });
    const input = body as Record<string, unknown>;
    const paymentId = typeof input.razorpay_payment_id === "string" ? input.razorpay_payment_id : "";
    const subscriptionId = typeof input.razorpay_subscription_id === "string" ? input.razorpay_subscription_id : "";
    const signature = typeof input.razorpay_signature === "string" ? input.razorpay_signature : "";
    if (!paymentId || !subscriptionId || !signature) return NextResponse.json({ error: "Razorpay payment details are incomplete." }, { status: 400 });

    const local = await prisma.subscription.findUnique({ where: { userId: user.id } });
    if (!local || local.razorpaySubscriptionId !== subscriptionId || local.razorpayPlanId !== planId) {
      return NextResponse.json({ error: "This payment does not match the subscription started for your account." }, { status: 409 });
    }
    const expected = createHmac("sha256", keySecret).update(`${paymentId}|${subscriptionId}`).digest("hex");
    if (!safeSignatureEqual(signature, expected)) return NextResponse.json({ error: "Razorpay payment signature could not be verified." }, { status: 400 });

    const response = await fetch(`https://api.razorpay.com/v1/subscriptions/${encodeURIComponent(subscriptionId)}`, {
      headers: { Authorization: `Basic ${Buffer.from(`${keyId}:${keySecret}`).toString("base64")}` },
      cache: "no-store",
    });
    const remote = await response.json().catch(() => ({})) as RazorpaySubscription;
    if (!response.ok || remote.id !== subscriptionId || remote.plan_id !== planId || remote.notes?.appUserId !== user.id) {
      console.error("Razorpay subscription could not be confirmed for the signed-in user.", { status: response.status });
      return NextResponse.json({ error: "Razorpay has not confirmed this subscription yet. Refresh billing status shortly." }, { status: 502 });
    }

    const mapped = mapStatus(remote.status);
    const currentPeriodStart = asDate(remote.current_start);
    const currentPeriodEnd = asDate(remote.current_end);
    await prisma.subscription.update({
      where: { userId: user.id },
      data: {
        status: mapped,
        tier: mapped === "CANCELLED" || mapped === "EXPIRED" ? "FREE" : "PRO",
        ...(currentPeriodStart ? { currentPeriodStart } : {}),
        ...(currentPeriodEnd ? { currentPeriodEnd } : {}),
      },
    });
    return NextResponse.json({ ok: true, status: mapped, active: mapped === "ACTIVE" }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Razorpay payment verification failed.", error);
    return NextResponse.json({ error: "Could not verify payment. Check billing status or contact support before retrying payment." }, { status: 500 });
  }
}