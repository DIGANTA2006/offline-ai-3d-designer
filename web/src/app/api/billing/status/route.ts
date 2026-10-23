import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser().catch(() => null);
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  try {
    const [subscription, usage] = await Promise.all([
      prisma.subscription.findUnique({ where: { userId: user.id } }),
      prisma.usageRecord.findUnique({
        where: { userId_action_periodStart: {
          userId: user.id,
          action: "generation",
          periodStart: new Date(Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), 1)),
        } },
        select: { count: true },
      }),
    ]);
    const billingConfigured = Boolean(
      process.env.RAZORPAY_KEY_ID?.trim() &&
      process.env.RAZORPAY_KEY_SECRET?.trim() &&
      process.env.RAZORPAY_PLAN_ID?.trim() &&
      !process.env.RAZORPAY_PLAN_ID?.trim().startsWith("plan_replace_"),
    );
    return NextResponse.json({
      role: user.role,
      adminAccess: user.role === "ADMIN",
      billingConfigured,
      subscription: subscription ? {
        tier: subscription.tier,
        status: subscription.status,
        currentPeriodEnd: subscription.currentPeriodEnd?.toISOString() ?? null,
        cancelAtPeriodEnd: subscription.cancelAtPeriodEnd,
      } : null,
      usageCount: usage?.count ?? 0,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Unable to load billing status.", error);
    return NextResponse.json({ error: "Could not load subscription status." }, { status: 503 });
  }
}