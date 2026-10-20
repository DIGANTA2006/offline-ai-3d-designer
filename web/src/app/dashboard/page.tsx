import { requireUser } from "@/lib/auth/server";
import DashboardContent from "./dashboard-content";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const user = await requireUser();
  return <DashboardContent user={user} />;
}
