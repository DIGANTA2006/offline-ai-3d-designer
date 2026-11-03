/**
 * Shared subscription-entitlement policy.
 *
 * Keep this module pure so the exact same rule can be exercised in CI without
 * a database connection.
 */
export type SubscriptionSnapshot = {
  tier: string;
  status: string;
} | null | undefined;

/** A paid subscription grants access only while its tier is PRO and status ACTIVE. */
export function hasActiveProSubscription(subscription: SubscriptionSnapshot): boolean {
  return subscription?.tier === "PRO" && subscription.status === "ACTIVE";
}

/** Administrator access is explicit; all other users need an active Pro subscription. */
export function hasPaidFeatureAccess(role: string, subscription: SubscriptionSnapshot): boolean {
  return role === "ADMIN" || hasActiveProSubscription(subscription);
}
