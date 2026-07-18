import type { Metadata } from "next";
import "./globals.css";
import "./dashboard/deepspace/animations.css";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import ToastProvider from "@/app/components/layout/ToastProvider";
import CursorSweepProvider from "@/app/components/layout/CursorSweepProvider";
import { BRAND_NAME } from "@/lib/brand";

export const metadata: Metadata = {
  title: `${BRAND_NAME} | Agentic OS for documents, connectors, and autonomous work`,
  description: `${BRAND_NAME} combines grounded chat, DeepSpace execution, proactive workspaces, connector automation, and tenant-isolated security for grounded AI work.`,
  keywords: [
    "document intelligence",
    "agentic OS",
    "DeepSpace",
    "proactive workspace",
    "connector automation",
    "AI search",
    "enterprise AI",
    "tenant isolation",
  ],
  openGraph: {
    title: `${BRAND_NAME} | Agentic OS for documents, connectors, and autonomous work`,
    description:
      "Grounded chat, DeepSpace execution, proactive workspaces, and connector automation in one tenant-isolated product.",
    type: "website",
    siteName: BRAND_NAME,
  },
  icons: {
    icon: "/logo_icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth" data-scroll-behavior="smooth">
      <body className="antialiased">
        <ThemeProvider>
          <CursorSweepProvider />
          <ToastProvider>
            <AuthProvider>
              <div className="flex min-h-[100svh] flex-col">
                <main className="flex-1">{children}</main>
              </div>
            </AuthProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
