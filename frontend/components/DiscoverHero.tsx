"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Info, PlayCircle, Volume2, VolumeX } from "lucide-react";
import { api, type TmdbItem } from "@/lib/api";

/** Netflix-style hero: starts on the backdrop image, then fades into a
 *  muted, looping trailer preview a moment after landing on the title. */
export function DiscoverHero({ item }: { item: TmdbItem }) {
  const [trailerKey, setTrailerKey] = useState<string | null>(null);
  const [playingTrailer, setPlayingTrailer] = useState(false);
  const [muted, setMuted] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    setTrailerKey(null);
    setPlayingTrailer(false);
    setMuted(true);
    api
      .details(item.media_type, item.id)
      .then((d) => {
        if (d.trailer_key) setTrailerKey(d.trailer_key);
      })
      .catch(() => {});
  }, [item.id, item.media_type]);

  useEffect(() => {
    if (!trailerKey) return;
    const timer = setTimeout(() => setPlayingTrailer(true), 1500);
    return () => clearTimeout(timer);
  }, [trailerKey]);

  function toggleMute() {
    const next = !muted;
    setMuted(next);
    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({ event: "command", func: next ? "mute" : "unMute", args: [] }),
      "*"
    );
  }

  const title = item.title ?? item.name ?? "Untitled";

  return (
    <div className="relative mb-10 h-[65vh] max-h-[560px] min-h-[380px] w-full overflow-hidden rounded-xl bg-black">
      {playingTrailer && trailerKey ? (
        <iframe
          ref={iframeRef}
          className="absolute inset-0 h-full w-full scale-125"
          src={`https://www.youtube.com/embed/${trailerKey}?autoplay=1&mute=1&controls=0&loop=1&playlist=${trailerKey}&modestbranding=1&rel=0&enablejsapi=1&showinfo=0`}
          allow="autoplay; encrypted-media"
          title="Trailer preview"
        />
      ) : (
        item.backdrop_url && <Image src={item.backdrop_url} alt="" fill className="object-cover" priority />
      )}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-vault-bg via-vault-bg/40 to-transparent" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-vault-bg/70 via-transparent to-transparent" />

      <div className="absolute bottom-8 left-8 max-w-xl">
        <h1 className="mb-3 text-4xl font-bold drop-shadow-lg">{title}</h1>
        <p className="mb-4 line-clamp-3 text-sm text-vault-text/90 drop-shadow">{item.overview}</p>
        <div className="flex items-center gap-3">
          <Link
            href={`/media/${item.media_type}/${item.id}`}
            className="flex items-center gap-2 rounded-md bg-vault-accent px-5 py-2.5 text-sm font-semibold hover:bg-red-700"
          >
            <PlayCircle className="h-5 w-5" /> View details
          </Link>
          <Link
            href={`/media/${item.media_type}/${item.id}`}
            className="flex items-center gap-2 rounded-md bg-vault-card px-5 py-2.5 text-sm font-semibold hover:bg-vault-surface"
          >
            <Info className="h-5 w-5" /> More info
          </Link>
          {playingTrailer && trailerKey && (
            <button
              onClick={toggleMute}
              className="ml-2 flex items-center justify-center rounded-full border border-white/40 p-2.5 text-white hover:bg-white/10"
              aria-label={muted ? "Unmute preview" : "Mute preview"}
            >
              {muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
