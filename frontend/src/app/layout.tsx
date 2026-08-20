import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "next-themes";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Reliastra — External Dependency Intelligence",
    template: "%s | Reliastra",
  },
  description:
    "Monitor third-party APIs independently. When vendors fail, generate timestamped SLA evidence reports to claim credits and prove fault.",
  keywords: [
    "RELIASTRA",
    "external dependency monitoring",
    "vendor monitoring",
    "SLA evidence",
    "SLA credits",
    "API monitoring",
    "uptime monitoring",
    "incident correlation",
    "partner program",
    "recurring commission",
    "infrastructure intelligence",
  ],
  icons: {
    icon: "/logo.svg",
  },
  openGraph: {
    title: "Reliastra — External Dependency Intelligence",
    description:
      "Monitor third-party APIs independently. When vendors fail, generate timestamped SLA evidence reports to claim credits and prove fault.",
    siteName: "Reliastra",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Reliastra — External Dependency Intelligence",
    description:
      "Monitor third-party APIs. Prove vendor failures. Claim SLA credits.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          {children}
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}