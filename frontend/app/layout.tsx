import type { Metadata } from "next";
import "./globals.css";
import "./dashboard/deepspace/animations.css";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import ToastProvider from "@/app/components/layout/ToastProvider";
import CursorSweepProvider from "@/app/components/layout/CursorSweepProvider";
import { BRAND_NAME } from "@/lib/brand";
import AverQelDialogHost from "@/app/components/ui/AverQelDialogHost";
import AppTooltipLayer from "@/app/components/ui/AppTooltipLayer";

const PRODUCT_SUMMARY =
  "AI workspace for documents, grounded answers, agent workflows, and team messaging";
const PRODUCT_DESCRIPTION =
  "AverQel is an AI workspace for document management and search, source-grounded questions, DeepSpace conversations and agent workflows, configurable model providers, approved connected apps, Qel Connect shared spaces and messaging, feedback and support, and tenant-aware security and administration. Provider and app integrations require configuration; Qel Connect is experimental beta.";

export const metadata: Metadata = {
  title: BRAND_NAME,
  description: PRODUCT_DESCRIPTION,
  keywords: [
    "document management",
    "source-cited answers",
    "AI conversations",
    "shared workspaces",
    "AI models",
    "connected tools",
  ],
  openGraph: {
    title: `${BRAND_NAME} - ${PRODUCT_SUMMARY}`,
    description: PRODUCT_DESCRIPTION,
    type: "website",
    siteName: BRAND_NAME,
  },
  icons: {
    icon: "/AverQel%20Logo/AverQel_Icon.svg",
    shortcut: "/AverQel%20Logo/AverQel_Icon.svg",
    apple: "/AverQel%20Logo/AverQel_Icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Browser extensions can add attributes to <html> before React hydrates.
  // The document root is deliberately hydration-tolerant; application UI
  // remains checked normally below it.
  return (
    <html
      lang="en"
      className="scroll-smooth"
      data-scroll-behavior="smooth"
      suppressHydrationWarning
    >
      <body className="antialiased" suppressHydrationWarning>
        <ThemeProvider>
          <CursorSweepProvider />
          <ToastProvider>
            <AverQelDialogHost />
            <AppTooltipLayer />
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
