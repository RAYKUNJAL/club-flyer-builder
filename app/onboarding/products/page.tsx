import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { StepHeader } from "@/components/StepHeader";
import { Field, TextArea } from "@/components/Input";
import { Button } from "@/components/Button";
import { requireVendor } from "@/lib/onboarding";
import {
  createProduct,
  deleteProduct,
  listProductsByVendor,
  updateVendor,
} from "@/lib/db";
import { saveUpload } from "@/lib/uploads";

export const dynamic = "force-dynamic";

async function addProduct(formData: FormData) {
  "use server";
  const vendor = await requireVendor();
  const name = String(formData.get("name") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const priceStr = String(formData.get("price") ?? "").trim();
  const price = Number(priceStr);
  const file = formData.get("image") as File | null;

  if (!name || !Number.isFinite(price) || price < 0) {
    redirect("/onboarding/products?error=missing");
  }

  let imageUrl: string | null = null;
  if (file && file.size > 0) {
    try {
      const saved = await saveUpload({
        vendorId: vendor.id,
        bucket: "products",
        file,
      });
      imageUrl = saved.url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "upload_failed";
      redirect(`/onboarding/products?error=${encodeURIComponent(msg)}`);
    }
  }

  await createProduct({
    vendorId: vendor.id,
    name,
    description,
    priceCents: Math.round(price * 100),
    currency: "TTD",
    imageUrl,
  });
  revalidatePath("/onboarding/products");
  redirect("/onboarding/products?added=1");
}

async function removeProduct(formData: FormData) {
  "use server";
  const vendor = await requireVendor();
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  await deleteProduct(id, vendor.id);
  revalidatePath("/onboarding/products");
  redirect("/onboarding/products");
}

async function finish() {
  "use server";
  const vendor = await requireVendor();
  const products = await listProductsByVendor(vendor.id);
  if (products.length === 0) {
    redirect("/onboarding/products?error=empty");
  }
  await updateVendor(vendor.id, { onboardingStep: "go-live" });
  redirect("/onboarding/go-live");
}

function formatPrice(cents: number) {
  return `TT$${(cents / 100).toFixed(2)}`;
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; added?: string }>;
}) {
  const vendor = await requireVendor();
  const params = await searchParams;
  const products = await listProductsByVendor(vendor.id);
  return (
    <main className="min-h-dvh bg-ink-100 pb-32">
      <StepHeader
        current="products"
        title="Add what you're selling"
        subtitle="Add at least one item. You can keep adding from your dashboard later."
      />
      <div className="container-app mt-2 space-y-5">
        {params.error === "empty" && (
          <div className="rounded-xl2 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Add at least one item before going live.
          </div>
        )}
        {params.added === "1" && (
          <div className="rounded-xl2 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            Item added.
          </div>
        )}

        <form
          action={addProduct}
          encType="multipart/form-data"
          className="glass space-y-4 p-4"
        >
          <h2 className="text-lg font-semibold">New item</h2>
          <Field label="Name" name="name" required placeholder="Doubles" />
          <TextArea
            label="Description"
            name="description"
            placeholder="Slight pepper, fresh channa"
            maxLength={200}
          />
          <Field
            label="Price (TTD)"
            name="price"
            required
            inputMode="decimal"
            type="number"
            step="0.01"
            min="0"
            placeholder="8.00"
          />
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">Photo (optional)</span>
            <input
              type="file"
              name="image"
              accept="image/*"
              className="block w-full text-sm"
            />
          </label>
          <Button type="submit" variant="secondary" fullWidth>
            Add item
          </Button>
        </form>

        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
            Your menu ({products.length})
          </h2>
          {products.length === 0 ? (
            <div className="rounded-xl2 border border-dashed border-ink-300 bg-white p-6 text-center text-sm text-ink-500">
              No items yet. Add your first above.
            </div>
          ) : (
            <ul className="space-y-3">
              {products.map((p) => (
                <li key={p.id} className="glass flex items-center gap-3 p-3">
                  <div
                    className="h-14 w-14 shrink-0 rounded-xl bg-ink-300/40"
                    style={
                      p.imageUrl
                        ? { background: `url(${p.imageUrl}) center/cover` }
                        : undefined
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{p.name}</p>
                    <p className="truncate text-xs text-ink-500">
                      {p.description || "—"}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold">{formatPrice(p.priceCents)}</p>
                    <form action={removeProduct}>
                      <input type="hidden" name="id" value={p.id} />
                      <button
                        type="submit"
                        className="text-xs text-red-600 hover:underline"
                      >
                        Remove
                      </button>
                    </form>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-ink-300/40 bg-white/90 backdrop-blur-xl">
        <div className="container-app py-3">
          <form action={finish}>
            <Button type="submit" fullWidth disabled={products.length === 0}>
              {products.length === 0
                ? "Add an item to continue"
                : `Continue with ${products.length} item${products.length === 1 ? "" : "s"}`}
            </Button>
          </form>
        </div>
      </div>
    </main>
  );
}
