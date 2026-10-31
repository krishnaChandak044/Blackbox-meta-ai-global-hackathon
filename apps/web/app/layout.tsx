import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blackbox — Road Incident Investigation",
  description:
    "Evidence-first road crash investigation workspace. Upload video, preserve originals, verify claims, and export a fully auditable review package.",
  keywords: ["crash investigation", "road safety", "evidence", "video analysis"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
