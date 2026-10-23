"use client";

import { type FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Box, LoaderCircle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type UnitSystem = "mm" | "cm" | "in" | "m";

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("Create a 40x20x10 mm box with a 5 mm diameter hole through the center");
  const [unitSystem, setUnitSystem] = useState<UnitSystem>("mm");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [requiresPlan, setRequiresPlan] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (description.trim().length < 5) {
      setError("Enter a part description with dimensions and the intended shape.");
      return;
    }
    setBusy(true);
    setError("");
    setRequiresPlan(false);
    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), text: description.trim(), unitSystem }),
      });
      const payload = await response.json().catch(() => ({})) as { error?: string; projectId?: string };
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (response.status === 402) setRequiresPlan(true);
      if (!response.ok || !payload.projectId) {
        throw new Error(payload.error ?? `Project generation failed (HTTP ${response.status}).`);
      }
      router.replace(`/dashboard/projects/${payload.projectId}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Project generation failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <Link href="/dashboard/projects" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Projects</Link>
        <div className="mt-5 flex items-center gap-3"><span className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground"><Box className="size-6" /></span><div><h1 className="text-3xl font-semibold tracking-tight">New CAD project</h1><p className="mt-1 text-sm text-muted-foreground">Generate a part from a dimensioned text description.</p></div></div>

        <Card className="mt-7">
          <CardHeader><CardTitle>Part specification</CardTitle><CardDescription>The server runs the Python CAD engine and saves the generated STEP/STL files to private storage.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-5">
              {error && <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}{requiresPlan && <span className="mt-2 block"><Link className="font-semibold underline" href="/dashboard/billing">View Pro plan and subscribe</Link></span>}</div>}
              <div className="space-y-2"><Label htmlFor="project-name">Project name (optional)</Label><Input id="project-name" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Mounting bracket" disabled={busy} /></div>
              <div className="space-y-2"><Label htmlFor="unit-system">Input unit</Label><select id="unit-system" value={unitSystem} onChange={(event) => setUnitSystem(event.target.value as UnitSystem)} disabled={busy} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"><option value="mm">Millimeters (mm)</option><option value="cm">Centimeters (cm)</option><option value="in">Inches (in)</option><option value="m">Meters (m)</option></select></div>
              <div className="space-y-2"><Label htmlFor="part-description">Describe the part</Label><textarea id="part-description" required minLength={5} maxLength={4000} rows={7} value={description} onChange={(event) => setDescription(event.target.value)} disabled={busy} className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Create a 40x20x10 mm box with a 5 mm hole through the center" /><p className="text-xs leading-5 text-muted-foreground">Start with explicit dimensions. The current parser supports a limited set of primitives and patterns; unsupported descriptions will return an error instead of pretending a model was generated.</p></div>
              <div className="rounded-xl border border-border bg-muted/30 p-3 text-sm leading-6 text-muted-foreground"><Sparkles className="mr-2 inline size-4 text-primary" /> STEP is for CAD workflows; STL is for 3D printing. Verify dimensions and geometry in a CAD viewer before manufacturing.</div>
              <Button type="submit" disabled={busy || description.trim().length < 5} className="w-full">{busy ? <><LoaderCircle className="size-4 animate-spin" /> Generating and saving model…</> : <><Sparkles className="size-4" /> Generate STEP + STL</>}</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
