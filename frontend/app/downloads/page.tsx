"use client";

import { useEffect, useRef, useState } from "react";
import { api, downloadsSocketUrl, type DownloadOut } from "@/lib/api";
import { DownloadRow } from "@/components/DownloadRow";

export default function DownloadsPage() {
  const [downloads, setDownloads] = useState<DownloadOut[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const socket = new WebSocket(downloadsSocketUrl());
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (Array.isArray(data)) setDownloads(data);
    };
    socket.onclose = () => {
      setConnected(false);
      // Fallback to polling if the WebSocket drops (e.g. proxy without WS support).
      pollRef.current = setInterval(() => {
        api.downloads().then(setDownloads).catch(() => {});
      }, 3000);
    };

    return () => {
      socket.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handlePause(hash: string) {
    await api.pauseDownload(hash);
  }
  async function handleResume(hash: string) {
    await api.resumeDownload(hash);
  }
  async function handleDelete(hash: string) {
    if (!confirm("Delete this download and its files?")) return;
    await api.deleteDownload(hash, true);
    setDownloads((prev) => prev.filter((d) => d.hash !== hash));
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Downloads</h1>
        <span className={`text-xs ${connected ? "text-green-400" : "text-vault-muted"}`}>
          {connected ? "● Live" : "○ Polling"}
        </span>
      </div>

      {downloads.length === 0 ? (
        <p className="text-vault-muted">No active downloads.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {downloads.map((d) => (
            <DownloadRow
              key={d.hash}
              download={d}
              onPause={handlePause}
              onResume={handleResume}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
