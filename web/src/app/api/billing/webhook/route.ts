import { createHmac, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RazorpayEntity = { id?: string; status?: string; current_start?: number | null; current_end?: number | null };
function secureHexEqual(received: string, expected: string): boolean {
  if (!/^[a-f0-9]{64}$/i.test(received) || !/^[a-f0-9]{64}$/i.test(expected)) return false;
  return timingSafeEqual(Buffer.from(received, "hex"), Buffer.from(expected, "hex"));
}
function dateFromEpoch(value: number | null | undefined): Date | undefined {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? new Date(value * 1000) : undefined;
}

export async function POST(request: Request) {
  const secret = process.env.RAZORPAY_WEBHOOK_SECRET?.trim();
  if (!secret) return NextResponse.json({ error: "Webhook secret is not configured." }, { status: 503 });
  const received = request.headers.get("x-razorpay-signature") ?? "";
  const raw = await request.text();
  const expected = createHmac("sha256", secret).update(raw).digest("hex");
  if (!secureHexEqual(received, expected)) return NextResponse.json({ error: "Invalid webhook signature." }, { status: 400 });

  try {
    const eventBody = JSON.parse(raw) as {
      event?: string;
      payload?: { subscription?: { entity?: RazorpayEntity } };
    };
    const event = eventBody.event ?? "";
    const entity = eventBody.payload?.subscription?.entity;
    if (!entity?.id) return NextResponse.json({ ok: true, ignored: true });

    let status: "ACTIVE" | "PAST_DUE" | "HALTED" | "CANCELLED" | "EXPIRED" | null = null;
    switch (event) {
      case "subscription.activated":
      case "subscription.charged":
      case "subscription.resumed": status = "ACTIVE"; break;
      case "subscription.pending": status = "PAST_DUE"; break;
      case "subscription.halted":
      case "subscription.paused": status = "HALTED"; break;
      case "subscription.cancelled": status = "CANCELLED"; break;
      case "subscription.completed": status = "EXPIRED"; break;
      default: return NextResponse.json({ ok: true, ignored: true });
    }

    const currentPeriodStart = dateFromEpoch(entity.current_start);
    const currentPeriodEnd = dateFromEpoch(entity.current_end);
    const updateData = {
      status,
      tier: status === "CANCELLED" || status === "EXPIRED" ? "FREE" as const : "PRO" as const,
      ...(event === "subscription.cancelled" ? { cancelAtPeriodEnd: false } : {}),
      ...(currentPeriodStart ? { currentPeriodStart } : {}),
      ...(currentPeriodEnd ? { currentPeriodEnd } : {}),
    };
    await prisma.subscription.updateMany({ where: { razorpaySubscriptionId: entity.id }, data: updateData });
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Razorpay webhook processing failed.", error);
    return NextResponse.json({ error: "Webhook event could not be processed." }, { status: 500 });
  }
}