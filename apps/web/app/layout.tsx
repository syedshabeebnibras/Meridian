import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
});

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
    <html lang="en" className={`${inter.variable} ${mono.variable} dark`}>
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
