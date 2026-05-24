import { redirect } from "next/navigation";
import { StepHeader } from "@/components/StepHeader";
import { TextArea } from "@/components/Input";
import { Button } from "@/components/Button";
import { requireVendor } from "@/lib/onboarding";
import { updateVendor } from "@/lib/db";
import { CATEGORIES } from "@/lib/categories";

export const dynamic = "force-dynamic";

async function submit(formData: FormData) {
  "use server";
  const vendor = await requireVendor();
  const category = String(formData.get("category") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();

  if (!category || !CATEGORIES.some((c) => c.id === category)) {
    redirect("/onboarding/category?error=category");
  }
  if (description.length < 10) {
    redirect("/onboarding/category?error=description");
  }

  await updateVendor(vendor.id, {
    category,
    description,
    onboardingStep: "location",
  });
  redirect("/onboarding/location");
}

export default async function CategoryPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const vendor = await requireVendor();
  const params = await searchParams;
  return (
    <main className="min-h-dvh bg-ink-100 pb-16">
      <StepHeader
        current="category"
        title="What do you sell?"
        subtitle="Pick the closest match. This decides your map pin color and search filters."
      />
      <form action={submit} className="container-app mt-2 space-y-5">
        {params.error && (
          <div className="rounded-xl2 bg-red-50 px-4 py-3 text-sm text-red-700">
            {params.error === "category"
              ? "Please pick a category."
              : "Please write a short description (at least 10 characters)."}
          </div>
        )}
        <fieldset>
          <legend className="mb-2 block text-sm font-medium">Category</legend>
          <div className="grid grid-cols-2 gap-2.5">
            {CATEGORIES.map((c) => (
              <label
                key={c.id}
                className="relative flex cursor-pointer flex-col rounded-xl2 border border-ink-300/60 bg-white p-3 transition has-[:checked]:border-carnival-purple has-[:checked]:bg-carnival-purple/5 has-[:checked]:shadow-glow"
              >
                <input
                  type="radio"
                  name="category"
                  value={c.id}
                  defaultChecked={vendor.category === c.id}
                  className="peer sr-only"
                  required
                />
                <span className="text-2xl">{c.icon}</span>
                <span className="mt-1 text-sm font-semibold">{c.name}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <TextArea
          label="Short description"
          name="description"
          required
          minLength={10}
          maxLength={280}
          defaultValue={vendor.description}
          placeholder="Hot doubles, slight pepper, fried fresh from 5am. Find us by the Savannah."
          hint="Shown on your storefront. 280 characters max."
        />
        <Button type="submit" fullWidth>
          Continue
        </Button>
      </form>
    </main>
  );
}
