"use client";

import Image from "next/image";
import Link from "next/link";
import { Star } from "lucide-react";
import type { TmdbItem } from "@/lib/api";

export function MediaCard({ item }: { item: TmdbItem }) {
  const title = item.title ?? item.name ?? "Untitled";
  const year = (item.release_date ?? item.first_air_date ?? "").slice(0, 4);

  return (
    <Link
      href={`/media/${item.media_type}/${item.id}`}
      className="group relative w-[160px] shrink-0 overflow-hidden rounded-lg bg-vault-card transition-transform duration-200 hover:z-10 hover:scale-105 sm:w-[180px]"
    >
      <div className="relative aspect-[2/3] w-full bg-vault-surface">
        {item.poster_url ? (
          <Image
            src={item.poster_url}
            alt={title}
            fill
            sizes="180px"
            className="object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-2 text-center text-xs text-vault-muted">
            {title}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/90 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
          <span className="flex items-center gap-1 text-xs font-medium text-yellow-400">
            <Star className="h-3 w-3 fill-yellow-400" />
            {item.vote_average?.toFixed(1)}
          </span>
          {year && <span className="text-xs text-vault-muted">{year}</span>}
        </div>
      </div>
      <p className="truncate px-1 py-2 text-sm font-medium text-vault-text">{title}</p>
    </Link>
  );
}
