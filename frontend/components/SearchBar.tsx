"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";

export function SearchBar({ onSearch }: { onSearch: (query: string) => void }) {
  const [value, setValue] = useState("");

  useEffect(() => {
    const timeout = setTimeout(() => onSearch(value.trim()), 350);
    return () => clearTimeout(timeout);
  }, [value, onSearch]);

  return (
    <div className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-vault-muted" />
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search movies and TV shows..."
        className="w-full rounded-full border border-vault-border bg-vault-surface py-2 pl-9 pr-4 text-sm text-vault-text placeholder:text-vault-muted focus:border-vault-accent focus:outline-none"
      />
    </div>
  );
}
