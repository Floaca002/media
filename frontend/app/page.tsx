"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type TmdbItem } from "@/lib/api";
import { MediaRail } from "@/components/MediaRail";
import { SearchBar } from "@/components/SearchBar";
import { DiscoverHero } from "@/components/DiscoverHero";

type Filter = "all" | "movie" | "tv";

interface Rail {
  title: string;
  items: TmdbItem[];
}

export default function DiscoverPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [trendingAll, setTrendingAll] = useState<TmdbItem[]>([]);
  const [trendingMovies, setTrendingMovies] = useState<TmdbItem[]>([]);
  const [trendingShows, setTrendingShows] = useState<TmdbItem[]>([]);
  const [popularMovies, setPopularMovies] = useState<TmdbItem[]>([]);
  const [popularShows, setPopularShows] = useState<TmdbItem[]>([]);
  const [topRatedMovies, setTopRatedMovies] = useState<TmdbItem[]>([]);
  const [topRatedShows, setTopRatedShows] = useState<TmdbItem[]>([]);
  const [nowPlaying, setNowPlaying] = useState<TmdbItem[]>([]);
  const [onTheAir, setOnTheAir] = useState<TmdbItem[]>([]);
  const [searchResults, setSearchResults] = useState<TmdbItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.trending("all"),
      api.trending("movie"),
      api.trending("tv"),
      api.popular("movie"),
      api.popular("tv"),
      api.topRated("movie"),
      api.topRated("tv"),
      api.nowPlaying(),
      api.onTheAir(),
    ])
      .then(([all, movies, shows, pMovies, pShows, tMovies, tShows, playing, air]) => {
        setTrendingAll(all.results);
        setTrendingMovies(movies.results);
        setTrendingShows(shows.results);
        setPopularMovies(pMovies.results);
        setPopularShows(pShows.results);
        setTopRatedMovies(tMovies.results);
        setTopRatedShows(tShows.results);
        setNowPlaying(playing.results);
        setOnTheAir(air.results);
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

  const rails: Rail[] = useMemo(() => {
    if (filter === "movie") {
      return [
        { title: "Trending movies", items: trendingMovies },
        { title: "Now playing in theaters", items: nowPlaying },
        { title: "Popular movies", items: popularMovies },
        { title: "Top rated movies", items: topRatedMovies },
      ];
    }
    if (filter === "tv") {
      return [
        { title: "Trending TV shows", items: trendingShows },
        { title: "Airing this week", items: onTheAir },
        { title: "Popular TV shows", items: popularShows },
        { title: "Top rated TV shows", items: topRatedShows },
      ];
    }
    return [
      { title: "Trending now", items: trendingAll },
      { title: "Popular movies", items: popularMovies },
      { title: "Popular TV shows", items: popularShows },
      { title: "Now playing in theaters", items: nowPlaying },
      { title: "Airing this week", items: onTheAir },
      { title: "Top rated movies", items: topRatedMovies },
      { title: "Top rated TV shows", items: topRatedShows },
    ];
  }, [
    filter,
    trendingAll,
    trendingMovies,
    trendingShows,
    popularMovies,
    popularShows,
    topRatedMovies,
    topRatedShows,
    nowPlaying,
    onTheAir,
  ]);

  const hero =
    filter === "movie" ? trendingMovies[0] : filter === "tv" ? trendingShows[0] : trendingAll[0];

  if (error) {
    return <p className="text-vault-muted">Could not reach Vault backend: {error}</p>;
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
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
        <SearchBar onSearch={runSearch} />
      </div>

      {searchResults ? (
        <MediaRail title="Search results" items={searchResults} />
      ) : (
        <>
          {hero && <DiscoverHero item={hero} />}
          {rails.map((rail) => (
            <MediaRail key={rail.title} title={rail.title} items={rail.items} />
          ))}
        </>
      )}
    </div>
  );
}
