import Link from "next/link";
import { ArrowLeft, ShieldCheck, Users } from "lucide-react";
import { requireAdmin } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";
import { SignOutButton } from "@/components/sign-out-button";
import { ThemeToggle } from "@/components/theme-toggle";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  await requireAdmin();
  const [userCount, activeCount, deletedCount, users] = await Promise.all([
    prisma.user.count({ where: { deletedAt: null } }),
    prisma.subscription.count({ where: { tier: "PRO", status: "ACTIVE", user: { deletedAt: null } } }),
    prisma.user.count({ where: { deletedAt: { not: null } } }),
    prisma.user.findMany({ where: { deletedAt: null }, orderBy: { createdAt: "desc" }, take: 25, select: { id: true, email: true, displayName: true, role: true, createdAt: true } }),
  ]);
  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8"><div className="mx-auto max-w-6xl">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-3"><div><Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Dashboard</Link><h1 className="mt-4 flex items-center gap-3 text-3xl font-semibold tracking-tight"><ShieldCheck className="size-7 text-primary" /> Admin overview</h1><p className="mt-2 text-sm text-muted-foreground">Server-protected account statistics and recent user records.</p></div><div className="flex items-center gap-2"><ThemeToggle /><SignOutButton /></div></header>
      <div className="grid gap-4 sm:grid-cols-3"><div className="rounded-2xl border border-border bg-card p-5"><Users className="size-5 text-primary" /><p className="mt-4 text-sm text-muted-foreground">Active user accounts</p><p className="mt-1 text-3xl font-semibold">{userCount}</p></div><div className="rounded-2xl border border-border bg-card p-5"><ShieldCheck className="size-5 text-primary" /><p className="mt-4 text-sm text-muted-foreground">Active subscriptions</p><p className="mt-1 text-3xl font-semibold">{activeCount}</p></div><div className="rounded-2xl border border-border bg-card p-5"><Users className="size-5 text-primary" /><p className="mt-4 text-sm text-muted-foreground">Scheduled for deletion</p><p className="mt-1 text-3xl font-semibold">{deletedCount}</p></div></div>
      <section className="mt-6 overflow-hidden rounded-2xl border border-border bg-card"><div className="border-b border-border p-5"><h2 className="font-semibold">Recent users</h2></div><div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead className="bg-muted/40 text-muted-foreground"><tr><th className="px-5 py-3 font-medium">User</th><th className="px-5 py-3 font-medium">Email</th><th className="px-5 py-3 font-medium">Role</th><th className="px-5 py-3 font-medium">Created</th></tr></thead><tbody>{users.map((user) => <tr key={user.id} className="border-t border-border"><td className="px-5 py-3">{user.displayName ?? "Unnamed user"}</td><td className="px-5 py-3">{user.email ?? "—"}</td><td className="px-5 py-3">{user.role}</td><td className="px-5 py-3">{user.createdAt.toLocaleDateString("en-IN")}</td></tr>)}{users.length === 0 && <tr><td colSpan={4} className="px-5 py-8 text-center text-muted-foreground">No user accounts yet.</td></tr>}</tbody></table></div></section>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">Initial administrator bootstrap is controlled by the server-only INITIAL_ADMIN_EMAIL environment variable. Usage, feedback, revenue and plan-editing tools remain in later phases.</p>
    </div></main>
  );
}
