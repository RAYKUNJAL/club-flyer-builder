import { redirect } from "next/navigation";
import { StepHeader } from "@/components/StepHeader";
import { Field } from "@/components/Input";
import { Button } from "@/components/Button";
import { requireVendor } from "@/lib/onboarding";
import { updateVendor } from "@/lib/db";

export const dynamic = "force-dynamic";

async function submit(formData: FormData) {
  "use server";
  const vendor = await requireVendor();
  const address = String(formData.get("address") ?? "").trim();
  const lat = Number(formData.get("lat"));
  const lng = Number(formData.get("lng"));

  if (!address || !Number.isFinite(lat) || !Number.isFinite(lng)) {
    redirect("/onboarding/location?error=missing");
  }
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    redirect("/onboarding/location?error=range");
  }

  await updateVendor(vendor.id, {
    address,
    lat,
    lng,
    onboardingStep: "products",
  });
  redirect("/onboarding/products");
}

export default async function LocationPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const vendor = await requireVendor();
  const params = await searchParams;
  // Trinidad default centre
  const defaultLat = vendor.lat ?? 10.6918;
  const defaultLng = vendor.lng ?? -61.2225;

  return (
    <main className="min-h-dvh bg-ink-100 pb-16">
      <StepHeader
        current="location"
        title="Pin where you sell"
        subtitle="Tourists find you by map. You can update this each day from your dashboard."
      />
      <form action={submit} className="container-app mt-2 space-y-5">
        {params.error && (
          <div className="rounded-xl2 bg-red-50 px-4 py-3 text-sm text-red-700">
            {params.error === "range"
              ? "Coordinates look out of range."
              : "Please fill in your address and tap 'Use my location' or enter coords."}
          </div>
        )}
        <Field
          label="Street address / landmark"
          name="address"
          required
          defaultValue={vendor.address ?? ""}
          placeholder="Corner of Tragarete & Maraval Rd"
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Latitude"
            name="lat"
            required
            defaultValue={defaultLat}
            step="any"
            type="number"
            inputMode="decimal"
          />
          <Field
            label="Longitude"
            name="lng"
            required
            defaultValue={defaultLng}
            step="any"
            type="number"
            inputMode="decimal"
          />
        </div>
        <button
          type="button"
          id="use-loc"
          className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl2 border border-ink-300/60 bg-white text-sm font-semibold hover:bg-ink-100"
        >
          📍 Use my current location
        </button>
        <p className="text-xs text-ink-500">
          Mapbox tap-to-pin is wired in a later slice. For now, paste from Google Maps or use the
          GPS button above.
        </p>
        <Button type="submit" fullWidth>
          Continue
        </Button>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              document.getElementById('use-loc')?.addEventListener('click', () => {
                if (!navigator.geolocation) { alert('Geolocation not available'); return; }
                navigator.geolocation.getCurrentPosition((pos) => {
                  const f = document.forms[0];
                  f.lat.value = pos.coords.latitude.toFixed(6);
                  f.lng.value = pos.coords.longitude.toFixed(6);
                }, (err) => alert('Could not get location: ' + err.message));
              });
            `,
          }}
        />
      </form>
    </main>
  );
}
