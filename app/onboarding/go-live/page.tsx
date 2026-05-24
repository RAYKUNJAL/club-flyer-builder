import { redirect } from "next/navigation";
import Link from "next/link";
import { StepHeader } from "@/components/StepHeader";
import { Button, LinkButton } from "@/components/Button";
import { requireVendor } from "@/lib/onboarding";
import { listProductsByVendor, updateVendor } from "@/lib/db";
import { categoryById } from "@/lib/categories";

export const dynamic = "force-dynamic";

async function goLive() {
  "use server";
  const vendor = await requireVendor();
  await updateVendor(vendor.id, {
    status: "live",
    onboardingStep: "done",
  });
  redirect("/dashboard?welcome=1");
}

export default async function GoLivePage() {
  const vendor = await requireVendor();
  const products = await listProductsByVendor(vendor.id);
  const cat = categoryById(vendor.category);
  const baseUrl =
    process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const storefrontUrl = `${baseUrl}/v/${vendor.slug}`;

  return (
    <main className="min-h-dvh bg-ink-100 pb-16">
      <StepHeader
        current="go-live"
        title="Last check, then you're live"
        subtitle="Review your storefront. You can keep editing after going live."
      />
      <div className="container-app mt-2 space-y-5">
        <div className="glass overflow-hidden p-0">
          <div className="aspect-[5/2] bg-carnival-gradient" />
          <div className="p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold">{vendor.businessName}</h2>
              {cat && (
                <span
                  className="pill"
                  style={{ background: `${cat.color}22`, color: cat.color }}
                >
                  {cat.icon} {cat.name}
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-ink-500">{vendor.description}</p>
            <p className="mt-2 text-xs text-ink-500">
              📍 {vendor.address}
            </p>
          </div>
        </div>

        <div className="glass p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Your QR storefront
          </h3>
          <div className="mt-3 flex items-center gap-4">
            <div className="rounded-xl2 border border-ink-300/60 bg-white p-3">
              <img
                src={`/api/qr?text=${encodeURIComponent(storefrontUrl)}&size=240`}
                alt="Storefront QR"
                width={140}
                height={140}
              />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-mono text-ink-700">{storefrontUrl}</p>
              <p className="mt-2 text-xs text-ink-500">
                Print this. Stick it on your cart. Anyone who scans it sees your menu and
                can pay.
              </p>
            </div>
          </div>
        </div>

        <div className="glass p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Menu ({products.length})
          </h3>
          <ul className="mt-2 divide-y divide-ink-300/40">
            {products.map((p) => (
              <li key={p.id} className="flex items-center justify-between py-2 text-sm">
                <span className="font-medium">{p.name}</span>
                <span className="font-semibold">
                  TT${(p.priceCents / 100).toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <form action={goLive}>
          <Button type="submit" variant="secondary" fullWidth>
            🚀 Go live now
          </Button>
        </form>
        <Link
          href="/onboarding/products"
          className="block text-center text-sm text-ink-500 hover:underline"
        >
          ← Back to edit menu
        </Link>
      </div>
    </main>
  );
}
