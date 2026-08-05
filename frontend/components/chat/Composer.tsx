"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const MAX = 600;

export function Composer({
  onSend,
  onStop,
  busy,
  disabled,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  busy: boolean;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`; // ~6 rows, then scroll
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy || disabled) return;
    onSend(text);
    setValue("");
  };

  const nearLimit = value.length > 400;

  return (
    <div
      className="sticky bottom-0 z-20 border-t border-hairline bg-canvas/85 backdrop-blur"
      style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
    >
      <div className="mx-auto max-w-3xl px-4 pt-3">
        <div className="card flex items-end gap-2 p-2 focus-within:border-brand-500/50 focus-within:shadow-[var(--shadow-glow)]">
          <label htmlFor="composer" className="sr-only">
            Ask about this loan document
          </label>
          <textarea
            id="composer"
            ref={ref}
            rows={1}
            value={value}
            maxLength={MAX}
            disabled={disabled}
            placeholder={disabled ? "Loading the document…" : "Ask about interest, fees, penalties, repayment…"}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            className="max-h-[168px] flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] leading-relaxed outline-none placeholder:text-muted disabled:opacity-60"
          />

          {busy ? (
            <button
              onClick={onStop}
              aria-label="Stop generating"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-hairline text-secondary transition hover:bg-subtle"
            >
              <Square className="h-3.5 w-3.5 fill-current" aria-hidden />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!value.trim() || disabled}
              aria-label="Send question"
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white transition",
                value.trim() && !disabled
                  ? "gradient-brand hover:opacity-90"
                  : "cursor-not-allowed bg-subtle text-muted",
              )}
            >
              <ArrowUp className="h-4 w-4" aria-hidden />
            </button>
          )}
        </div>

        <div className="flex items-center justify-between px-1 pb-1 pt-1.5">
          <p className="text-[0.68rem] text-muted">
            Enter to send · Shift + Enter for a new line
          </p>
          {nearLimit && (
            <span
              className={cn(
                "font-mono text-[0.68rem]",
                value.length >= MAX ? "text-blocked-500" : "text-muted",
              )}
            >
              {value.length}/{MAX}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
