"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { PlayCircle } from "lucide-react";
import { API_BASE_URL, api, type JellyfinItem } from "@/lib/api";

function imageUrl(item: JellyfinItem): string | null {
  if (!item.ImageTags?.Primary) return null;
  // Routed through Vault's own backend, not Jellyfin directly — Jellyfin
  // has no published port, so the browser could never reach it itself.
  return `${API_BASE_URL}/library/items/${item.Id}/image?tag=${item.ImageTags.Primary}`;
}

export default function LibraryPage() {
  const [items, setItems] = useState<JellyfinItem[]>([]);
  const [continueWatching, setContinueWatching] = useState<JellyfinItem[]>([]);

  useEffect(() => {
    api.libraryItems({ type: "Movie,Series" }).then((r) => setItems(r.Items));
    api.continueWatching().then(setContinueWatching);
  }, []);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Your Library</h1>

      {continueWatching.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-xl font-semibold">Continue Watching</h2>
          <div className="rail flex gap-4 overflow-x-auto pb-2">
            {continueWatching.map((item) => (
              <LibraryCard key={item.Id} item={item} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-xl font-semibold">All Titles</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {items.map((item) => (
            <LibraryCard key={item.Id} item={item} />
          ))}
        </div>
        {items.length === 0 && <p className="text-vault-muted">Nothing available yet — request a title from Discover.</p>}
      </section>
    </div>
  );
}

function LibraryCard({ item }: { item: JellyfinItem }) {
  const img = imageUrl(item);
  const progress = item.UserData?.PlayedPercentage ?? 0;

  return (
    <Link href={`/watch/${item.Id}`} className="group relative overflow-hidden rounded-lg bg-vault-card">
      <div className="relative aspect-[2/3] w-full bg-vault-surface">
        {img ? (
          <Image src={img} alt={item.Name} fill sizes="200px" className="object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center px-2 text-center text-xs text-vault-muted">
            {item.Name}
          </div>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
          <PlayCircle className="h-10 w-10 text-white" />
        </div>
        {progress > 0 && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-black/50">
            <div className="h-full bg-vault-accent" style={{ width: `${progress}%` }} />
          </div>
        )}
      </div>
      <p className="truncate px-2 py-2 text-sm font-medium">{item.Name}</p>
    </Link>
  );
}
