import Link from "next/link";
import { ArrowLeft, Layers3, ShieldCheck } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { AuthPanel } from "@/components/auth/auth-panel";

export default function SignupPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="pointer-events-none absolute inset-0 surface-grid opacity-60" />
      <div className="absolute right-5 top-6 sm:right-10 sm:top-8"><ThemeToggle /></div>
      <section className="relative z-10 w-full max-w-md">
        <Link href="/" className="mb-8 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Back to home</Link>
        <div className="rounded-3xl border border-border bg-card/95 p-6 shadow-2xl shadow-black/20 sm:p-8">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground"><Layers3 className="size-6" /></div>
          <h1 className="mt-6 text-2xl font-semibold tracking-tight">Create your account</h1>
          <p className="mb-6 mt-2 text-sm leading-6 text-muted-foreground">Set up your engineering workspace and keep your models in one place.</p>
          <AuthPanel mode="signup" />
          <p className="mt-5 flex items-start gap-2 border-t border-border pt-4 text-xs leading-5 text-muted-foreground"><ShieldCheck className="mt-0.5 size-4 shrink-0" /> Account roles are assigned on the server. The browser cannot make itself an administrator.</p>
        </div>
      </section>
    </main>
  );
}