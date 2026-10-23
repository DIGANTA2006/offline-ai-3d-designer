"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  GoogleAuthProvider,
  RecaptchaVerifier,
  createUserWithEmailAndPassword,
  getAuth,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  signInWithPhoneNumber,
  signInWithPopup,
  updateProfile,
  type ConfirmationResult,
} from "firebase/auth";
import { ArrowRight, CheckCircle2, Globe, LoaderCircle, LockKeyhole, Mail, Phone, RotateCcw, UserRound } from "lucide-react";
import { getFirebaseClientApp } from "@/lib/firebase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = { mode: "login" | "signup" };

function explainAuthError(error: unknown): string {
  const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
  const messages: Record<string, string> = {
    "auth/invalid-credential": "Email/password or sign-in details were not accepted.",
    "auth/invalid-api-key": "Firebase rejected this app's API key. Check the web API key and its API restrictions.",
    "auth/operation-not-allowed": "This sign-in method is disabled. Enable it in Firebase Console under Authentication and Sign-in method.",
    "auth/unauthorized-domain": "This site's domain is not authorized. Add the exact Vercel hostname under Firebase Authentication Settings and Authorized domains.",
    "auth/app-not-authorized": "Firebase rejected this application's configuration. Check the API key, Firebase project and authorized domain.",
    "auth/popup-blocked": "The browser blocked the Google sign-in popup. Allow popups or use email/password.",
    "auth/invalid-app-credential": "Firebase could not verify this app. Check authorized domains and phone reCAPTCHA settings.",
    "auth/missing-app-credential": "Phone verification is missing a valid reCAPTCHA credential. Refresh and retry phone verification.",
    "auth/quota-exceeded": "Firebase has exhausted the quota for this authentication request. Check Firebase usage and try later.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/user-disabled": "This account has been disabled.",
    "auth/user-not-found": "No account was found for those details.",
    "auth/wrong-password": "Email/password or sign-in details were not accepted.",
    "auth/email-already-in-use": "An account already exists for this email address.",
    "auth/weak-password": "Choose a stronger password with at least 8 characters.",
    "auth/popup-closed-by-user": "The Google sign-in window was closed before completing sign-in.",
    "auth/too-many-requests": "Too many attempts. Wait a while and try again.",
    "auth/invalid-phone-number": "Enter the phone number in international format, for example +919876543210.",
    "auth/invalid-verification-code": "That SMS code is not correct. Check it and try again.",
    "auth/code-expired": "That SMS code has expired. Request a new code.",
    "auth/captcha-check-failed": "Phone verification could not verify this browser. Refresh and try again.",
  };
  if (code in messages) return messages[code];
  if (error instanceof Error && error.message) return error.message;
  return "Sign-in could not be completed. Check your Firebase configuration and try again.";
}

async function createServerSession(idToken: string): Promise<void> {
  const response = await fetch("/api/auth/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ idToken }),
  });
  const payload = (await response.json().catch(() => ({}))) as { error?: string };
  if (!response.ok) throw new Error(payload.error ?? "The server could not establish a secure session.");
}

