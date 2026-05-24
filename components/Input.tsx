import type { ComponentProps, ReactNode } from "react";

const fieldBase =
  "block w-full rounded-xl2 border border-ink-300/60 bg-white px-4 py-3 text-base text-ink-900 placeholder:text-ink-500 focus:border-carnival-purple focus:outline-none focus:ring-4 focus:ring-carnival-purple/15";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
}

export function Field({
  label,
  hint,
  error,
  ...rest
}: FieldProps & ComponentProps<"input">) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-900">{label}</span>
      <input {...rest} className={`${fieldBase} ${rest.className ?? ""}`} />
      {hint && !error && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function TextArea({
  label,
  hint,
  error,
  ...rest
}: FieldProps & ComponentProps<"textarea">) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-900">{label}</span>
      <textarea
        {...rest}
        className={`${fieldBase} min-h-[100px] resize-y ${rest.className ?? ""}`}
      />
      {hint && !error && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Select({
  label,
  hint,
  error,
  children,
  ...rest
}: FieldProps & ComponentProps<"select">) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-900">{label}</span>
      <select {...rest} className={`${fieldBase} appearance-none ${rest.className ?? ""}`}>
        {children}
      </select>
      {hint && !error && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}
