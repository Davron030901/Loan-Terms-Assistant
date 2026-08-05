"use client";

import { motion } from "framer-motion";
import { FileQuestion, ShieldAlert, ShieldCheck, ShieldX, TriangleAlert } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SourceDrawer } from "@/components/chat/SourceDrawer";
import { VERDICT_META } from "@/lib/constants";
import type { ChatMessage, Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS: Record<Verdict, typeof ShieldCheck> = {
  answered: ShieldCheck,
  refused_out_of_scope: ShieldAlert,
  blocked_not_grounded: ShieldX,
  not_stated: FileQuestion,
  error: TriangleAlert,
};

const HINTS: Partial<Record<Verdict, string>> = {
  refused_out_of_scope:
    "Try asking about interest, fees, penalties, repayment or what happens on default.",
  blocked_not_grounded:
    "The draft answer wasn't fully supported by the document, so it was withheld. That's the grounding guard doing its job.",
  not_stated: "This contract doesn't cover that. Nothing was invented to fill the gap.",
};

/** Renders (p. 4) as a clickable evidence chip. */
function withCitationChips(text: string, onOpen: (page: number) => void) {
  const parts = text.split(/(\(\s*pp?\.\s*[\d,\s.p]*\))/gi);
  return parts.map((part, index) => {
    const match = /\(\s*pp?\.\s*([\d,\s.p]*)\)/i.exec(part);
    if (!match) return <span key={index}>{part}</span>;
    const pages = (match[1].match(/\d+/g) ?? []).map(Number);
    return (
      <span key={index} className="ml-1 inline-flex gap-1 align-baseline">
        {pages.map((page) => (
          <button
            key={page}
            onClick={() => onOpen(page)}
            title={`Show the clause on page ${page}`}
            aria-label={`Page ${page}, source`}
            className="inline-flex items-center rounded-md bg-brand-500/12 px-1.5 py-0.5 font-mono text-[0.72rem] font-medium text-brand-700 transition hover:-translate-y-px hover:bg-brand-500/20 dark:text-brand-300"
          >
            p. {page}
          </button>
        ))}
      </span>
    );
  });
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const [drawerPage, setDrawerPage] = useState<number | null>(null);

  if (message.role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex justify-end"
      >
        <div className="wrap-anywhere max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[0.95rem] text-white shadow-sm sm:max-w-[75%]">
          {message.text}
        </div>
      </motion.div>
    );
  }

  if (message.pending && !message.text) return null;

  const verdict = message.verdict ?? "answered";
  const meta = VERDICT_META[verdict];
  const Icon = ICONS[verdict];
  const hint = HINTS[verdict];
  const plain = verdict !== "answered";

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24 }}
        className="flex justify-start"
      >
        <div
          className={cn(
            "wrap-anywhere relative w-full max-w-[92%] overflow-hidden rounded-2xl rounded-bl-md border px-4 py-3.5 pl-5 sm:max-w-[85%]",
            message.pending
              ? "border-dashed border-brand-500/40 bg-surface"
              : plain
                ? cn("border-transparent ring-1", meta.tone, meta.ring)
                : "border-hairline bg-surface",
          )}
        >
          <span className={cn("absolute inset-y-0 left-0 w-[3px]", meta.rail)} aria-hidden />

          <div className="mb-2 flex flex-wrap items-center gap-2">
            {message.pending ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-500/10 px-2 py-0.5 text-[0.7rem] font-medium text-brand-600 dark:text-brand-300">
                <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-brand-500" />
                Verifying against the document…
              </span>
            ) : (
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.7rem] font-medium",
                  meta.tone,
                  meta.text,
                )}
              >
                <Icon className="h-3 w-3" aria-hidden />
                {meta.label}
              </span>
            )}
          </div>

          <div className="prose-sm text-[0.95rem] leading-relaxed text-secondary">
            {verdict === "answered" ? (
              <div className="[&_p]:mb-2 [&_p:last-child]:mb-0 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => (
                      <p>
                        {typeof children === "string"
                          ? withCitationChips(children, setDrawerPage)
                          : Array.isArray(children)
                            ? children.map((child, i) =>
                                typeof child === "string" ? (
                                  <span key={i}>{withCitationChips(child, setDrawerPage)}</span>
                                ) : (
                                  child
                                ),
                              )
                            : children}
                      </p>
                    ),
                  }}
                >
                  {message.text}
                </ReactMarkdown>
              </div>
            ) : (
              <p>{message.text}</p>
            )}
          </div>

          {hint && !message.pending && <p className="mt-2.5 text-xs text-muted">{hint}</p>}

          {!!message.chunks?.length && !message.pending && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
              <button
                onClick={() => setDrawerPage(message.citations?.[0]?.page ?? -1)}
                className="rounded-lg bg-subtle px-2.5 py-1 text-xs font-medium text-secondary transition hover:bg-brand-500/10 hover:text-brand-600 dark:hover:text-brand-300"
              >
                Show sources ({message.chunks.length})
              </button>
              {message.trace?.grounding_guard?.method &&
                message.trace.grounding_guard.method !== "none" && (
                  <span className="font-mono text-[0.68rem] text-muted">
                    checked by {message.trace.grounding_guard.method}
                  </span>
                )}
            </div>
          )}

          {message.requestId && verdict === "error" && (
            <p className="mt-2 font-mono text-[0.65rem] text-muted">{message.requestId}</p>
          )}
        </div>
      </motion.div>

      <SourceDrawer
        open={drawerPage !== null}
        onClose={() => setDrawerPage(null)}
        chunks={message.chunks ?? []}
        focusPage={drawerPage ?? undefined}
      />
    </>
  );
}
