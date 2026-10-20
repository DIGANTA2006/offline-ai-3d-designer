import Link from "next/link";
import { ArrowLeft, UserRound } from "lucide-react";
import { requireUser } from "@/lib/auth/server";
import { ProfileForm } from "@/components/profile/profile-form";
import { SignOutButton } from "@/components/sign-out-button";
import { ThemeToggle } from "@/components/theme-toggle";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  const user = await requireUser();
  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-3">
          <div><Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Dashboard</Link><h1 className="mt-4 flex items-center gap-3 text-3xl font-semibold tracking-tight"><UserRound className="size-7 text-primary" /> Account profile</h1><p className="mt-2 text-sm text-muted-foreground">Signed in as {user.email ?? user.phone ?? user.displayName ?? "account"}</p></div>
          <div className="flex items-center gap-2"><ThemeToggle /><SignOutButton /></div>
        </header>
        <ProfileForm />
      </div>
    </main>
  );
}