import { NextRequest } from "next/server";
import QRCode from "qrcode";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const text = searchParams.get("text");
  const sizeRaw = Number(searchParams.get("size") ?? "320");
  const size = Number.isFinite(sizeRaw)
    ? Math.min(Math.max(sizeRaw, 64), 1024)
    : 320;

  if (!text) {
    return new Response("Missing 'text' param", { status: 400 });
  }

  const svg = await QRCode.toString(text, {
    type: "svg",
    margin: 1,
    width: size,
    color: { dark: "#0B0B10", light: "#FFFFFF" },
    errorCorrectionLevel: "M",
  });

  return new Response(svg, {
    headers: {
      "Content-Type": "image/svg+xml",
      "Cache-Control": "public, max-age=86400, immutable",
    },
  });
}
