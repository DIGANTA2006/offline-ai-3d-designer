import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getFirebaseAdminAuth } from "@/lib/firebase/admin";
import { prisma } from "@/lib/prisma";

export const SESSION_COOKIE_NAME = "offline_ai_session";

export type SafeUser = {
  id: string;
  firebaseUid: string;
  email: string | null;
  phone: string | null;
  displayName: string | null;
  photoURL: string | null;
  role: "USER" | "ADMIN";
  createdAt: Date;
};

export async function getCurrentUser(): Promise<SafeUser | null> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  if (!sessionCookie) return null;

  const auth = getFirebaseAdminAuth();
  let firebaseUid: string;
  try {
    firebaseUid = (await auth.verifySessionCookie(sessionCookie, true)).uid;
  } catch {
    // Expired, invalid, or revoked cookies mean the request is unauthenticated.
    return null;
  }

  // Deliberately keep the database query outside the cookie-validation catch.
  // A PostgreSQL outage must surface as a server error, not masquerade as logout.
  return prisma.user.findFirst({
    where: { firebaseUid, deletedAt: null },
    select: {
      id: true,
      firebaseUid: true,
      email: true,
      phone: true,
      displayName: true,
      photoURL: true,
      role: true,
      createdAt: true,
    },
  });
}

export async function requireUser(): Promise<SafeUser> {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return user;
}

export async function requireAdmin(): Promise<SafeUser> {
  const user = await requireUser();
  if (user.role !== "ADMIN") redirect("/dashboard");
  return user;
}