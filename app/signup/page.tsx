import Link from "next/link";
import { redirect } from "next/navigation";
import { Field } from "@/components/Input";
import { Button } from "@/components/Button";
import { Logo } from "@/components/Logo";
import { createVendor, findVendorByEmail } from "@/lib/db";
import { hashPassword, verifyPassword } from "@/lib/password";
import { setSession, getCurrentVendor } from "@/lib/session";

export const dynamic = "force-dynamic";

const ONBOARDING_PATH: Record<string, string> = {
  kyc: "/onboarding/kyc",
  bank: "/onboarding/bank",
  category: "/onboarding/category",
  location: "/onboarding/location",
  products: "/onboarding/products",
  "go-live": "/onboarding/go-live",
  done: "/dashboard",
};

async function nextStepFor(vendorId: string): Promise<string> {
  const vendor = await import("@/lib/db").then((m) => m.getVendor(vendorId));
  if (!vendor) return "/signup";
  return ONBOARDING_PATH[vendor.onboardingStep] ?? "/dashboard";
}

async function signupAction(formData: FormData) {
  "use server";
  const mode = String(formData.get("mode") ?? "signup");
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const phone = String(formData.get("phone") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const businessName = String(formData.get("businessName") ?? "").trim();

  if (!email || !password) {
    redirect("/signup?error=missing");
  }

  const existing = await findVendorByEmail(email);
  if (mode === "signin") {
    if (!existing || !verifyPassword(password, existing.passwordHash)) {
      redirect("/signup?error=invalid&mode=signin");
    }
    await setSession(existing.id);
    redirect(await nextStepFor(existing.id));
  }

  if (existing) {
    redirect("/signup?error=exists");
  }
  if (!phone || !businessName) {
    redirect("/signup?error=missing");
  }

  const vendor = await createVendor({
    email,
    phone,
    passwordHash: hashPassword(password),
    businessName,
  });
  await setSession(vendor.id);
  redirect("/onboarding/kyc");
}

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; mode?: string }>;
}) {
  const current = await getCurrentVendor();
  if (current) {
    redirect(await nextStepFor(current.id));
  }
  const params = await searchParams;
  const isSignIn = params.mode === "signin";
  const errorText: Record<string, string> = {
    missing: "Please fill in all fields.",
    invalid: "Email or password is incorrect.",
    exists: "An account with that email already exists. Try signing in.",
  };

  return (
    <main className="min-h-dvh bg-ink-100">
      <div className="container-app safe-top pt-6">
        <Link href="/" className="inline-block">
          <Logo />
        </Link>
      </div>
      <div className="container-app py-8">
        <div className="mb-4 inline-flex rounded-full bg-white p-1 shadow-glass">
          <Link
            href="/signup"
            className={`rounded-full px-4 py-1.5 text-sm font-semibold ${!isSignIn ? "bg-carnival-purple text-white" : "text-ink-500"}`}
          >
            Create account
          </Link>
          <Link
            href="/signup?mode=signin"
            className={`rounded-full px-4 py-1.5 text-sm font-semibold ${isSignIn ? "bg-carnival-purple text-white" : "text-ink-500"}`}
          >
            Sign in
          </Link>
        </div>

        <h1 className="text-2xl font-bold">
          {isSignIn ? "Welcome back" : "Become a RoadLime vendor"}
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          {isSignIn
            ? "Pick up where you left off."
            : "Takes about 5 minutes. No card or hardware required."}
        </p>

        {params.error && (
          <div className="mt-4 rounded-xl2 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorText[params.error] ?? "Something went wrong."}
          </div>
        )}

        <form action={signupAction} className="mt-6 space-y-4">
          <input type="hidden" name="mode" value={isSignIn ? "signin" : "signup"} />
          {!isSignIn && (
            <Field
              label="Business name"
              name="businessName"
              required
              placeholder="Auntie Sherryl's Doubles"
              autoComplete="organization"
            />
          )}
          <Field
            label="Email"
            type="email"
            name="email"
            required
            placeholder="you@example.com"
            autoComplete="email"
          />
          {!isSignIn && (
            <Field
              label="Phone (WhatsApp)"
              type="tel"
              name="phone"
              required
              placeholder="+1 868 555 0100"
              autoComplete="tel"
            />
          )}
          <Field
            label="Password"
            type="password"
            name="password"
            required
            minLength={8}
            placeholder="At least 8 characters"
            autoComplete={isSignIn ? "current-password" : "new-password"}
          />
          <Button type="submit" fullWidth>
            {isSignIn ? "Sign in" : "Create my account"}
          </Button>
        </form>

        <p className="mt-6 text-xs text-ink-500">
          By continuing you agree to RoadLime&apos;s terms and acknowledge our privacy policy.
        </p>
      </div>
    </main>
  );
}
