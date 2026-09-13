"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useParams } from "next/navigation";
import { Download, PlayCircle, Star } from "lucide-react";
import { api, type Availability, type TmdbDetails } from "@/lib/api";
import { MediaRail } from "@/components/MediaRail";

export default function MediaDetailPage() {
  const params = useParams<{ type: "movie" | "tv"; id: string }>();
  const [details, setDetails] = useState<TmdbDetails | null>(null);
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [showTrailer, setShowTrailer] = useState(false);
  const [magnetInput, setMagnetInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const tmdbId = Number(params.id);
  const mediaType = params.type;

  useEffect(() => {
    setLoadError(null);
    api
      .details(mediaType, tmdbId)
      .then(setDetails)
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load title"));
    api.availability(mediaType, tmdbId).then(setAvailability).catch(() => {});
  }, [mediaType, tmdbId]);

  async function submitRequest() {
    if (!details || !magnetInput.startsWith("magnet:")) {
      setMessage("Paste a valid magnet link first.");
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      await api.createRequest({
        tmdb_id: tmdbId,
        media_type: mediaType,
        title: details.title ?? details.name ?? "Untitled",
        magnet: magnetInput,
      });
      setAvailability({ status: "DOWNLOADING", jellyfin_item_id: null });
      setMessage("Added to Downloads.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to create request");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) return <p className="text-vault-muted">Could not load this title: {loadError}</p>;
  if (!details) return <p className="text-vault-muted">Loading...</p>;

  const title = details.title ?? details.name ?? "Untitled";
  const isAvailable = availability?.status === "AVAILABLE";
  const isDownloading = availability?.status === "DOWNLOADING" || availability?.status === "SEARCHING";

  return (
    <div>
      <div className="relative -mx-6 -mt-6 mb-6 h-[380px] w-[calc(100%+3rem)] overflow-hidden">
        {details.backdrop_url && (
          <Image src={details.backdrop_url} alt="" fill className="object-cover" priority />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-vault-bg via-vault-bg/50 to-transparent" />
      </div>

      <div className="flex flex-col gap-8 md:flex-row">
        {details.poster_url && (
          <Image
            src={details.poster_url}
            alt={title}
            width={260}
            height={390}
            className="h-fit rounded-lg shadow-2xl"
          />
        )}

        <div className="flex-1">
          <h1 className="mb-2 text-3xl font-bold">{title}</h1>
          <div className="mb-4 flex items-center gap-3 text-sm text-vault-muted">
            <span className="flex items-center gap-1 text-yellow-400">
              <Star className="h-4 w-4 fill-yellow-400" /> {details.vote_average?.toFixed(1)}
            </span>
            {details.runtime && <span>{details.runtime} min</span>}
            <span>{(details.release_date ?? details.first_air_date ?? "").slice(0, 4)}</span>
            <span>{details.genres?.map((g) => g.name).join(", ")}</span>
          </div>

          <p className="mb-6 max-w-2xl text-vault-text/90">{details.overview}</p>

          <div className="mb-8 flex flex-wrap gap-3">
            {isAvailable ? (
              <a
                href={`/watch/${availability?.jellyfin_item_id}`}
                className="flex items-center gap-2 rounded-md bg-vault-accent px-6 py-3 font-semibold hover:bg-red-700"
              >
                <PlayCircle className="h-5 w-5" /> Watch Now
              </a>
            ) : isDownloading ? (
              <span className="flex items-center gap-2 rounded-md bg-vault-card px-6 py-3 font-semibold text-vault-muted">
                <Download className="h-5 w-5 animate-pulse" /> {availability?.status.toLowerCase()}...
              </span>
            ) : (
              <div className="flex w-full max-w-lg flex-col gap-2 sm:flex-row">
                <input
                  value={magnetInput}
                  onChange={(e) => setMagnetInput(e.target.value)}
                  placeholder="Paste magnet link to download"
                  className="flex-1 rounded-md border border-vault-border bg-vault-surface px-3 py-2 text-sm placeholder:text-vault-muted focus:border-vault-accent focus:outline-none"
                />
                <button
                  onClick={submitRequest}
                  disabled={submitting}
                  className="flex items-center justify-center gap-2 rounded-md bg-vault-accent px-6 py-2.5 font-semibold hover:bg-red-700 disabled:opacity-50"
                >
                  <Download className="h-5 w-5" /> Download
                </button>
              </div>
            )}

            {details.trailer_key && (
              <button
                onClick={() => setShowTrailer(true)}
                className="rounded-md bg-vault-card px-6 py-3 font-semibold hover:bg-vault-surface"
              >
                Watch Trailer
              </button>
            )}
          </div>

          {message && <p className="mb-6 text-sm text-vault-muted">{message}</p>}

          {details.cast?.length > 0 && (
            <div className="mb-8">
              <h2 className="mb-3 text-xl font-semibold">Cast</h2>
              <div className="rail flex gap-4 overflow-x-auto pb-2">
                {details.cast.map((c) => (
                  <div key={c.id} className="w-24 shrink-0 text-center">
                    <div className="mb-2 h-24 w-24 overflow-hidden rounded-full bg-vault-card">
                      {c.profile_path && (
                        <Image
                          src={`https://image.tmdb.org/t/p/w200${c.profile_path}`}
                          alt={c.name}
                          width={96}
                          height={96}
                          className="h-full w-full object-cover"
                        />
                      )}
                    </div>
                    <p className="truncate text-xs font-medium">{c.name}</p>
                    <p className="truncate text-xs text-vault-muted">{c.character}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <MediaRail title="More like this" items={details.similar ?? []} />

      {showTrailer && details.trailer_key && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setShowTrailer(false)}
        >
          <div className="aspect-video w-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
            <iframe
              className="h-full w-full rounded-lg"
              src={`https://www.youtube.com/embed/${details.trailer_key}?autoplay=1`}
              title="Trailer"
              allow="autoplay; encrypted-media"
              allowFullScreen
            />
          </div>
        </div>
      )}
    </div>
  );
}
