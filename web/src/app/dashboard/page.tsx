import { requireUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";
import DashboardContent from "./dashboard-content";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const user = await requireUser();
  const [projects, totalProjects, activeJobs, completedProjects] = await Promise.all([
    prisma.project.findMany({
      where: { userId: user.id },
      orderBy: { updatedAt: "desc" },
      take: 5,
      select: { id: true, name: true, status: true, updatedAt: true },
    }),
    prisma.project.count({ where: { userId: user.id } }),
    prisma.project.count({ where: { userId: user.id, status: { in: ["QUEUED", "PROCESSING"] } } }),
    prisma.project.count({ where: { userId: user.id, status: "SUCCEEDED" } }),
  ]);

  return (
    <DashboardContent
      user={user}
      projects={projects}
      stats={{ totalProjects, activeJobs, completedProjects }}
    />
  );
}
