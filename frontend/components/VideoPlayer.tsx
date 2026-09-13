"use client";

import Hls from "hls.js";
import { useEffect, useRef } from "react";
import { getToken } from "@/lib/api";

const TICKS_PER_SECOND = 10_000_000; // Jellyfin uses 100-nanosecond ticks
const REPORT_INTERVAL_MS = 10_000;

interface VideoPlayerProps {
  src: string;
  startPositionTicks?: number;
  onProgress: (positionTicks: number, isPaused: boolean) => void;
  onEnded?: () => void;
}

export function VideoPlayer({ src, startPositionTicks = 0, onProgress, onEnded }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls: Hls | null = null;

    if (Hls.isSupported()) {
      // hls.js issues every request (master playlist, variant playlists,
      // and each segment) through its own configurable loader, so this is
      // the one path that can actually attach the Vault JWT the backend's
      // /api/stream proxy requires — a plain <video src> assignment (the
      // Safari-native-HLS branch this used to take) cannot set custom
      // headers at all, so Safari isn't supported by this player yet.
      hls = new Hls({
        maxBufferLength: 30,
        xhrSetup: (xhr) => {
          const token = getToken();
          if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        },
      });
      hls.loadSource(src);
      hls.attachMedia(video);
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
    }

    const startSeconds = startPositionTicks / TICKS_PER_SECOND;
    const onLoadedMetadata = () => {
      if (startSeconds > 0) video.currentTime = startSeconds;
      video.play().catch(() => {
        /* autoplay may be blocked until user interacts */
      });
    };
    video.addEventListener("loadedmetadata", onLoadedMetadata);

    const reportInterval = setInterval(() => {
      if (video.readyState > 0) {
        onProgress(Math.floor(video.currentTime * TICKS_PER_SECOND), video.paused);
      }
    }, REPORT_INTERVAL_MS);

    const onEndedEvent = () => onEnded?.();
    video.addEventListener("ended", onEndedEvent);

    return () => {
      clearInterval(reportInterval);
      video.removeEventListener("loadedmetadata", onLoadedMetadata);
      video.removeEventListener("ended", onEndedEvent);
      hls?.destroy();
    };
  }, [src, startPositionTicks, onProgress, onEnded]);

  return (
    <video
      ref={videoRef}
      controls
      className="h-full w-full bg-black"
      playsInline
    />
  );
}
