import { redirect } from "next/navigation";
import { getCurrentVendor } from "./session";
import type { OnboardingStep, Vendor } from "./types";

const PATHS: Record<OnboardingStep, string> = {
  signup: "/signup",
  kyc: "/onboarding/kyc",
  bank: "/onboarding/bank",
  category: "/onboarding/category",
  location: "/onboarding/location",
  products: "/onboarding/products",
  "go-live": "/onboarding/go-live",
  done: "/dashboard",
};

const ORDER: OnboardingStep[] = [
  "kyc",
  "bank",
  "category",
  "location",
  "products",
  "go-live",
  "done",
];

export function pathForStep(step: OnboardingStep): string {
  return PATHS[step];
}

export function nextStep(step: OnboardingStep): OnboardingStep {
  const idx = ORDER.indexOf(step);
  if (idx === -1 || idx === ORDER.length - 1) return "done";
  return ORDER[idx + 1];
}

export async function requireVendor(): Promise<Vendor> {
  const vendor = await getCurrentVendor();
  if (!vendor) redirect("/signup");
  return vendor;
}
