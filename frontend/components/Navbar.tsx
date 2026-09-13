"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Clapperboard, Compass, Download, Library } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Discover", icon: Compass },
  { href: "/library", label: "Watch", icon: Library },
  { href: "/downloads", label: "Downloads", icon: Download },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between gap-6 border-b border-vault-border bg-vault-bg/90 px-6 py-3 backdrop-blur">
      <Link href="/" className="flex items-center gap-2 font-bold tracking-tight text-vault-text">
        <Clapperboard className="h-6 w-6 text-vault-accent" />
        <span className="text-lg">Vault</span>
      </Link>
      <nav className="flex items-center gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                active ? "bg-vault-card text-vault-text" : "text-vault-muted hover:text-vault-text"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
