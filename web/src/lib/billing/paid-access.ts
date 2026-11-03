import { prisma } from "@/lib/prisma";
import { hasPaidFeatureAccess } from "@/lib/billing/subscription-policy";

export type PaidFeatureUser = {
  id: string;
  role: string;
};

export type PaidFeatureAccess =
  | { allowed: true }
  | { allowed: false; status: 402 | 503; message: string };

/**
 * Shared server-side entitlement check for paid application routes.
 * Admins bypass subscription lookup; other users require tier=PRO and status=ACTIVE.
 */
export async function checkPaidFeatureAccess(
  user: PaidFeatureUser,
  deniedMessage: string,
): Promise<PaidFeatureAccess> {
  if (user.role === "ADMIN") return { allowed: true };

  try {
    const subscription = await prisma.subscription.findUnique({
      where: { userId: user.id },
      select: { tier: true, status: true },
    });

    if (hasPaidFeatureAccess(user.role, subscription)) return { allowed: true };
    return { allowed: false, status: 402, message: deniedMessage };
  } catch (error) {
    console.error("Paid feature subscription check failed.", error);
    return {
      allowed: false,
      status: 503,
      message: "Subscription service is unavailable. Please retry shortly.",
    };
  }
}
