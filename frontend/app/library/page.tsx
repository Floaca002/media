"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { PlayCircle } from "lucide-react";
import { api, jellyfinImageUrl, type JellyfinItem } from "@/lib/api";

type Filter = "all" | "movie" | "tv";

export default function LibraryPage() {
  const [items, setItems] = useState<JellyfinItem[]>([]);
  const [continueWatching, setContinueWatching] = useState<JellyfinItem[]>([]);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    api.libraryItems({ type: "Movie,Series" }).then((r) => setItems(r.Items));
    api.continueWatching().then(setContinueWatching);
  }, []);

  const filteredItems = useMemo(() => {
    if (filter === "all") return items;
    const wantType = filter === "movie" ? "Movie" : "Series";
    return items.filter((item) => item.Type === wantType);
  }, [items, filter]);

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Your Library</h1>
        <div className="flex gap-1 rounded-md bg-vault-card p-1">
          {(["all", "movie", "tv"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded px-4 py-1.5 text-sm font-medium transition-colors ${
                filter === f ? "bg-vault-accent text-white" : "text-vault-muted hover:text-vault-text"
              }`}
            >
              {f === "all" ? "All" : f === "movie" ? "Movies" : "TV Shows"}
            </button>
          ))}
        </div>
      </div>

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
        <h2 className="mb-3 text-xl font-semibold">
          {filter === "all" ? "All Titles" : filter === "movie" ? "Movies" : "TV Shows"}
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {filteredItems.map((item) => (
            <LibraryCard key={item.Id} item={item} />
          ))}
        </div>
        {filteredItems.length === 0 && (
          <p className="text-vault-muted">Nothing available yet — request a title from Discover.</p>
        )}
      </section>
    </div>
  );
}

function LibraryCard({ item }: { item: JellyfinItem }) {
  const img = jellyfinImageUrl(item);
  const progress = item.UserData?.PlayedPercentage ?? 0;
  // A Series has no video file of its own — it needs a season/episode
  // picked first, so it links to the show page instead of straight to
  // the player the way a Movie (or an episode from Continue Watching) does.
  const href = item.Type === "Series" ? `/show/${item.Id}` : `/watch/${item.Id}`;

  return (
    <Link href={href} className="group relative overflow-hidden rounded-lg bg-vault-card">
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
          <div className="absolute inset-x-0 bottom-0 flex flex-col">
            <span className="bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
              {Math.round(progress)}% watched
            </span>
            <div className="h-1 bg-black/50">
              <div className="h-full bg-vault-accent" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}
      </div>
      <p className="truncate px-2 py-2 text-sm font-medium">{item.Name}</p>
    </Link>
  );
}
