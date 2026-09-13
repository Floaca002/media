import type { Metadata } from "next";
import { AuthGuard } from "@/components/AuthGuard";
import { Navbar } from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vault",
  description: "Your self-hosted media command center",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-vault-bg text-vault-text">
        <Navbar />
        <main className="mx-auto max-w-[1600px] px-6 py-6">
          <AuthGuard>{children}</AuthGuard>
        </main>
      </body>
    </html>
  );
}
