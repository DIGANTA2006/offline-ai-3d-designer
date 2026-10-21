import "server-only";

import { cert, getApps, initializeApp } from "firebase-admin/app";
import { getAuth, type Auth } from "firebase-admin/auth";

export function getFirebaseAdminAuth(): Auth {
  const projectId = process.env.FIREBASE_PROJECT_ID;
  const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
  const rawPrivateKey = process.env.FIREBASE_PRIVATE_KEY;
  const privateKey = rawPrivateKey
    ?.trim()
    .replace(/^["']|["']$/g, "")
    .replace(/\\n/g, "\n")
    .replace(/\r\n/g, "\n");

  if (!projectId || !clientEmail || !privateKey) {
    throw new Error(
      "Firebase Admin configuration is missing. Set FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, and FIREBASE_PRIVATE_KEY.",
    );
  }
  if (!privateKey.includes("-----BEGIN PRIVATE KEY-----") || !privateKey.includes("-----END PRIVATE KEY-----")) {
    throw new Error("Firebase Admin private key is malformed. Copy the complete private_key value from a fresh service-account JSON file.");
  }

  const app =
    getApps().find((candidate) => candidate.name === "[DEFAULT]") ??
    initializeApp({
      credential: cert({ projectId, clientEmail, privateKey }),
      projectId,
    });

  return getAuth(app);
}