import type { TmdbItem } from "@/lib/api";
import { MediaCard } from "./MediaCard";

export function MediaRail({ title, items }: { title: string; items: TmdbItem[] }) {
  if (!items.length) return null;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-xl font-semibold text-vault-text">{title}</h2>
      <div className="rail flex gap-4 overflow-x-auto pb-2">
        {items.map((item) => (
          <MediaCard key={`${item.media_type}-${item.id}`} item={item} />
        ))}
      </div>
    </section>
  );
}
