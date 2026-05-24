export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-display font-bold ${className}`}>
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-carnival-purple text-carnival-gold">
        R
      </span>
      <span>RoadLime</span>
    </span>
  );
}
