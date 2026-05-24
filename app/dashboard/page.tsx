import { redirect } from "next/navigation";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { LinkButton } from "@/components/Button";
import { requireVendor, pathForStep } from "@/lib/onboarding";
import { listProductsByVendor } from "@/lib/db";
import { categoryById } from "@/lib/categories";
import { clearSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function signOut() {
  "use server";
  await clearSession();
  redirect("/");
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ welcome?: string }>;
}) {
  const vendor = await requireVendor();
  if (vendor.onboardingStep !== "done") {
    redirect(pathForStep(vendor.onboardingStep));
  }
  const params = await searchParams;
  const products = await listProductsByVendor(vendor.id);
  const cat = categoryById(vendor.category);
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const storefrontUrl = `${baseUrl}/v/${vendor.slug}`;

  return (
    <main className="min-h-dvh bg-ink-100 pb-16">
      <header className="safe-top sticky top-0 z-20 bg-ink-100/85 backdrop-blur-xl">
        <div className="container-wide flex items-center justify-between py-3">
          <Logo />
          <form action={signOut}>
            <button
              type="submit"
              className="text-sm font-medium text-ink-500 hover:text-ink-900"
            >
              Sign out
            </button>
          </form>
        </div>
      </header>

      <div className="container-wide space-y-6 py-6">
        {params.welcome === "1" && (
          <div className="rounded-xl2 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            🎉 You&apos;re live on RoadLime. Share your QR or storefront link below.
          </div>
        )}

        <section className="glass overflow-hidden p-0">
          <div className="aspect-[5/2] bg-carnival-gradient" />
          <div className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-ink-500">
                  {vendor.status === "live" ? "Live storefront" : vendor.status}
                </p>
                <h1 className="mt-1 text-2xl font-bold">{vendor.businessName}</h1>
                {cat && (
                  <span
                    className="pill mt-2"
                    style={{ background: `${cat.color}22`, color: cat.color }}
                  >
                    {cat.icon} {cat.name}
                  </span>
                )}
              </div>
              <LinkButton href={`/v/${vendor.slug}`} variant="primary">
                View storefront →
              </LinkButton>
            </div>
          </div>
        </section>

        <div className="grid gap-6 md:grid-cols-3">
          <section className="glass p-5 md:col-span-2">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Menu</h2>
              <Link
                href="/onboarding/products"
                className="text-sm font-semibold text-carnival-purple hover:underline"
              >
                Edit items
              </Link>
            </div>
            {products.length === 0 ? (
              <p className="mt-3 text-sm text-ink-500">No items yet.</p>
            ) : (
              <ul className="mt-3 divide-y divide-ink-300/40">
                {products.map((p) => (
                  <li
                    key={p.id}
                    className="flex items-center gap-3 py-3 text-sm"
                  >
                    <div
                      className="h-12 w-12 shrink-0 rounded-lg bg-ink-300/40"
                      style={
                        p.imageUrl
                          ? { background: `url(${p.imageUrl}) center/cover` }
                          : undefined
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold">{p.name}</p>
                      <p className="truncate text-xs text-ink-500">
                        {p.description || "—"}
                      </p>
                    </div>
                    <p className="font-semibold">
                      TT${(p.priceCents / 100).toFixed(2)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="glass p-5">
            <h2 className="text-lg font-semibold">QR storefront</h2>
            <div className="mt-3 rounded-xl2 border border-ink-300/60 bg-white p-3">
              <img
                src={`/api/qr?text=${encodeURIComponent(storefrontUrl)}&size=320`}
                alt="Storefront QR"
                className="mx-auto block h-44 w-44"
              />
            </div>
            <p className="mt-3 break-all text-xs text-ink-500">{storefrontUrl}</p>
            <a
              href={`/api/qr?text=${encodeURIComponent(storefrontUrl)}&size=1024`}
              download={`roadlime-${vendor.slug}.svg`}
              className="mt-3 inline-flex w-full items-center justify-center rounded-xl2 border border-ink-300/60 bg-white px-3 py-2 text-sm font-semibold hover:bg-ink-100"
            >
              Download SVG
            </a>
          </section>
        </div>

        <section className="glass p-5">
          <h2 className="text-lg font-semibold">Coming next</h2>
          <ul className="mt-2 list-inside list-disc text-sm text-ink-500">
            <li>Payments via WiPay & Powertranz (abstraction layer)</li>
            <li>Mapbox storefront pin & vendor map</li>
            <li>Real-time order notifications</li>
            <li>Daily payout statements</li>
            <li>Admin moderation dashboard</li>
          </ul>
        </section>
      </div>
    </main>
  );
}
