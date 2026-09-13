import { Pause, Play, Trash2 } from "lucide-react";
import type { DownloadOut } from "@/lib/api";

function formatBytes(bytesPerSec: number): string {
  if (bytesPerSec <= 0) return "0 KB/s";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytesPerSec;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}/s`;
}

function formatEta(seconds: number | null): string {
  if (seconds === null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const PAUSED_STATES = new Set(["pausedDL", "pausedUP"]);

export function DownloadRow({
  download,
  onPause,
  onResume,
  onDelete,
}: {
  download: DownloadOut;
  onPause: (hash: string) => void;
  onResume: (hash: string) => void;
  onDelete: (hash: string) => void;
}) {
  const isPaused = PAUSED_STATES.has(download.state);

  return (
    <div className="rounded-lg border border-vault-border bg-vault-card p-4">
      <div className="mb-2 flex items-center justify-between gap-4">
        <p className="truncate font-medium">{download.name}</p>
        <div className="flex shrink-0 gap-2">
          {isPaused ? (
            <button
              onClick={() => onResume(download.hash)}
              className="rounded-md bg-vault-surface p-2 hover:bg-vault-border"
              title="Resume"
            >
              <Play className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={() => onPause(download.hash)}
              className="rounded-md bg-vault-surface p-2 hover:bg-vault-border"
              title="Pause"
            >
              <Pause className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => onDelete(download.hash)}
            className="rounded-md bg-vault-surface p-2 text-red-400 hover:bg-vault-border"
            title="Delete"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-vault-surface">
        <div
          className="h-full rounded-full bg-vault-accent transition-all"
          style={{ width: `${download.progress}%` }}
        />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-vault-muted">
        <span>{download.progress.toFixed(1)}%</span>
        <span>↓ {formatBytes(download.download_speed_bps)}</span>
        <span>↑ {formatBytes(download.upload_speed_bps)}</span>
        <span>ETA {formatEta(download.eta_seconds)}</span>
        <span className="capitalize">{download.state}</span>
      </div>
    </div>
  );
}
