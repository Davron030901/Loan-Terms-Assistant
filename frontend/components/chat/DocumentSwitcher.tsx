"use client";

import { Check, ChevronDown, FileText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DocumentInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

export function DocumentSwitcher({
  documents,
  docId,
  onChange,
  hasMessages,
}: {
  documents: DocumentInfo[];
  docId: string;
  onChange: (id: string) => void;
  hasMessages: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const active = documents.find((d) => d.doc_id === docId);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const select = (id: string) => {
    setOpen(false);
    if (id === docId) return;
    if (
      hasMessages &&
      !window.confirm(
        "This assistant answers about one document at a time. Switching will clear the conversation.",
      )
    ) {
      return;
    }
    onChange(id);
  };

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex max-w-[15rem] items-center gap-2 rounded-xl border border-hairline bg-surface px-3 py-2 text-sm transition hover:border-brand-500/40 sm:max-w-xs"
      >
        <FileText className="h-4 w-4 shrink-0 text-brand-500" aria-hidden />
        <span className="truncate font-medium">{active?.bank ?? "Select a document"}</span>
        <ChevronDown
          className={cn("h-3.5 w-3.5 shrink-0 text-muted transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label="Loan document"
          className="absolute left-0 z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-hairline bg-surface p-1 shadow-xl"
        >
          {documents.map((doc) => (
            <li key={doc.doc_id}>
              <button
                role="option"
                aria-selected={doc.doc_id === docId}
                onClick={() => select(doc.doc_id)}
                className={cn(
                  "flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition",
                  doc.doc_id === docId ? "bg-brand-500/10" : "hover:bg-subtle",
                )}
              >
                <span className="mt-0.5 w-4 shrink-0">
                  {doc.doc_id === docId && <Check className="h-4 w-4 text-brand-500" aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{doc.bank}</span>
                    <span className="shrink-0 rounded bg-subtle px-1.5 font-mono text-[0.62rem] uppercase text-muted">
                      {doc.language}
                    </span>
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-muted">
                    {doc.jurisdiction} · {doc.pages} pages
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
