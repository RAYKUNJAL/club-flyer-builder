import { redirect } from "next/navigation";
import { StepHeader } from "@/components/StepHeader";
import { Field, Select } from "@/components/Input";
import { Button } from "@/components/Button";
import { requireVendor } from "@/lib/onboarding";
import { updateVendor } from "@/lib/db";
import { saveUpload } from "@/lib/uploads";

export const dynamic = "force-dynamic";

async function submit(formData: FormData) {
  "use server";
  const vendor = await requireVendor();
  const idType = String(formData.get("idType") ?? "") as
    | "passport"
    | "drivers_license"
    | "national_id";
  const idNumber = String(formData.get("idNumber") ?? "").trim();
  const file = formData.get("document") as File | null;

  if (!idType || !idNumber || !file || file.size === 0) {
    redirect("/onboarding/kyc?error=missing");
  }

  let documentUrl: string | null = null;
  try {
    const saved = await saveUpload({
      vendorId: vendor.id,
      bucket: "kyc",
      file: file as File,
    });
    documentUrl = saved.url;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "upload_failed";
    redirect(`/onboarding/kyc?error=${encodeURIComponent(msg)}`);
  }

  await updateVendor(vendor.id, {
    kyc: {
      idType,
      idNumber,
      documentUrl,
      submittedAt: new Date().toISOString(),
    },
    onboardingStep: "bank",
  });
  redirect("/onboarding/bank");
}

export default async function KycPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const vendor = await requireVendor();
  const params = await searchParams;
  return (
    <main className="min-h-dvh bg-ink-100 pb-16">
      <StepHeader
        current="kyc"
        title="Verify your identity"
        subtitle="We need to confirm who you are before activating payouts. We never share this with customers."
      />
      <form
        action={submit}
        className="container-app mt-2 space-y-5"
        encType="multipart/form-data"
      >
        {params.error && (
          <div className="rounded-xl2 bg-red-50 px-4 py-3 text-sm text-red-700">
            {params.error === "missing"
              ? "Please fill in all fields and attach a document."
              : params.error}
          </div>
        )}
        <Select
          label="ID type"
          name="idType"
          required
          defaultValue={vendor.kyc.idType ?? ""}
        >
          <option value="" disabled>
            Select…
          </option>
          <option value="national_id">National ID</option>
          <option value="drivers_license">Driver&apos;s License</option>
          <option value="passport">Passport</option>
        </Select>
        <Field
          label="ID number"
          name="idNumber"
          required
          defaultValue={vendor.kyc.idNumber ?? ""}
          placeholder="As printed on document"
          autoComplete="off"
        />
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink-900">
            Upload a photo of your ID
          </span>
          <div className="rounded-xl2 border-2 border-dashed border-ink-300 bg-white p-5 text-center">
            <input
              type="file"
              name="document"
              accept="image/*,application/pdf"
              required
              className="block w-full text-sm"
            />
            <p className="mt-2 text-xs text-ink-500">
              JPG, PNG, WEBP or PDF · max 8MB
            </p>
          </div>
        </label>
        <Button type="submit" fullWidth>
          Continue to payouts
        </Button>
      </form>
    </main>
  );
}
