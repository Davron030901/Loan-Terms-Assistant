"use client";

import { ArrowDown, Activity, Eraser, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Composer } from "@/components/chat/Composer";
import { DocumentSwitcher } from "@/components/chat/DocumentSwitcher";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { TracePanel } from "@/components/chat/TracePanel";
import { Drawer } from "@/components/ui/Drawer";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { useChat } from "@/hooks/useChat";
import { OFF_TOPIC_PROBE, SUGGESTED } from "@/lib/constants";

export function ChatShell() {
  const params = useSearchParams();
  const chat = useChat(params.get("doc") ?? undefined);
  const [traceOpen, setTraceOpen] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // Follow the conversation only when the reader is already at the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (nearBottom) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      setShowJump(false);
    } else if (chat.messages.length) {
      setShowJump(true);
    }
  }, [chat.messages]);

  const suggestions = SUGGESTED[chat.docId] ?? SUGGESTED.cibc_personal;
  const empty = chat.messages.length === 0;

  return (
    <div className="flex h-[100dvh] flex-col">
      <header className="z-30 shrink-0 border-b border-hairline bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4">
          <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="Home">
            <span className="gradient-brand flex h-8 w-8 items-center justify-center rounded-xl">
              <ShieldCheck className="h-4 w-4 text-white" aria-hidden />
            </span>
          </Link>

          <DocumentSwitcher
            documents={chat.documents}
            docId={chat.docId}
            onChange={chat.switchDocument}
            hasMessages={chat.messages.length > 0}
          />

          {chat.activeDocument && chat.activeDocument.chunks > 0 && (
            <span className="hidden shrink-0 rounded-lg bg-subtle px-2 py-1 font-mono text-[0.68rem] text-muted lg:inline">
              {chat.activeDocument.chunks} clauses indexed
            </span>
          )}

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setTraceOpen(true)}
              className="flex items-center gap-1.5 rounded-xl border border-hairline px-3 py-2 text-xs font-medium text-secondary transition hover:bg-subtle lg:hidden"
            >
              <Activity className="h-3.5 w-3.5" aria-hidden />
              Reasoning
            </button>
            {!empty && (
              <button
                onClick={chat.clear}
                aria-label="Clear conversation"
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-hairline text-muted transition hover:bg-subtle hover:text-primary"
              >
                <Eraser className="h-4 w-4" aria-hidden />
              </button>
            )}
            <div className="hidden sm:block">
              <ThemeToggle />
            </div>
          </div>
        </div>

        {chat.waking && (
          <div className="border-t border-refused-500/20 bg-refused-500/[0.07] px-4 py-2">
            <p className="mx-auto flex max-w-7xl items-center gap-2 text-xs text-refused-700 dark:text-refused-300">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-refused-500" />
              Waking the server — it sleeps on the free tier, so the first request can take ~30
              seconds.
            </p>
          </div>
        )}
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1 gap-6 overflow-hidden px-0 lg:px-4">
        <main id="main" className="relative flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto overscroll-contain">
            <div
              className="mx-auto max-w-3xl space-y-4 px-4 py-6"
              role="log"
              aria-live="polite"
              aria-relevant="additions"
              aria-label="Conversation"
            >
              {empty ? (
                <div className="pt-6 sm:pt-12">
                  <div className="text-center">
                    <span className="gradient-brand mx-auto flex h-12 w-12 items-center justify-center rounded-2xl shadow-[var(--shadow-glow)]">
                      <Sparkles className="h-5 w-5 text-white" aria-hidden />
                    </span>
                    <h1 className="mt-4 text-xl font-semibold">
                      Ask about {chat.activeDocument?.bank ?? "this loan document"}
                    </h1>
                    <p className="mx-auto mt-2 max-w-md text-pretty text-sm leading-relaxed text-secondary">
                      Every answer is quoted from the contract with a page number. Anything the
                      document doesn&apos;t say, this assistant won&apos;t say either.
                    </p>
                  </div>

                  <div className="mt-8 grid gap-2 sm:grid-cols-2">
                    {suggestions.map((question) => (
                      <button
                        key={question}
                        onClick={() => chat.send(question)}
                        disabled={chat.loadingDocs}
                        className="card px-4 py-3 text-left text-sm text-secondary transition hover:border-brand-500/40 hover:text-primary disabled:opacity-50"
                      >
                        {question}
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={() => chat.send(OFF_TOPIC_PROBE)}
                    disabled={chat.loadingDocs}
                    className="mt-3 w-full rounded-xl border border-dashed border-refused-500/40 bg-refused-500/[0.05] px-4 py-3 text-left text-sm text-refused-700 transition hover:bg-refused-500/10 disabled:opacity-50 dark:text-refused-300"
                  >
                    Try an off-topic question → watch the scope guard refuse it
                  </button>
                </div>
              ) : (
                chat.messages.map((message) => <MessageBubble key={message.id} message={message} />)
              )}
              <div ref={endRef} />
            </div>
          </div>

          {showJump && (
            <button
              onClick={() => {
                endRef.current?.scrollIntoView({ behavior: "smooth" });
                setShowJump(false);
              }}
              className="glass absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium shadow-lg"
            >
              <ArrowDown className="h-3.5 w-3.5" aria-hidden />
              New message
            </button>
          )}

          <Composer
            onSend={chat.send}
            onStop={chat.stop}
            busy={chat.busy}
            disabled={chat.loadingDocs || !chat.docId}
          />
        </main>

        <aside className="hidden w-[340px] shrink-0 overflow-y-auto py-6 lg:block">
          <div className="sticky top-0">
            <TracePanel stages={chat.stages} busy={chat.busy} />
          </div>
        </aside>
      </div>

      <Drawer
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        title="Agent trace"
        description="What the agent did with your last question."
      >
        <TracePanel stages={chat.stages} busy={chat.busy} />
      </Drawer>
    </div>
  );
}
