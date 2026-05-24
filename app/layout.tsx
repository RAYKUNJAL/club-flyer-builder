import type { Metadata, Viewport } from "next";
import "./globals.css";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: {
    default: "RoadLime — Caribbean vendor discovery & cashless commerce",
    template: "%s · RoadLime",
  },
  description:
    "RoadLime is the Caribbean vendor discovery and cashless commerce platform. Get a QR storefront, take card payments, and get found by tourists.",
  applicationName: "RoadLime",
  openGraph: {
    title: "RoadLime",
    description:
      "Caribbean vendor discovery and cashless commerce — built for Trinidad & Tobago Carnival and beyond.",
    url: APP_URL,
    siteName: "RoadLime",
    type: "website",
  },
  icons: {
    icon: [
      {
        url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%234A1E7A'/%3E%3Ctext x='50%25' y='58%25' text-anchor='middle' font-family='system-ui' font-size='34' font-weight='800' fill='%23F4C233'%3ER%3C/text%3E%3C/svg%3E",
        type: "image/svg+xml",
      },
    ],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#4A1E7A",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
