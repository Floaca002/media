"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { api, type PlaybackInfo } from "@/lib/api";
import { VideoPlayer } from "@/components/VideoPlayer";

export default function WatchPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [playback, setPlayback] = useState<PlaybackInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hasReportedStart = useRef(false);

  useEffect(() => {
    api
      .playbackInfo(params.id)
      .then(setPlayback)
      .catch((err) => setError(err.message ?? "Could not start playback"));
  }, [params.id]);

  useEffect(() => {
    if (!playback || hasReportedStart.current) return;
    hasReportedStart.current = true;
    api.reportProgress({
      item_id: params.id,
      play_session_id: playback.play_session_id,
      media_source_id: playback.media_source_id,
      position_ticks: playback.start_position_ticks,
      event: "start",
    });
  }, [playback, params.id]);

  const handleProgress = useCallback(
    (positionTicks: number, isPaused: boolean) => {
      if (!playback) return;
      api.reportProgress({
        item_id: params.id,
        play_session_id: playback.play_session_id,
        media_source_id: playback.media_source_id,
        position_ticks: positionTicks,
        is_paused: isPaused,
        event: "progress",
      });
    },
    [playback, params.id]
  );

  const handleEnded = useCallback(() => {
    if (!playback) return;
    api.reportProgress({
      item_id: params.id,
      play_session_id: playback.play_session_id,
      media_source_id: playback.media_source_id,
      position_ticks: 0,
      event: "stop",
    });
    router.push("/library");
  }, [playback, params.id, router]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24">
        <p className="text-vault-muted">{error}</p>
        <button onClick={() => router.back()} className="text-vault-accent">
          Go back
        </button>
      </div>
    );
  }

  if (!playback) return <p className="text-vault-muted">Preparing stream...</p>;

  return (
    <div className="-mx-6 -mt-6">
      <button
        onClick={() => router.back()}
        className="absolute z-10 m-4 flex items-center gap-1 rounded-full bg-black/60 px-3 py-2 text-sm hover:bg-black/80"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>
      <div className="aspect-video w-full bg-black">
        <VideoPlayer
          src={playback.hls_url}
          startPositionTicks={playback.start_position_ticks}
          onProgress={handleProgress}
          onEnded={handleEnded}
        />
      </div>
    </div>
  );
}
