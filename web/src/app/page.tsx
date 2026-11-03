import Link from "next/link";\nimport { BrandLogo } from "@/components/brand-logo";
import {
  ArrowRight,
  Check,
  Layers3,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme-toggle";

const features = [
  {
    icon: ScanLine,
    title: "Drawing-aware workflow",
    description:
      "Build a foundation for reading engineering drawings, dimensions, callouts, and annotations.",
  },
  {
    icon: Layers3,
    title: "Parametric CAD core",
    description:
      "Keep the existing Python and build123d engine as the geometry source of truth.",
  },
  {
    icon: Workflow,
    title: "Auditable AI pipeline",
    description:
      "Separate ingestion, research, fit reasoning, and CAD synthesis into inspectable stages.",
  },
];

const freeFeatures = ["Create an account", "Access the account dashboard", "Manage your profile"];
const proFeatures = [
  "Unlimited generation allowance",
  "STEP, STL, and GLB exports",
  "Batch jobs and version history",
  "Priority processing",
];

export default function HomePage() {
  return (
    <main className="min-h-screen overflow-hidden">
      <div className="pointer-events-none fixed inset-0 surface-grid opacity-60" />
      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
        <BrandLogo />
        <nav className="flex items-center gap-2">
          <a href="#features" className="hidden px-3 py-2 text-sm text-muted-foreground hover:text-foreground sm:inline-flex">
            Platform
          </a>
          <a href="#pricing" className="hidden px-3 py-2 text-sm text-muted-foreground hover:text-foreground sm:inline-flex">
            Pricing
          </a>
          <ThemeToggle />
          <Button variant="ghost" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild>
            <Link href="/signup">Get started <ArrowRight aria-hidden="true" /></Link>
          </Button>
        </nav>
      </header>

      <section className="relative z-10 mx-auto grid max-w-7xl items-center gap-14 px-5 pb-20 pt-14 sm:px-8 lg:grid-cols-[1.04fr_0.96fr] lg:pb-28 lg:pt-24">
        <div>
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary">
            <Sparkles className="size-3.5" />
            From technical intent to CAD-ready geometry
          </div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
            Engineering ideas, translated into{" "}
            <span className="text-primary">precise 3D models.</span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
            A workspace for turning part descriptions and engineering drawings into inspectable
            geometry, fit checks, and manufacturing-ready exports—with a clear record of how each
            model was produced.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" asChild>
              <Link href="/dashboard">Open workspace <ArrowRight aria-hidden="true" /></Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <a href="#features">Explore the platform</a>
            </Button>
          </div>
          <div className="mt-8 flex flex-wrap gap-x-5 gap-y-3 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-2"><Check className="size-4 text-primary" /> Parametric CAD foundation</span>
            <span className="inline-flex items-center gap-2"><Check className="size-4 text-primary" /> Local-first engine preserved</span>
          </div>
        </div>

        <div className="relative mx-auto w-full max-w-xl">
          <div className="absolute -inset-8 rounded-[2rem] bg-primary/10 blur-3xl" />
          <Card className="relative overflow-hidden border-white/10 bg-card/90 shadow-2xl shadow-black/30 backdrop-blur">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <p className="text-sm font-semibold">Part workspace</p>
                <p className="mt-1 text-xs text-muted-foreground">Concept preview · Enclosure assembly</p>
              </div>
              <span className="rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs text-primary">
                CAD pipeline
              </span>
            </div>
            <CardContent className="p-4 sm:p-6">
              <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-2xl border border-border bg-[#0c1319]">
                <div className="absolute inset-0 surface-grid opacity-70" />
                <svg viewBox="0 0 460 320" role="img" aria-label="Stylized technical wireframe preview of a 3D enclosure" className="relative w-full max-w-[440px]">
                  <defs>
                    <linearGradient id="face" x1="0" x2="1" y1="0" y2="1">
                      <stop offset="0%" stopColor="#44e4b3" stopOpacity="0.27" />
                      <stop offset="100%" stopColor="#44e4b3" stopOpacity="0.03" />
                    </linearGradient>
                  </defs>
                  <g stroke="#42d9ac" strokeWidth="1.4" strokeLinejoin="round">
                    <path d="M112 105 L254 54 L351 104 L210 157 Z" fill="url(#face)" />
                    <path d="M112 105 L112 207 L210 260 L210 157 Z" fill="#0f5043" fillOpacity=".35" />
                    <path d="M210 157 L351 104 L351 207 L210 260 Z" fill="#0d302a" fillOpacity=".7" />
                    <path d="M132 112 L254 69 L330 108 L209 151 Z" fill="none" strokeOpacity=".8" />
                    <path d="M132 112 L132 191 L209 233 L209 151" fill="none" strokeDasharray="4 5" />
                    <path d="M209 151 L330 108 L330 188 L209 233" fill="none" strokeDasharray="4 5" />
                    <path d="M175 89 L271 126 L271 227" fill="none" stroke="#77f5d0" strokeOpacity=".8" />
                    <path d="M155 96 L155 181 M300 88 L300 176" fill="none" strokeOpacity=".45" />
                    <path d="M94 89 L94 220 M87 95 L101 83 M87 214 L101 226" stroke="#8ba1ac" strokeOpacity=".9" />
                    <path d="M112 231 L211 284 L365 225 M111 237 L111 245 M365 218 L365 231" stroke="#8ba1ac" strokeOpacity=".9" />
                  </g>
                  <g fill="#b6c8d0" fontSize="10" fontFamily="monospace">
                    <text x="56" y="159" transform="rotate(-90 56 159)">80 mm</text>
                    <text x="205" y="303">120 mm</text>
                    <text x="309" y="250">60 mm</text>
                  </g>
                </svg>
                <div className="absolute bottom-3 left-3 flex items-center gap-2 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-xs text-slate-300 backdrop-blur">
                  <span className="size-2 rounded-full bg-primary" /> Preview illustration — not an exported part
                </div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-border bg-background/70 p-3">
                  <p className="text-xs text-muted-foreground">Geometry</p>
                  <p className="mt-1 text-sm font-medium">Parametric</p>
                </div>
                <div className="rounded-xl border border-border bg-background/70 p-3">
                  <p className="text-xs text-muted-foreground">Validation</p>
                  <p className="mt-1 text-sm font-medium">Planned</p>
                </div>
                <div className="rounded-xl border border-border bg-background/70 p-3">
                  <p className="text-xs text-muted-foreground">Exports</p>
                  <p className="mt-1 text-sm font-medium">STEP · STL</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <section id="features" className="relative z-10 mx-auto max-w-7xl px-5 py-16 sm:px-8">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-primary">Built for engineering work</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">A workflow, not a black box.</h2>
          <p className="mt-4 leading-7 text-muted-foreground">
            The web interface is being added around the existing geometry engine. Processing stages,
            confidence, and engineering assumptions will be surfaced as the pipeline is implemented.
          </p>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <Card key={feature.title} className="bg-card/80 transition-colors hover:border-primary/35">
                <CardContent className="p-6">
                  <span className="flex size-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <h3 className="mt-5 text-lg font-semibold">{feature.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{feature.description}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      <section id="pricing" className="relative z-10 mx-auto max-w-7xl px-5 py-16 sm:px-8">
        <div className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-primary">Simple plans</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Start small. Scale your workflow.</h2>
          <p className="mt-4 text-muted-foreground">CAD generation requires an active Pro subscription. Pro is INR 500/month with recurring billing that you can cancel.</p>
        </div>
        <div className="mx-auto mt-8 grid max-w-4xl gap-4 md:grid-cols-2">
          <Card>
            <CardContent className="p-6 sm:p-8">
              <p className="font-semibold">Free</p>
              <p className="mt-3 text-4xl font-semibold">₹0 <span className="text-sm font-normal text-muted-foreground">/ month</span></p>
              <p className="mt-3 text-sm text-muted-foreground">Create an account. CAD generation and STEP/STL downloads require Pro.</p>
              <ul className="mt-6 space-y-3 text-sm">
                {freeFeatures.map((item) => <li key={item} className="flex gap-2"><Check className="size-4 shrink-0 text-primary" />{item}</li>)}
              </ul>
              <Button className="mt-8 w-full" variant="outline" asChild><Link href="/signup">Create free account</Link></Button>
            </CardContent>
          </Card>
          <Card className="border-primary/40 bg-primary/[0.06]">
            <CardContent className="p-6 sm:p-8">
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold">Pro</p>
                <span className="rounded-full bg-primary/15 px-2.5 py-1 text-xs font-semibold text-primary">Monthly subscription</span>
              </div>
              <p className="mt-3 text-4xl font-semibold">₹500 <span className="text-sm font-normal text-muted-foreground">/ month</span></p>
              <p className="mt-3 text-sm text-muted-foreground">Unlock CAD generation for as long as your monthly subscription is active.</p>
              <ul className="mt-6 space-y-3 text-sm">
                {proFeatures.map((item) => <li key={item} className="flex gap-2"><Check className="size-4 shrink-0 text-primary" />{item}</li>)}
              </ul>
              <Button className="mt-8 w-full" asChild><Link href="/login?next=%2Fdashboard%2Fbilling">Subscribe for ₹500/month <ArrowRight /></Link></Button>
            </CardContent>
          </Card>
        </div>
      </section>

      <footer className="relative z-10 border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-7 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span>© {new Date().getFullYear()} Offline AI 3D Designer</span>
          <span className="inline-flex items-center gap-2"><ShieldCheck className="size-4" /> Engineering output must be reviewed before manufacture.</span>
        </div>
      </footer>
    </main>
  );
}
