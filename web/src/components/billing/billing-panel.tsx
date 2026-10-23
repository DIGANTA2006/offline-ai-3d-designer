"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, CreditCard, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type CheckoutResponse = {
  subscriptionId?: string;
  keyId?: string;
  name?: string;
  description?: string;
  prefill?: { name?: string; email?: string; contact?: string };
  error?: string;
};
type RazorpaySuccess = { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string };
type RazorpayOptions = {
  key: string;
  subscription_id: string;
  name: string;
  description: string;
  prefill?: { name?: string; email?: string; contact?: string };
  theme: { color: string };
  handler: (response: RazorpaySuccess) => void | Promise<void>;
  modal?: { ondismiss?: () => void };
};
type RazorpayCheckout = { open: () => void; on: (event: string, handler: (response: { error?: { description?: string } }) => void) => void };
declare global { interface Window { Razorpay?: new (options: RazorpayOptions) => RazorpayCheckout } }
type BillingStatus = {
  role: string;
  adminAccess: boolean;
  billingConfigured: boolean;
  subscription: { tier: string; status: string; currentPeriodEnd: string | null; cancelAtPeriodEnd: boolean } | null;
  usageCount: number;
};

async function ensureCheckoutScript(): Promise<void> {
  if (window.Razorpay) return;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Razorpay Checkout could not be loaded. Check your internet connection and try again."));
    document.body.appendChild(script);
  });
  if (!window.Razorpay) throw new Error("Razorpay Checkout did not initialize. Please refresh and retry.");
}

export function BillingPanel() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/billing/status", { cache: "no-store", credentials: "same-origin" });
      const payload = await response.json().catch(() => ({})) as BillingStatus & { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Unable to load billing status.");
      setStatus(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load billing status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function startSubscription() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const createResponse = await fetch("/api/billing/subscribe", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const checkout = await createResponse.json().catch(() => ({})) as CheckoutResponse;
      if (!createResponse.ok || !checkout.subscriptionId || !checkout.keyId) {
        throw new Error(checkout.error ?? "Could not start the subscription checkout.");
      }
      await ensureCheckoutScript();
      const CheckoutConstructor = window.Razorpay;
      if (!CheckoutConstructor) throw new Error("Razorpay Checkout is unavailable. Refresh and try again.");
      const instance = new CheckoutConstructor({
        key: checkout.keyId,
        subscription_id: checkout.subscriptionId,
        name: checkout.name ?? "Offline AI 3D Designer",
        description: checkout.description ?? "Pro monthly subscription - ₹500/month",
        prefill: checkout.prefill,
        theme: { color: "#16a085" },
        handler: async (result) => {
          setBusy(true);
          try {
            const verifyResponse = await fetch("/api/billing/verify", {
              method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
              body: JSON.stringify(result),
            });
            const verification = await verifyResponse.json().catch(() => ({})) as { error?: string; active?: boolean; status?: string };
            if (!verifyResponse.ok) throw new Error(verification.error ?? "Payment could not be verified.");
            if (verification.active) setNotice("Payment verified. Your Pro subscription is active.");
            else setNotice("Payment details verified. Subscription activation is still pending with Razorpay; use Refresh status in a moment.");
            await refresh();
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Payment verification failed.");
          } finally {
            setBusy(false);
          }
        },
        modal: { ondismiss: () => setBusy(false) },
      });
      instance.on("payment.failed", (response) => {
        setError(response.error?.description ?? "Razorpay payment failed. You have not been granted paid access.");
        setBusy(false);
      });
      instance.open();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start checkout.");
      setBusy(false);
    }
  }

  async function cancelRenewal() {
    if (!window.confirm("Cancel automatic renewal? Your Pro access remains active until the current billing period ends.")) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/billing/cancel", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json().catch(() => ({})) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Could not cancel renewal.");
      setNotice("Automatic renewal has been scheduled to cancel at the end of this billing period.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not cancel renewal.");
    } finally {
      setBusy(false);
    }
  }

  const currentSubscription = status?.subscription;
  const activePro = currentSubscription?.tier === "PRO" && currentSubscription.status === "ACTIVE";
  const needsAttention = currentSubscription?.tier === "PRO" && ["PAST_DUE", "HALTED"].includes(currentSubscription.status);
  const date = currentSubscription?.currentPeriodEnd ? new Date(currentSubscription.currentPeriodEnd).toLocaleDateString("en-IN") : null;

  return (
    <div className="space-y-5">
      {error && <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
      {notice && <div role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300">{notice}</div>}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2"><CreditCard className="size-5 text-primary" /><CardTitle>Offline AI 3D Designer Pro</CardTitle></div>
          <CardDescription>Recurring subscription through Razorpay. Cancel renewal from this page at any time.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div><p className="text-4xl font-semibold">₹500 <span className="text-base font-normal text-muted-foreground">/ month</span></p><p className="mt-2 text-sm text-muted-foreground">CAD generation and STEP/STL downloads are enabled only while Pro is active. Payments are verified on the server.</p></div>
          {loading ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" /> Loading subscription status…</p> : status?.adminAccess ? (
            <div className="rounded-xl border border-primary/25 bg-primary/5 p-4"><p className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-5 text-primary" /> Administrator access</p><p className="mt-1 text-sm text-muted-foreground">Your verified ADMIN role bypasses subscription checkout for testing and administration.</p></div>
          ) : activePro ? (
            <div className="space-y-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4"><p className="flex items-center gap-2 font-semibold text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="size-5" /> Pro is active</p><p className="text-sm text-muted-foreground">{date ? `Current period ends ${date}.` : "Your subscription is active."}</p>{status?.subscription?.cancelAtPeriodEnd ? <p className="text-sm text-muted-foreground">Automatic renewal is scheduled to stop at the end of the current period.</p> : <Button variant="outline" onClick={cancelRenewal} disabled={busy}>Cancel automatic renewal</Button>}</div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Current plan: {status?.subscription?.status === "PAST_DUE" ? "Payment needs attention" : status?.subscription?.status === "HALTED" ? "Subscription halted" : "Free account — CAD generation locked"}.</p>
              {!status?.billingConfigured && <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">Payments are not configured yet. The site administrator must add the Razorpay API keys and the correct ₹500/month Plan ID in Vercel.</p>}
              {needsAttention && <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">Your existing subscription is {status?.subscription?.status.toLowerCase()}. To avoid duplicate charges, don&apos;t start another subscription. Resolve the existing payment in Razorpay or contact the site administrator.</p>}
              <Button className="w-full sm:w-auto" onClick={startSubscription} disabled={busy || !status?.billingConfigured || Boolean(needsAttention)}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <CreditCard className="size-4" />} Subscribe for ₹500/month</Button>
            </div>
          )}
          <Button variant="outline" onClick={() => { setLoading(true); void refresh(); }} disabled={loading || busy}><RefreshCw className="size-4" /> Refresh status</Button>
        </CardContent>
      </Card>
      <p className="text-sm text-muted-foreground">Need to return to your workspace? <Link className="font-medium text-primary underline" href="/dashboard">Go to dashboard</Link>.</p>
    </div>
  );
}