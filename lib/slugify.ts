export function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
}

export function uniqueSlug(base: string, existing: Set<string>): string {
  let candidate = slugify(base) || "vendor";
  if (!existing.has(candidate)) return candidate;
  let i = 2;
  while (existing.has(`${candidate}-${i}`)) i++;
  return `${candidate}-${i}`;
}
