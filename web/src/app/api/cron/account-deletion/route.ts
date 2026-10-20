import { NextResponse } from "next/server";
import { getFirebaseAdminAuth } from "@/lib/firebase/admin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  }

  const dueUsers = await prisma.user.findMany({
    where: { deletedAt: { not: null }, hardDeleteAt: { lte: new Date() } },
    select: { id: true, firebaseUid: true },
    take: 50,
    orderBy: { hardDeleteAt: "asc" },
  });
  let deleted = 0;
  let failed = 0;

  for (const user of dueUsers) {
    try {
      try {
        await getFirebaseAdminAuth().deleteUser(user.firebaseUid);
      } catch (error) {
        const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
        if (code !== "auth/user-not-found") throw error;
      }
      await prisma.user.delete({ where: { id: user.id } });
      deleted += 1;
    } catch (error) {
      failed += 1;
      console.error("Scheduled account deletion failed for internal user id:", user.id, error);
    }
  }

  return NextResponse.json({ processed: dueUsers.length, deleted, failed });
}