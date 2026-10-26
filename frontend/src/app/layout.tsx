import type { Metadata } from "next";
import { ProductShell } from "../components/product-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "ResearchForge AI — Research workspace",
  description: "Evidence-first research, built one verified step at a time.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ProductShell>{children}</ProductShell>
      </body>
    </html>
  );
}
