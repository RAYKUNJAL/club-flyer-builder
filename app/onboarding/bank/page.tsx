import { redirect } from "next/navigation";
import { StepHeader } from "@/components/StepHeader";
import { Field, Select } from "@/components/Input";
import { Button } from "@/components/Button";
import { requireVendor } from "@/lib/onboarding";
import { updateVendor } from "@/lib/db";

export const dynamic = "force-dynamic";

async function submit(formData: FormData) {
  "use server";
  const vendor = await requireVendor();
  const accountHolder = String(formData.get("accountHolder") ?? "").trim();
  const bankName = String(formData.get("bankName") ?? "").trim();
  const accountNumber = String(formData.get("accountNumber") ?? "").trim();
  const routingNumber = String(formData.get("routingNumber") ?? "").trim();
  const country = String(formData.get("country") ?? "TT").trim();

  if (!accountHolder || !bankName || !accountNumber) {
    redirect("/onboarding/bank?error=missing");
  }

  await updateVendor(vendor.id, {
    bank: {
      accountHolder,
      bankName,
      accountNumber,
      routingNumber: routingNumber || null,
      country,
    },
    onboardingStep: "category",
  });
  redirect("/onboarding/category");
}

export default async function BankPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const vendor = await requireVendor();
  const params = await searchParams;
  return (
    <main className="min-h-dvh bg-ink-100 pb-16">
      <StepHeader
        current="bank"
        title="Where should payouts go?"
        subtitle="Next-day payouts to your bank account. We never share this with customers."
      />
      <form action={submit} className="container-app mt-2 space-y-5">
        {params.error === "missing" && (
          <div className="rounded-xl2 bg-red-50 px-4 py-3 text-sm text-red-700">
            Please fill in all required fields.
          </div>
        )}
        <Field
          label="Account holder name"
          name="accountHolder"
          required
          defaultValue={vendor.bank.accountHolder ?? vendor.businessName}
        />
        <Field
          label="Bank name"
          name="bankName"
          required
          defaultValue={vendor.bank.bankName ?? ""}
          placeholder="Republic Bank, RBC, First Citizens…"
        />
        <Field
          label="Account number"
          name="accountNumber"
          required
          inputMode="numeric"
          autoComplete="off"
          defaultValue={vendor.bank.accountNumber ?? ""}
        />
        <Field
          label="Routing / transit number"
          name="routingNumber"
          hint="Optional in TT — required for some banks."
          inputMode="numeric"
          autoComplete="off"
          defaultValue={vendor.bank.routingNumber ?? ""}
        />
        <Select
          label="Country"
          name="country"
          defaultValue={vendor.bank.country ?? "TT"}
        >
          <option value="TT">Trinidad & Tobago</option>
          <option value="BB">Barbados</option>
          <option value="JM">Jamaica</option>
          <option value="GY">Guyana</option>
          <option value="GD">Grenada</option>
          <option value="VC">St. Vincent & the Grenadines</option>
          <option value="LC">St. Lucia</option>
        </Select>
        <Button type="submit" fullWidth>
          Continue
        </Button>
        <p className="text-xs text-ink-500">
          Bank verification is stubbed in this build. Real settlement will be wired via the
          WiPay & Powertranz abstraction layer.
        </p>
      </form>
    </main>
  );
}
