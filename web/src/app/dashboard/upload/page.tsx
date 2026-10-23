import Link from "next/link";
import { ArrowLeft, Sparkles } from "lucide-react";
import { requireUser } from "@/lib/auth/server";
import { UploadPanel } from "@/components/upload/upload-panel";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

export default async function UploadPage() {
  await requireUser();
  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8">
          <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Dashboard</Link>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">Upload drawings</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Securely store supported source files and extract reviewable OCR text/dimension candidates. Drawing-to-parametric-CAD conversion is still a separate, incomplete stage.</p>
            </div>
            <Button asChild><Link href="/dashboard/projects/new"><Sparkles className="size-4" /> New text-to-CAD project</Link></Button>
          </div>
        </header>
        <UploadPanel />
      </div>
    </main>
  );
}
