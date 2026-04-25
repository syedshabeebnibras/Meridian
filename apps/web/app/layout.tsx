import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Meridian — enterprise knowledge assistant",
    template: "%s · Meridian",
  },
  description:
    "A production-grade LLM orchestrator — deterministic routing, grounded answers, full observability, and cost-aware dispatch.",
  openGraph: {
    title: "Meridian",
    description:
      "Enterprise knowledge assistant with deterministic orchestration, semantic caching, and cost circuit breakers.",
    type: "website",
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#1a1a24",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
