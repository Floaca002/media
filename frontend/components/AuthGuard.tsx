"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

/**
 * Keeps you signed in across reloads: the JWT already lives in
 * localStorage (which survives a refresh on its own), but nothing was
 * actually checking for it, so every page just showed inline auth-error
 * text instead of taking you to /login. This gates every route except
 * /login itself on token *presence* (fast, no network round-trip) — an
 * actually-expired token is caught by the 401 handler in lib/api.ts,
 * which clears it and redirects for real.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setReady(true);
      return;
    }
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}
