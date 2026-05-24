import { LinkButton } from "@/components/Button";
import { Logo } from "@/components/Logo";
import { listLiveVendors } from "@/lib/db";
import { categoryById } from "@/lib/categories";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const vendors = await listLiveVendors();
  return (
    <main className="min-h-dvh bg-ink-100">
      <section className="bg-carnival-gradient text-white">
        <div className="container-wide safe-top">
          <nav className="flex items-center justify-between py-5">
            <Logo className="text-white" />
            <div className="flex items-center gap-2">
              <Link
                href="/signup"
                className="hidden rounded-full px-4 py-2 text-sm font-semibold text-white/90 hover:bg-white/10 sm:inline-flex"
              >
                Sign in
              </Link>
              <LinkButton href="/signup" variant="secondary">
                Become a vendor
              </LinkButton>
            </div>
          </nav>
          <div className="grid gap-10 py-10 md:grid-cols-2 md:py-20">
            <div>
              <p className="pill bg-white/15 text-white">
                <span className="h-1.5 w-1.5 rounded-full bg-carnival-gold" />
                Trinidad & Tobago Carnival · 2026
              </p>
              <h1 className="mt-4 font-display text-4xl font-bold leading-[1.05] sm:text-5xl md:text-6xl">
                Take card. Get found. <br />
                Own the road.
              </h1>
              <p className="mt-5 max-w-md text-lg text-white/85">
                RoadLime is the cashless commerce and discovery platform for Caribbean
                vendors. Get a QR storefront in minutes — no website, no hardware.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <LinkButton href="/signup" variant="secondary">
                  Start onboarding
                </LinkButton>
                <LinkButton href="#vendors" variant="ghost" className="bg-white/10 text-white border-white/30 hover:bg-white/20">
                  Browse vendors
                </LinkButton>
              </div>
              <p className="mt-6 text-xs text-white/70">
                Next-day payouts · No POS hardware · Free QR storefront
              </p>
            </div>
            <div className="hidden md:block">
              <div className="glass-dark mx-auto w-full max-w-xs p-5">
                <div className="aspect-[3/4] rounded-xl bg-gradient-to-br from-carnival-gold/30 via-carnival-sunset/20 to-carnival-purple/40 p-4">
                  <div className="flex h-full flex-col justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-widest text-white/60">
                        Vendor preview
                      </p>
                      <p className="mt-1 font-display text-2xl font-bold">
                        Auntie Sherryl&apos;s Doubles
                      </p>
                      <p className="text-sm text-white/70">Queen&apos;s Park Savannah</p>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-lg bg-white/10 p-2">
                        <p className="text-white/60">Doubles</p>
                        <p className="font-semibold">TT$8</p>
                      </div>
                      <div className="rounded-lg bg-white/10 p-2">
                        <p className="text-white/60">Aloo Pie</p>
                        <p className="font-semibold">TT$10</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-sunset-fade">
        <div className="container-wide py-14">
          <div className="grid gap-6 sm:grid-cols-3">
            {[
              {
                t: "QR-first storefront",
                d: "Scan a QR, see your menu, pay. No app install. Works on any phone.",
              },
              {
                t: "Card, Apple Pay, Google Pay",
                d: "Cashless from day one. Settlement via WiPay & Powertranz. Next-day payouts.",
              },
              {
                t: "Get found by tourists",
                d: "Every vendor gets an SEO-indexed page and a pin on the Carnival map.",
              },
            ].map((f) => (
              <div key={f.t} className="glass p-6">
                <h3 className="text-lg font-semibold">{f.t}</h3>
                <p className="mt-2 text-sm text-ink-500">{f.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="vendors" className="bg-ink-100">
        <div className="container-wide py-14">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold sm:text-3xl">Live vendors</h2>
              <p className="text-sm text-ink-500">
                {vendors.length === 0
                  ? "No live vendors yet — be the first."
                  : `${vendors.length} vendor${vendors.length === 1 ? "" : "s"} on the road right now.`}
              </p>
            </div>
            <LinkButton href="/signup" variant="primary">
              Join them
            </LinkButton>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {vendors.length === 0 && (
              <div className="glass col-span-full p-8 text-center text-ink-500">
                Vendors who finish onboarding will appear here.
              </div>
            )}
            {vendors.map((v) => {
              const cat = categoryById(v.category);
              return (
                <Link
                  key={v.id}
                  href={`/v/${v.slug}`}
                  className="glass group block overflow-hidden p-0 transition hover:shadow-glow"
                >
                  <div
                    className="aspect-[5/3] w-full"
                    style={{
                      background:
                        v.bannerUrl
                          ? `url(${v.bannerUrl}) center/cover`
                          : "linear-gradient(135deg, #4A1E7A 0%, #F76B1C 60%, #F4C233 100%)",
                    }}
                  />
                  <div className="p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-base font-semibold">{v.businessName}</h3>
                      <span className="pill bg-emerald-100 text-emerald-800">Open</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm text-ink-500">
                      {v.description || "Tap to see what's on the menu."}
                    </p>
                    {cat && (
                      <span
                        className="pill mt-3"
                        style={{ background: `${cat.color}22`, color: cat.color }}
                      >
                        {cat.icon} {cat.name}
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      <footer className="border-t border-ink-300/40 bg-white">
        <div className="container-wide flex flex-col gap-4 py-8 text-sm text-ink-500 sm:flex-row sm:items-center sm:justify-between">
          <Logo />
          <p>
            Caribbean vendor discovery & cashless commerce. Built for the road.
          </p>
        </div>
      </footer>
    </main>
  );
}
