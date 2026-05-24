import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { findVendorBySlug, listProductsByVendor } from "@/lib/db";
import { categoryById } from "@/lib/categories";
import { Logo } from "@/components/Logo";

export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const vendor = await findVendorBySlug(slug);
  if (!vendor || vendor.status !== "live") return { title: "Vendor not found" };
  const cat = categoryById(vendor.category);
  const desc = vendor.description || `${vendor.businessName} on RoadLime.`;
  return {
    title: `${vendor.businessName}${cat ? ` · ${cat.name}` : ""}`,
    description: desc,
    openGraph: {
      title: vendor.businessName,
      description: desc,
      type: "website",
    },
  };
}

function formatPrice(cents: number) {
  return `TT$${(cents / 100).toFixed(2)}`;
}

export default async function VendorPage({ params }: Params) {
  const { slug } = await params;
  const vendor = await findVendorBySlug(slug);
  if (!vendor || vendor.status !== "live") notFound();

  const products = await listProductsByVendor(vendor.id);
  const cat = categoryById(vendor.category);
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: vendor.businessName,
    description: vendor.description,
    image: vendor.bannerUrl || undefined,
    url: `${baseUrl}/v/${vendor.slug}`,
    telephone: vendor.phone,
    geo:
      vendor.lat != null && vendor.lng != null
        ? {
            "@type": "GeoCoordinates",
            latitude: vendor.lat,
            longitude: vendor.lng,
          }
        : undefined,
    address: vendor.address
      ? {
          "@type": "PostalAddress",
          streetAddress: vendor.address,
          addressCountry: vendor.bank.country ?? "TT",
        }
      : undefined,
    hasMenu: {
      "@type": "Menu",
      hasMenuItem: products.map((p) => ({
        "@type": "MenuItem",
        name: p.name,
        description: p.description,
        offers: {
          "@type": "Offer",
          price: (p.priceCents / 100).toFixed(2),
          priceCurrency: p.currency,
        },
      })),
    },
  };

  return (
    <main className="min-h-dvh bg-ink-100 pb-32">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div
        className="aspect-[5/3] w-full sm:aspect-[5/2]"
        style={{
          background: vendor.bannerUrl
            ? `url(${vendor.bannerUrl}) center/cover`
            : "linear-gradient(135deg, #4A1E7A 0%, #F76B1C 60%, #F4C233 100%)",
        }}
      />
      <div className="container-app -mt-8">
        <div className="glass p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-2xl font-bold">{vendor.businessName}</h1>
              <p className="mt-1 text-sm text-ink-500">{vendor.description}</p>
            </div>
            {cat && (
              <span
                className="pill shrink-0"
                style={{ background: `${cat.color}22`, color: cat.color }}
              >
                {cat.icon} {cat.name}
              </span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-500">
            <span className="pill bg-emerald-100 text-emerald-800">● Open</span>
            {vendor.address && <span>📍 {vendor.address}</span>}
          </div>
        </div>

        <h2 className="mt-6 px-1 text-sm font-semibold uppercase tracking-wide text-ink-500">
          Menu
        </h2>
        {products.length === 0 ? (
          <div className="mt-3 rounded-xl2 border border-dashed border-ink-300 bg-white p-6 text-center text-sm text-ink-500">
            This vendor hasn&apos;t added items yet.
          </div>
        ) : (
          <ul className="mt-3 space-y-3">
            {products.map((p) => (
              <li key={p.id} className="glass flex items-center gap-3 p-3">
                <div
                  className="h-16 w-16 shrink-0 rounded-xl bg-ink-300/40"
                  style={
                    p.imageUrl
                      ? { background: `url(${p.imageUrl}) center/cover` }
                      : undefined
                  }
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{p.name}</p>
                  <p className="line-clamp-2 text-xs text-ink-500">
                    {p.description || "—"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold">
                    {formatPrice(p.priceCents)}
                  </p>
                  <button
                    type="button"
                    className="mt-1 rounded-full bg-carnival-purple px-3 py-1 text-xs font-semibold text-white"
                  >
                    Add
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-8 text-center text-xs text-ink-500">
          <Link href="/" className="inline-flex items-center gap-2">
            Powered by <Logo />
          </Link>
        </div>
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-ink-300/40 bg-white/95 backdrop-blur-xl">
        <div className="container-app py-3">
          <button
            type="button"
            className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl2 bg-carnival-purple text-sm font-semibold text-white"
          >
            Pay with card · Apple Pay · Google Pay
          </button>
          <p className="mt-1 text-center text-[10px] text-ink-500">
            Checkout is wired in the next slice (WiPay / Powertranz).
          </p>
        </div>
      </div>
    </main>
  );
}