export function AuthPanel({ mode }: Props) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [smsCode, setSmsCode] = useState("");
  const [confirmation, setConfirmation] = useState<ConfirmationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [firebaseReady, setFirebaseReady] = useState(false);
  const [configError, setConfigError] = useState("");
  const [showReset, setShowReset] = useState(false);
  const verifierRef = useRef<RecaptchaVerifier | null>(null);

  useEffect(() => {
    try {
      getFirebaseClientApp();
      setFirebaseReady(true);
    } catch {
      setConfigError("Firebase is not configured yet. Add the NEXT_PUBLIC_FIREBASE_* values in web/.env and enable Google, Email/Password, and Phone providers in Firebase Console.");
    }
    return () => {
      verifierRef.current?.clear();
      verifierRef.current = null;
    };
  }, []);

  function getPhoneVerifier() {
    const auth = getAuth(getFirebaseClientApp());
    if (!verifierRef.current) {
      verifierRef.current = new RecaptchaVerifier(auth, "auth-recaptcha-container", { size: "invisible" });
    }
    return verifierRef.current;
  }

  async function finishSignIn(idToken: string) {
    await createServerSession(idToken);
    const statusResponse = await fetch("/api/auth/session", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    });
    const statusPayload = await statusResponse.json().catch(() => ({})) as { user?: { role?: string } };
    const role = statusResponse.ok ? statusPayload.user?.role : undefined;
    const requestedPath = new URLSearchParams(window.location.search).get("next");
    const safeRequestedPath = requestedPath === "/dashboard/billing" ? requestedPath : null;
    router.replace(role === "ADMIN" ? "/admin" : (safeRequestedPath ?? "/dashboard"));
    router.refresh();
  }

  async function handleEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const auth = getAuth(getFirebaseClientApp());
      const credential = mode === "signup"
        ? await createUserWithEmailAndPassword(auth, email.trim(), password)
        : await signInWithEmailAndPassword(auth, email.trim(), password);
      if (mode === "signup") {
        if (name.trim()) await updateProfile(credential.user, { displayName: name.trim() });
        await sendEmailVerification(credential.user);
        await signOut(auth);
        setSuccess("Account created. Check your inbox for the verification link, verify the address, then sign in. The server grants admin access only to a verified email matching INITIAL_ADMIN_EMAIL.");
        return;
      }
      if (!credential.user.emailVerified) {
        await sendEmailVerification(credential.user);
        await signOut(auth);
        setSuccess("Your email is not verified. We sent a verification link. Verify your address, then sign in again.");
        return;
      }
      await finishSignIn(await credential.user.getIdToken(true));
    } catch (cause) {
      setError(explainAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleGoogle() {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const auth = getAuth(getFirebaseClientApp());
      const credential = await signInWithPopup(auth, new GoogleAuthProvider());
      await finishSignIn(await credential.user.getIdToken(true));
    } catch (cause) {
      setError(explainAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleForgotPassword() {
    if (!email.trim()) {
      setError("Enter your email address first.");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const auth = getAuth(getFirebaseClientApp());
      await sendPasswordResetEmail(auth, email.trim());
      setSuccess("Password reset email sent. Check your inbox (and spam folder).");
      setShowReset(false);
    } catch (cause) {
      setError(explainAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function sendPhoneCode() {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const auth = getAuth(getFirebaseClientApp());
      const result = await signInWithPhoneNumber(auth, phone.trim(), getPhoneVerifier());
      setConfirmation(result);
      setSuccess("Verification SMS sent. Enter the code to continue.");
    } catch (cause) {
      verifierRef.current?.clear();
      verifierRef.current = null;
      setError(explainAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function verifyPhoneCode() {
    if (!confirmation) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const result = await confirmation.confirm(smsCode.trim());
      await finishSignIn(await result.user.getIdToken(true));
    } catch (cause) {
      setError(explainAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {configError && <div role="alert" className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm leading-6 text-amber-200">{configError}</div>}
      {error && <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm leading-6 text-destructive">{error}</div>}
      {success && <div role="status" className="flex items-start gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-200"><CheckCircle2 className="mt-0.5 size-4 shrink-0" />{success}</div>}

      <Button type="button" variant="outline" className="w-full" onClick={handleGoogle} disabled={busy || !firebaseReady}>
        {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Globe aria-hidden="true" className="size-4" />}
        Continue with Google
      </Button>

      <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" /> EMAIL & PASSWORD <span className="h-px flex-1 bg-border" /></div>

      <form onSubmit={handleEmail} className="space-y-4">
        {mode === "signup" && <div className="space-y-2"><Label htmlFor="display-name">Full name</Label><Input id="display-name" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" maxLength={80} required disabled={busy || !firebaseReady} /></div>}
        <div className="space-y-2"><Label htmlFor="email">Email address</Label><Input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required disabled={busy || !firebaseReady} /></div>
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === "signup" ? "At least 8 characters" : "Your password"} minLength={8} required disabled={busy || !firebaseReady} />
          {mode === "login" && (
            <button
              type="button"
              onClick={() => setShowReset(!showReset)}
              className="mt-1 text-sm text-primary hover:underline flex items-center gap-1"
              disabled={busy}
            >
              <RotateCcw className="size-3" /> Forgot password?
            </button>
          )}
        </div>
        {showReset && (
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-3 space-y-2">
            <p className="text-sm text-primary">Enter your email above, then click send.</p>
            <Button type="button" variant="outline" className="w-full" onClick={handleForgotPassword} disabled={busy || !email.trim()}>
              {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Mail className="size-4" />} Send reset email
            </Button>
            <button type="button" className="w-full text-sm text-muted-foreground hover:text-foreground" onClick={() => setShowReset(false)}>Cancel</button>
          </div>
        )}
        <Button type="submit" className="w-full" disabled={busy || !firebaseReady}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : mode === "signup" ? <UserRound className="size-4" /> : <Mail className="size-4" />}{mode === "signup" ? "Create account" : "Sign in with email"}<ArrowRight className="ml-auto size-4" /></Button>
      </form>

      <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" /> PHONE OTP <span className="h-px flex-1 bg-border" /></div>
      <div className="space-y-3">
        <div className="space-y-2"><Label htmlFor="phone">Phone number</Label><Input id="phone" type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+919876543210" disabled={busy || !firebaseReady || Boolean(confirmation)} /><p className="text-xs leading-5 text-muted-foreground">Use international format including country code.</p></div>
        {!confirmation ? <Button type="button" variant="outline" className="w-full" onClick={sendPhoneCode} disabled={busy || !firebaseReady || !phone.trim()}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <Phone className="size-4" />} Send verification code</Button> : <><div className="space-y-2"><Label htmlFor="sms-code">SMS verification code</Label><Input id="sms-code" inputMode="numeric" autoComplete="one-time-code" value={smsCode} onChange={(event) => setSmsCode(event.target.value)} placeholder="Enter code" disabled={busy} /></div><Button type="button" className="w-full" onClick={verifyPhoneCode} disabled={busy || !smsCode.trim()}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <LockKeyhole className="size-4" />} Verify and continue</Button><button type="button" className="w-full text-sm text-muted-foreground hover:text-foreground" onClick={() => { setConfirmation(null); setSmsCode(""); setSuccess(""); }}>Use a different number</button></>}
      </div>
      <div id="auth-recaptcha-container" />
      <p className="text-center text-sm text-muted-foreground">{mode === "signup" ? "Already have an account? " : "New to the platform? "}<Link className="font-semibold text-primary hover:underline" href={mode === "signup" ? "/login" : "/signup"}>{mode === "signup" ? "Sign in" : "Create an account"}</Link></p>
    </div>
  );
}
