import type { Category } from "./types";

export const CATEGORIES: Category[] = [
  { id: "doubles", name: "Doubles", icon: "🫓", color: "#F4C233" },
  { id: "corn_soup", name: "Corn Soup", icon: "🌽", color: "#0FB892" },
  { id: "shark_bake", name: "Shark & Bake", icon: "🦈", color: "#4A1E7A" },
  { id: "bbq", name: "BBQ & Grill", icon: "🔥", color: "#F76B1C" },
  { id: "drinks", name: "Drinks & Coconut", icon: "🥥", color: "#0FB892" },
  { id: "costumes", name: "Costumes", icon: "🪶", color: "#F4C233" },
  { id: "makeup", name: "Makeup & Glam", icon: "💄", color: "#F76B1C" },
  { id: "taxi", name: "Taxi & Rides", icon: "🚖", color: "#4A1E7A" },
  { id: "parking", name: "Parking", icon: "🅿️", color: "#5A5A6A" },
  { id: "event", name: "Event Services", icon: "🎉", color: "#F4C233" },
];

export function categoryById(id: string | null | undefined): Category | null {
  if (!id) return null;
  return CATEGORIES.find((c) => c.id === id) ?? null;
}
