import { promises as fs } from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import type { Product, Vendor } from "./types";
import { uniqueSlug } from "./slugify";

/**
 * Local JSON-file repository. Designed so swapping to Supabase later only
 * requires reimplementing this module against the SQL schema in
 * /supabase/migrations/0001_init.sql — the rest of the app talks to this
 * interface, not to the storage backend.
 */

const DATA_DIR = path.join(process.cwd(), ".data");
const VENDORS_FILE = path.join(DATA_DIR, "vendors.json");
const PRODUCTS_FILE = path.join(DATA_DIR, "products.json");

interface DbShape {
  vendors: Vendor[];
  products: Product[];
}

let cache: DbShape | null = null;
let writeLock: Promise<void> = Promise.resolve();

async function ensureDir() {
  await fs.mkdir(DATA_DIR, { recursive: true });
}

async function load(): Promise<DbShape> {
  if (cache) return cache;
  await ensureDir();
  const [vendorsRaw, productsRaw] = await Promise.all([
    fs.readFile(VENDORS_FILE, "utf8").catch(() => "[]"),
    fs.readFile(PRODUCTS_FILE, "utf8").catch(() => "[]"),
  ]);
  cache = {
    vendors: JSON.parse(vendorsRaw) as Vendor[],
    products: JSON.parse(productsRaw) as Product[],
  };
  return cache;
}

async function persist(): Promise<void> {
  const next = writeLock.then(async () => {
    if (!cache) return;
    await ensureDir();
    await Promise.all([
      fs.writeFile(VENDORS_FILE, JSON.stringify(cache.vendors, null, 2)),
      fs.writeFile(PRODUCTS_FILE, JSON.stringify(cache.products, null, 2)),
    ]);
  });
  writeLock = next.catch(() => {});
  return next;
}

export function newId(): string {
  return crypto.randomUUID();
}

export async function findVendorByEmail(email: string): Promise<Vendor | null> {
  const db = await load();
  return db.vendors.find((v) => v.email.toLowerCase() === email.toLowerCase()) ?? null;
}

export async function findVendorBySlug(slug: string): Promise<Vendor | null> {
  const db = await load();
  return db.vendors.find((v) => v.slug === slug) ?? null;
}

export async function getVendor(id: string): Promise<Vendor | null> {
  const db = await load();
  return db.vendors.find((v) => v.id === id) ?? null;
}

export async function listLiveVendors(): Promise<Vendor[]> {
  const db = await load();
  return db.vendors.filter((v) => v.status === "live");
}

export async function createVendor(input: {
  email: string;
  phone: string;
  passwordHash: string;
  businessName: string;
}): Promise<Vendor> {
  const db = await load();
  const existing = new Set(db.vendors.map((v) => v.slug));
  const now = new Date().toISOString();
  const vendor: Vendor = {
    id: newId(),
    email: input.email,
    phone: input.phone,
    passwordHash: input.passwordHash,
    businessName: input.businessName,
    slug: uniqueSlug(input.businessName, existing),
    description: "",
    category: "",
    logoUrl: null,
    bannerUrl: null,
    status: "draft",
    onboardingStep: "kyc",
    lat: null,
    lng: null,
    address: null,
    kyc: {
      idType: null,
      idNumber: null,
      documentUrl: null,
      submittedAt: null,
    },
    bank: {
      accountHolder: null,
      bankName: null,
      accountNumber: null,
      routingNumber: null,
      country: null,
    },
    createdAt: now,
    updatedAt: now,
  };
  db.vendors.push(vendor);
  await persist();
  return vendor;
}

export async function updateVendor(
  id: string,
  patch: Partial<Vendor>,
): Promise<Vendor | null> {
  const db = await load();
  const idx = db.vendors.findIndex((v) => v.id === id);
  if (idx === -1) return null;
  const current = db.vendors[idx];
  const merged: Vendor = {
    ...current,
    ...patch,
    kyc: { ...current.kyc, ...(patch.kyc ?? {}) },
    bank: { ...current.bank, ...(patch.bank ?? {}) },
    updatedAt: new Date().toISOString(),
  };
  db.vendors[idx] = merged;
  await persist();
  return merged;
}

export async function listProductsByVendor(vendorId: string): Promise<Product[]> {
  const db = await load();
  return db.products
    .filter((p) => p.vendorId === vendorId)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function createProduct(input: {
  vendorId: string;
  name: string;
  description: string;
  priceCents: number;
  currency: string;
  imageUrl: string | null;
}): Promise<Product> {
  const db = await load();
  const product: Product = {
    id: newId(),
    vendorId: input.vendorId,
    name: input.name,
    description: input.description,
    priceCents: input.priceCents,
    currency: input.currency,
    imageUrl: input.imageUrl,
    isActive: true,
    createdAt: new Date().toISOString(),
  };
  db.products.push(product);
  await persist();
  return product;
}

export async function deleteProduct(id: string, vendorId: string): Promise<boolean> {
  const db = await load();
  const before = db.products.length;
  db.products = db.products.filter((p) => !(p.id === id && p.vendorId === vendorId));
  if (db.products.length === before) return false;
  await persist();
  return true;
}
