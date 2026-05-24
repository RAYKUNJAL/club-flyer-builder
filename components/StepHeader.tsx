import Link from "next/link";
import { Logo } from "./Logo";

const STEPS = [
  { key: "kyc", label: "Verify" },
  { key: "bank", label: "Payouts" },
  { key: "category", label: "Category" },
  { key: "location", label: "Location" },
  { key: "products", label: "Products" },
  { key: "go-live", label: "Go live" },
] as const;

export type StepKey = (typeof STEPS)[number]["key"];

export function StepHeader({
  current,
  title,
  subtitle,
}: {
  current: StepKey;
  title: string;
  subtitle?: string;
}) {
  const idx = STEPS.findIndex((s) => s.key === current);
  const progress = ((idx + 1) / STEPS.length) * 100;
  return (
    <header className="safe-top sticky top-0 z-20 bg-ink-100/85 backdrop-blur-xl">
      <div className="container-app flex items-center justify-between py-3">
        <Link href="/" className="text-ink-900">
          <Logo />
        </Link>
        <span className="text-xs font-medium text-ink-500">
          Step {idx + 1} of {STEPS.length}
        </span>
      </div>
      <div className="h-1 w-full bg-ink-300/40">
        <div
          className="h-full bg-carnival-gradient transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="container-app pb-4 pt-5">
        <h1 className="text-2xl font-bold leading-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
    </header>
  );
}
