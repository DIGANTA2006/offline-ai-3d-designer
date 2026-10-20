"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getAuth, signOut } from "firebase/auth";
import { LogOut, LoaderCircle } from "lucide-react";
import { getFirebaseClientApp } from "@/lib/firebase/client";
import { Button } from "@/components/ui/button";

export function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleSignOut() {
    setBusy(true);
    try {
      await fetch("/api/auth/session", { method: "DELETE", credentials: "same-origin" });
    } catch {
      // Continue to client sign-out and navigation if the network is unavailable.
    }
    try {
      await signOut(getAuth(getFirebaseClientApp()));
    } catch {
      // Clearing the server cookie is the security boundary; client sign-out is best-effort.
    }
    router.replace("/login");
    router.refresh();
  }

  return <Button type="button" variant="outline" onClick={handleSignOut} disabled={busy}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <LogOut className="size-4" />} Sign out</Button>;
}