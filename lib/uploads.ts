import { promises as fs } from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const UPLOAD_ROOT = path.join(process.cwd(), "public", "uploads");
const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
  "application/pdf",
]);
const MAX_BYTES = 8 * 1024 * 1024;

function extFromMime(mime: string): string {
  switch (mime) {
    case "image/jpeg":
      return "jpg";
    case "image/png":
      return "png";
    case "image/webp":
      return "webp";
    case "image/heic":
      return "heic";
    case "image/heif":
      return "heif";
    case "application/pdf":
      return "pdf";
    default:
      return "bin";
  }
}

export async function saveUpload(opts: {
  vendorId: string;
  bucket: "kyc" | "products" | "logos";
  file: File;
}): Promise<{ url: string; path: string }> {
  const { vendorId, bucket, file } = opts;
  if (!ALLOWED_MIME.has(file.type)) {
    throw new Error(`Unsupported file type: ${file.type || "unknown"}`);
  }
  if (file.size > MAX_BYTES) {
    throw new Error("File exceeds 8MB limit");
  }
  const dir = path.join(UPLOAD_ROOT, bucket, vendorId);
  await fs.mkdir(dir, { recursive: true });
  const id = crypto.randomBytes(8).toString("hex");
  const filename = `${id}.${extFromMime(file.type)}`;
  const target = path.join(dir, filename);
  const buf = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(target, buf);
  const url = `/uploads/${bucket}/${vendorId}/${filename}`;
  return { url, path: target };
}
