"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Drawer } from "@/components/ui/Drawer";
import type { Chunk } from "@/lib/types";
import { cn } from "@/lib/utils";

function ChunkCard({ chunk, highlighted }: { chunk: Chunk; highlighted: boolean }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(chunk.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <article
      className={cn(
        "rounded-xl border p-3.5 transition",
        highlighted ? "border-brand-500/50 bg-brand-500/[0.05]" : "border-hairline bg-subtle/40",
      )}
    >
      <header className="mb-2.5 flex items-center justify-between gap-3">
        <span className="inline-flex items-center rounded-md bg-brand-500/12 px-2 py-0.5 font-mono text-xs font-medium text-brand-700 dark:text-brand-300">
          p. {chunk.page}
        </span>
        <div className="flex flex-1 items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-subtle">
            <div
              className="gradient-brand h-full rounded-full"
              style={{ width: `${Math.round(chunk.score * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[0.68rem] text-muted">{chunk.score.toFixed(2)}</span>
        </div>
        <button
          onClick={copy}
          aria-label={`Copy the clause from page ${chunk.page}`}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted transition hover:bg-subtle hover:text-primary"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-grounded-500" aria-hidden />
          ) : (
            <Copy className="h-3.5 w-3.5" aria-hidden />
          )}
        </button>
      </header>
      <p className="wrap-anywhere font-mono text-[0.8rem] leading-relaxed text-secondary">
        {chunk.text}
      </p>
    </article>
  );
}

export function SourceDrawer({
  open,
  onClose,
  chunks,
  focusPage,
}: {
  open: boolean;
  onClose: () => void;
  chunks: Chunk[];
  focusPage?: number;
}) {
  const ordered = [...chunks].sort((a, b) => {
    if (focusPage) {
      if (a.page === focusPage && b.page !== focusPage) return -1;
      if (b.page === focusPage && a.page !== focusPage) return 1;
    }
    return b.score - a.score;
  });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Source clauses"
      description="The exact text the answer was allowed to use."
    >
      <div className="space-y-3">
        {ordered.length === 0 && (
          <p className="text-sm text-muted">No clauses were retrieved for this message.</p>
        )}
        {ordered.map((chunk) => (
          <ChunkCard
            key={`${chunk.page}-${chunk.chunk_index}`}
            chunk={chunk}
            highlighted={chunk.page === focusPage}
          />
        ))}
      </div>
    </Drawer>
  );
}
