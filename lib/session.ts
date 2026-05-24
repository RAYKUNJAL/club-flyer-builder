import crypto from "node:crypto";
import { cookies } from "next/headers";
import { getVendor } from "./db";
import type { Vendor } from "./types";

const COOKIE_NAME = "rl_session";
const MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

function getSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret || secret.length < 16) {
    // Dev-friendly fallback so the app boots without a .env.local.
    // In production SESSION_SECRET must be set or sessions are forgeable.
    return "dev-only-insecure-secret-please-override-in-env";
  }
  return secret;
}

function sign(payload: string): string {
  return crypto.createHmac("sha256", getSecret()).update(payload).digest("base64url");
}

function encode(vendorId: string): string {
  const payload = Buffer.from(JSON.stringify({ v: vendorId, t: Date.now() })).toString(
    "base64url",
  );
  return `${payload}.${sign(payload)}`;
}

function decode(token: string): { vendorId: string } | null {
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return null;
  if (sign(payload) !== sig) return null;
  try {
    const obj = JSON.parse(Buffer.from(payload, "base64url").toString()) as {
      v: string;
      t: number;
    };
    if (!obj.v) return null;
    return { vendorId: obj.v };
  } catch {
    return null;
  }
}

export async function setSession(vendorId: string): Promise<void> {
  const store = await cookies();
  store.set(COOKIE_NAME, encode(vendorId), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export async function getSessionVendorId(): Promise<string | null> {
  const store = await cookies();
  const token = store.get(COOKIE_NAME)?.value;
  if (!token) return null;
  return decode(token)?.vendorId ?? null;
}

export async function getCurrentVendor(): Promise<Vendor | null> {
  const id = await getSessionVendorId();
  if (!id) return null;
  return getVendor(id);
}
