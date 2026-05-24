# RoadLime

Caribbean vendor discovery and cashless commerce — built for Trinidad & Tobago Carnival and beyond.

This repo currently implements **Phase 1, Slice 1: full vendor onboarding flow** from the master build doc.

## What's in this slice

- Marketing landing page with live vendor grid
- Vendor signup / sign-in (HMAC-signed session cookie)
- Onboarding wizard: **KYC → bank → category → location → products → go-live**
- Server-side ID and product image uploads
- QR storefront generation (`/api/qr?text=…`)
- SSR vendor storefront at `/v/[slug]` with `LocalBusiness` JSON-LD
- Vendor dashboard with downloadable QR
- Supabase migration ready under `/supabase/migrations/0001_init.sql`

## Tech choices

- **Next.js 15** App Router + React 19 + TypeScript
- **Tailwind CSS** with a Carnival design-token palette (Gold / Purple / Emerald / Sunset / Obsidian)
- **Local JSON store** (`/lib/db.ts`, writes to `.data/`) — placeholder behind the same interface a Supabase implementation will use. Swap is mechanical.
- **HMAC session cookie** — placeholder for Supabase Auth
- **Server-side filesystem uploads** to `public/uploads/` — placeholder for Supabase Storage
- **`qrcode`** for SVG QR generation

## Run

```bash
cp .env.example .env.local
# generate a session secret:
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
# paste into SESSION_SECRET=

npm install
npm run dev
```

App boots at <http://localhost:3000>. Onboarding flow:

1. Land on `/`
2. `Become a vendor` → `/signup`
3. Walk through `/onboarding/kyc → bank → category → location → products → go-live`
4. Click **Go live now** → land on `/dashboard`
5. Open `/v/<your-slug>` in another tab to see the public storefront and QR

Data lives in `.data/vendors.json` and `.data/products.json` (gitignored). Delete the folder to reset.

## Project layout

```
app/
  layout.tsx, globals.css, page.tsx          marketing
  signup/                                    auth (server action)
  onboarding/{kyc,bank,category,location,products,go-live}/
  dashboard/                                 vendor home
  v/[slug]/                                  public SSR storefront
  api/qr/                                    SVG QR endpoint
components/                                  Button, Input, StepHeader, Logo
lib/
  db.ts            file-based repo (swap to Supabase later)
  session.ts       HMAC cookie auth (swap to Supabase Auth later)
  uploads.ts       fs-based uploads (swap to Supabase Storage later)
  password.ts      scrypt
  onboarding.ts    step routing helpers
  categories.ts    seeded category lookup
  types.ts         shared Vendor / Product / Category types
  slugify.ts
supabase/
  migrations/0001_init.sql                   production schema (RLS-enabled)
legacy/
  club-flyer-builder.html                    previous repo content, archived
```

## What's deferred (intentionally)

The master build doc's Phase 1 MVP is 4–8 weeks. This slice deliberately stops at the end of onboarding. Wired in the next slices:

| Slice | Adds |
| --- | --- |
| Auth & data | Supabase Auth + apply `0001_init.sql` + replace `lib/db.ts` Supabase impl |
| Map | Mapbox GL JS at `/map`, tap-to-pin in `/onboarding/location` |
| Payments | WiPay & Powertranz behind a `PaymentProcessor` interface; checkout sheet on `/v/[slug]` |
| Search | Typesense or Algolia index over vendors + products |
| Admin | `/admin` moderation, KYC review, fraud queue |
| SEO | Dynamic sitemap, OG image generator |
| PWA | `next-pwa`, install prompt, offline shell |
| AI | Vendor setup from a single photo (description + category + tags) |

## Branding note

The master build doc lists eight candidate names. This implementation uses **RoadLime** throughout (chosen in the project brief). To rebrand: search-replace `RoadLime` in `lib/`, `components/Logo.tsx`, `app/layout.tsx`, `app/page.tsx`, `README.md`, `package.json`.

---

Strategic positioning (from the spec):

> Do NOT market as a payment processor.
> Market as the Caribbean vendor discovery and cashless commerce platform.
> Payments are infrastructure. **Discovery is the moat.**
