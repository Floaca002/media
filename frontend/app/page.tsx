"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { PlayCircle, Info } from "lucide-react";
import { api, type TmdbItem } from "@/lib/api";
import { MediaRail } from "@/components/MediaRail";
import { SearchBar } from "@/components/SearchBar";

export default function DiscoverPage() {
  const [trending, setTrending] = useState<TmdbItem[]>([]);
  const [popularMovies, setPopularMovies] = useState<TmdbItem[]>([]);
  const [popularShows, setPopularShows] = useState<TmdbItem[]>([]);
  const [searchResults, setSearchResults] = useState<TmdbItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.trending("all"), api.popular("movie"), api.popular("tv")])
      .then(([t, m, s]) => {
        setTrending(t.results);
        setPopularMovies(m.results);
        setPopularShows(s.results);
      })
      .catch((err) => setError(err.message ?? "Failed to load Discover"));
  }, []);

  const runSearch = useCallback((query: string) => {
    if (!query) {
      setSearchResults(null);
      return;
    }
    api
      .search(query)
      .then((r) => setSearchResults(r.results))
      .catch(() => setSearchResults([]));
  }, []);

  const hero = trending[0];

  if (error) {
    return <p className="text-vault-muted">Could not reach Vault backend: {error}</p>;
  }

  return (
    <div>
      <div className="mb-6 flex justify-end">
        <SearchBar onSearch={runSearch} />
      </div>

      {searchResults ? (
        <MediaRail title="Search results" items={searchResults} />
      ) : (
        <>
          {hero && (
            <div className="relative mb-10 h-[420px] w-full overflow-hidden rounded-xl">
              {hero.backdrop_url && (
                <Image src={hero.backdrop_url} alt="" fill className="object-cover" priority />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-vault-bg via-vault-bg/40 to-transparent" />
              <div className="absolute bottom-8 left-8 max-w-xl">
                <h1 className="mb-3 text-4xl font-bold">{hero.title ?? hero.name}</h1>
                <p className="mb-4 line-clamp-3 text-sm text-vault-muted">{hero.overview}</p>
                <div className="flex gap-3">
                  <Link
                    href={`/media/${hero.media_type}/${hero.id}`}
                    className="flex items-center gap-2 rounded-md bg-vault-accent px-5 py-2.5 text-sm font-semibold hover:bg-red-700"
                  >
                    <PlayCircle className="h-5 w-5" /> View details
                  </Link>
                  <Link
                    href={`/media/${hero.media_type}/${hero.id}`}
                    className="flex items-center gap-2 rounded-md bg-vault-card px-5 py-2.5 text-sm font-semibold hover:bg-vault-surface"
                  >
                    <Info className="h-5 w-5" /> More info
                  </Link>
                </div>
              </div>
            </div>
          )}

          <MediaRail title="Trending now" items={trending} />
          <MediaRail title="Popular movies" items={popularMovies} />
          <MediaRail title="Popular TV shows" items={popularShows} />
        </>
      )}
    </div>
  );
}
