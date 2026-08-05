"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, getDocuments, pingHealth, streamChat } from "@/lib/api";
import type { ChatMessage, DocumentInfo, TraceEvent, TraceStage } from "@/lib/types";
import { uid } from "@/lib/utils";

export type StageState = Partial<Record<TraceStage, { status: "running" | "done" } & Record<string, unknown>>>;

export function useChat(initialDocId?: string) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [docId, setDocId] = useState<string>(initialDocId ?? "");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [stages, setStages] = useState<StageState>({});
  const [waking, setWaking] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  // Wake a sleeping Render free-tier instance, then load the corpus.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => !cancelled && setWaking(true), 2500);

    (async () => {
      await pingHealth();
      try {
        const data = await getDocuments();
        if (cancelled) return;
        setDocuments(data.documents);
        setDocId((current) => {
          if (current && data.documents.some((d) => d.doc_id === current)) return current;
          const stored = localStorage.getItem("lta-doc");
          if (stored && data.documents.some((d) => d.doc_id === stored)) return stored;
          return data.default_doc_id;
        });
      } catch {
        /* surfaced by the empty-state UI */
      } finally {
        if (!cancelled) {
          clearTimeout(timer);
          setWaking(false);
          setLoadingDocs(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (docId) localStorage.setItem("lta-doc", docId);
  }, [docId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setMessages((prev) => prev.filter((m) => !m.pending));
  }, []);

  const clear = useCallback(() => {
    stop();
    setMessages([]);
    setStages({});
  }, [stop]);

  const switchDocument = useCallback(
    (next: string) => {
      if (next === docId) return;
      clear();
      setDocId(next);
    },
    [docId, clear],
  );

  const send = useCallback(
    async (raw: string) => {
      const question = raw.trim();
      if (!question || busy || !docId) return;

      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      setStages({ scope_guard: { status: "running" } });

      const pendingId = uid("a");
      setMessages((prev) => [
        ...prev,
        { id: uid("u"), role: "user", text: question },
        { id: pendingId, role: "assistant", text: "", pending: true },
      ]);

      try {
        await streamChat(
          { question, doc_id: docId },
          {
            onTrace: (event: TraceEvent) => {
              setStages((prev) => ({
                ...prev,
                [event.stage]: { ...event, status: event.status === "running" ? "running" : "done" },
              }));
            },
            // Tokens arrive only after both gates have passed, so they are safe to show.
            onToken: (text) =>
              setMessages((prev) =>
                prev.map((m) => (m.id === pendingId ? { ...m, text: m.text + text } : m)),
              ),
            onFinal: (response) =>
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === pendingId
                    ? {
                        ...m,
                        text: response.answer,
                        verdict: response.verdict,
                        citations: response.citations,
                        chunks: response.chunks,
                        trace: response.trace,
                        requestId: response.request_id,
                        pending: false,
                      }
                    : m,
                ),
              ),
            onError: (error) =>
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === pendingId
                    ? { ...m, text: error.message, verdict: "error", pending: false, requestId: error.requestId }
                    : m,
                ),
              ),
          },
          controller.signal,
        );
      } catch (error) {
        if ((error as Error)?.name === "AbortError") {
          setMessages((prev) => prev.filter((m) => m.id !== pendingId));
        } else {
          const apiError = error as ApiRequestError;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === pendingId
                ? {
                    ...m,
                    text:
                      apiError?.message ??
                      "The server could not be reached. It may be waking up — try again in a moment.",
                    verdict: "error",
                    pending: false,
                    requestId: apiError?.requestId,
                  }
                : m,
            ),
          );
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, docId],
  );

  const activeDocument = documents.find((d) => d.doc_id === docId);

  return {
    documents, docId, activeDocument, messages, busy, stages, waking, loadingDocs,
    send, stop, clear, switchDocument,
  };
}
