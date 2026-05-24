import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-carnival-purple text-white hover:bg-carnival-purple/90 shadow-glass active:scale-[0.99]",
  secondary:
    "bg-carnival-gold text-ink-900 hover:bg-carnival-gold/90 shadow-glass active:scale-[0.99]",
  ghost: "bg-white/60 text-ink-900 hover:bg-white border border-ink-300/40",
  danger: "bg-red-600 text-white hover:bg-red-700",
};

const base =
  "inline-flex h-12 items-center justify-center gap-2 rounded-xl2 px-5 text-sm font-semibold transition disabled:opacity-50 disabled:pointer-events-none";

interface CommonProps {
  variant?: Variant;
  fullWidth?: boolean;
  children: ReactNode;
  className?: string;
}

export function Button({
  variant = "primary",
  fullWidth,
  className = "",
  ...rest
}: CommonProps & ComponentProps<"button">) {
  return (
    <button
      {...rest}
      className={`${base} ${VARIANTS[variant]} ${fullWidth ? "w-full" : ""} ${className}`}
    />
  );
}

export function LinkButton({
  variant = "primary",
  fullWidth,
  className = "",
  ...rest
}: CommonProps & ComponentProps<typeof Link>) {
  return (
    <Link
      {...rest}
      className={`${base} ${VARIANTS[variant]} ${fullWidth ? "w-full" : ""} ${className}`}
    />
  );
}
