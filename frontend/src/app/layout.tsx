import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { AuthGate } from "@/components/auth-gate";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FinPilot AI", template: "%s · FinPilot AI" },
  description: "Your local workspace for spending, budgets, and financial insights.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={GeistSans.variable}><AuthGate>{children}</AuthGate></body></html>;
}
