import Link from "next/link";
import { Logo } from "@/components/Logo";

export default function NotFound() {
  return (
    <main className="container-app flex min-h-dvh flex-col items-center justify-center text-center">
      <Logo />
      <h1 className="mt-6 text-2xl font-bold">Vendor not found</h1>
      <p className="mt-2 text-sm text-ink-500">
        This vendor may not be live yet or the link is mistyped.
      </p>
      <Link
        href="/"
        className="mt-6 rounded-xl2 bg-carnival-purple px-4 py-2 text-sm font-semibold text-white"
      >
        Back home
      </Link>
    </main>
  );
}
