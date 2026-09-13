"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PlayCircle, CheckCircle2 } from "lucide-react";
import { api, jellyfinImageUrl, type JellyfinItem } from "@/lib/api";

const TICKS_PER_MINUTE = 600_000_000;

export default function ShowPage() {
  const params = useParams<{ id: string }>();
  const [series, setSeries] = useState<JellyfinItem | null>(null);
  const [seasons, setSeasons] = useState<JellyfinItem[]>([]);
  const [selectedSeasonId, setSelectedSeasonId] = useState<string | null>(null);
  const [episodes, setEpisodes] = useState<JellyfinItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .itemDetail(params.id)
      .then(setSeries)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load show"));
    api
      .seasons(params.id)
      .then((s) => {
        setSeasons(s);
        if (s.length > 0) setSelectedSeasonId(s[0].Id);
      })
      .catch(() => {});
  }, [params.id]);

  useEffect(() => {
    if (!selectedSeasonId) return;
    api
      .episodes(params.id, selectedSeasonId)
      .then(setEpisodes)
      .catch(() => setEpisodes([]));
  }, [params.id, selectedSeasonId]);

  if (error) return <p className="text-vault-muted">Could not load this show: {error}</p>;
  if (!series) return <p className="text-vault-muted">Loading...</p>;

  const poster = jellyfinImageUrl(series);

  return (
    <div>
      <div className="mb-8 flex flex-col gap-8 md:flex-row">
        {poster && (
          <Image src={poster} alt={series.Name} width={260} height={390} className="h-fit rounded-lg shadow-2xl" />
        )}
        <div className="flex-1">
          <h1 className="mb-2 text-3xl font-bold">{series.Name}</h1>
          {series.ProductionYear && <p className="mb-4 text-sm text-vault-muted">{series.ProductionYear}</p>}
          {series.Overview && <p className="max-w-2xl text-vault-text/90">{series.Overview}</p>}
        </div>
      </div>

      {seasons.length > 0 && (
        <div className="mb-6 flex gap-2 overflow-x-auto pb-2">
          {seasons.map((season) => (
            <button
              key={season.Id}
              onClick={() => setSelectedSeasonId(season.Id)}
              className={`shrink-0 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                selectedSeasonId === season.Id
                  ? "bg-vault-accent text-white"
                  : "bg-vault-card text-vault-muted hover:text-vault-text"
              }`}
            >
              {season.Name}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {episodes.map((episode) => (
          <EpisodeRow key={episode.Id} episode={episode} />
        ))}
        {seasons.length > 0 && episodes.length === 0 && (
          <p className="text-vault-muted">No episodes available in this season yet.</p>
        )}
        {seasons.length === 0 && (
          <p className="text-vault-muted">No seasons found for this show yet — check back once more has downloaded.</p>
        )}
      </div>
    </div>
  );
}

function EpisodeRow({ episode }: { episode: JellyfinItem }) {
  const thumb = jellyfinImageUrl(episode);
  const progress = episode.UserData?.PlayedPercentage ?? 0;
  const watched = episode.UserData?.Played;
  const runtimeMin = episode.RunTimeTicks ? Math.round(episode.RunTimeTicks / TICKS_PER_MINUTE) : null;

  return (
    <Link
      href={`/watch/${episode.Id}`}
      className="group flex gap-4 rounded-lg bg-vault-card p-3 transition-colors hover:bg-vault-surface"
    >
      <div className="relative h-24 w-40 shrink-0 overflow-hidden rounded bg-vault-surface">
        {thumb ? (
          <Image src={thumb} alt={episode.Name} fill className="object-cover" sizes="160px" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-vault-muted">No preview</div>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
          <PlayCircle className="h-8 w-8 text-white" />
        </div>
        {progress > 0 && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-black/50">
            <div className="h-full bg-vault-accent" style={{ width: `${progress}%` }} />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <p className="truncate font-medium">
            {episode.IndexNumber != null ? `${episode.IndexNumber}. ` : ""}
            {episode.Name}
          </p>
          {watched && <CheckCircle2 className="h-4 w-4 shrink-0 text-vault-accent" />}
        </div>
        <p className="mb-1 text-xs text-vault-muted">
          {runtimeMin ? `${runtimeMin} min` : ""}
          {progress > 0 && !watched ? ` · ${Math.round(progress)}% watched` : ""}
        </p>
        {episode.Overview && <p className="line-clamp-2 text-sm text-vault-text/80">{episode.Overview}</p>}
      </div>
    </Link>
  );
}
