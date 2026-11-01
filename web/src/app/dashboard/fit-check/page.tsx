import { requireUser } from "@/lib/auth/server";
import { FitCheckPanel } from "@/components/fit-check/fit-check-panel";

export const dynamic = "force-dynamic";

export default async function HardwareFitCheckPage() {
  await requireUser();
  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <FitCheckPanel />
      </div>
    </main>
  );
}
