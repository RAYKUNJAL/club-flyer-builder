import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        carnival: {
          gold: "#F4C233",
          purple: "#4A1E7A",
          emerald: "#0FB892",
          sunset: "#F76B1C",
          obsidian: "#0B0B10",
        },
        ink: {
          900: "#0B0B10",
          800: "#16161E",
          700: "#22222D",
          500: "#5A5A6A",
          300: "#B5B5C2",
          100: "#F3F3F6",
          0: "#FFFFFF",
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glass: "0 1px 2px rgba(11,11,16,0.06), 0 8px 32px rgba(11,11,16,0.08)",
        glow: "0 0 0 1px rgba(244,194,51,0.4), 0 8px 32px rgba(244,194,51,0.25)",
      },
      backgroundImage: {
        "carnival-gradient":
          "linear-gradient(135deg, #4A1E7A 0%, #F76B1C 60%, #F4C233 100%)",
        "sunset-fade":
          "linear-gradient(180deg, rgba(247,107,28,0.12) 0%, rgba(255,255,255,0) 100%)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
