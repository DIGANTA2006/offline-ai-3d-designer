import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MONTHLY_PRICE_PAISE = 50_000;
const SUBSCRIPTION_CYCLES = 120;
type RazorpayPlan = { id?: string; period?: string; interval?: number; item?: { amount?: number; currency?: string; name?: string } };
type RazorpaySubscription = { id?: string; status?: string; plan_id?: string; short_url?: string };

function razorpayAuth(keyId: string, keySecret: string): string {
  return `Basic ${Buffer.from(`${keyId}:${keySecret}`).toString("base64")}`;
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  const user = await getCurrentUser().catch(() => null);
  if (!user) return NextResponse.json({ error: "Sign in before subscribing." }, { status: 401 });

  const keyId = process.env.RAZORPAY_KEY_ID?.trim();
  const keySecret = process.env.RAZORPAY_KEY_SECRET?.trim();
  const planId = process.env.RAZORPAY_PLAN_ID?.trim();
  if (!keyId || !keySecret || !planId || planId.startsWith("plan_replace_")) {
    return NextResponse.json({ error: "Razorpay billing is not configured. Add API keys and the ₹500/month Razorpay plan ID in Vercel." }, { status: 503 });
  }

  try {
    const current = await prisma.subscription.findUnique({ where: { userId: user.id } });
    if (current?.tier === "PRO" && ["ACTIVE", "PAST_DUE", "HALTED"].includes(current.status)) {
      const message = current.status === "ACTIVE"
        ? "Your Pro subscription is already active."
        : "Your existing Razorpay subscription needs attention. Update that subscription before starting another to avoid duplicate billing.";
      return NextResponse.json({ error: message }, { status: 409 });
    }

    const authHeader = razorpayAuth(keyId, keySecret);
    const planResponse = await fetch(`https://api.razorpay.com/v1/plans/${encodeURIComponent(planId)}`, {
      headers: { Authorization: authHeader }, cache: "no-store",
    });
    if (!planResponse.ok) {
      console.error("Razorpay plan validation failed with status:", planResponse.status);
      return NextResponse.json({ error: "Razorpay could not validate the configured plan. Check the plan ID and API-key mode." }, { status: 503 });
    }
    const plan = await planResponse.json() as RazorpayPlan;
    if (plan.id !== planId || plan.period !== "monthly" || plan.interval !== 1 || plan.item?.currency !== "INR" || plan.item.amount !== MONTHLY_PRICE_PAISE) {
      return NextResponse.json({ error: "The configured Razorpay plan must be exactly ₹500 INR every month." }, { status: 503 });
    }

    const createResponse = await fetch("https://api.razorpay.com/v1/subscriptions", {
      method: "POST",
      headers: { Authorization: authHeader, "Content-Type": "application/json" },
      body: JSON.stringify({
        plan_id: planId,
        total_count: SUBSCRIPTION_CYCLES,
        quantity: 1,
        customer_notify: 1,
        notes: { appUserId: user.id, appName: "offline-ai-3d-designer" },
      }),
      cache: "no-store",
    });
    const created = await createResponse.json().catch(() => ({})) as RazorpaySubscription & { error?: { description?: string } };
    if (!createResponse.ok || !created.id) {
      console.error("Razorpay subscription creation failed with status:", createResponse.status);
      return NextResponse.json({ error: created.error?.description ?? "Razorpay could not create a subscription. Check that Subscriptions is enabled for this account." }, { status: 502 });
    }

    await prisma.subscription.upsert({
      where: { userId: user.id },
      update: {
        tier: "PRO", status: "INCOMPLETE", razorpayPlanId: planId,
        razorpaySubscriptionId: created.id, currentPeriodStart: null,
        currentPeriodEnd: null, cancelAtPeriodEnd: false,
      },
      create: {
        userId: user.id, tier: "PRO", status: "INCOMPLETE",
        razorpayPlanId: planId, razorpaySubscriptionId: created.id,
      },
    });

    return NextResponse.json({
      subscriptionId: created.id,
      keyId,
      name: "Offline AI 3D Designer",
      description: "Pro monthly subscription - ₹500/month",
      prefill: {
        name: user.displayName ?? undefined,
        email: user.email ?? undefined,
        contact: user.phone ?? undefined,
      },
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Could not create Razorpay subscription.", error);
    return NextResponse.json({ error: "Could not start checkout. Retry shortly or check Vercel logs." }, { status: 500 });
  }
}