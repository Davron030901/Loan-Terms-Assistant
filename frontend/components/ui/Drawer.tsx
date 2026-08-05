"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useRef } from "react";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
}

/**
 * Right-side sheet on desktop, bottom sheet on mobile. Focus is trapped while open and
 * returned to whatever opened it on close.
 */
export function Drawer({ open, onClose, title, description, children }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    window.setTimeout(() => panelRef.current?.focus(), 20);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      restoreRef.current?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={title}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="absolute inset-0 bg-slate-950/45 backdrop-blur-[2px]"
          />
          <motion.div
            ref={panelRef}
            tabIndex={-1}
            initial={{ x: "100%", y: 0, opacity: 0.6 }}
            animate={{ x: 0, y: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0.4 }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-hairline bg-surface shadow-2xl max-sm:inset-x-0 max-sm:top-auto max-sm:h-[82dvh] max-sm:max-w-none max-sm:rounded-t-3xl max-sm:border-l-0 max-sm:border-t"
          >
            <header className="flex items-start justify-between gap-4 border-b border-hairline px-5 py-4">
              <div className="min-w-0">
                <h2 className="text-base font-semibold">{title}</h2>
                {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="-mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted transition hover:bg-subtle hover:text-primary"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </header>
            <div className="flex-1 overflow-y-auto overscroll-contain px-5 py-4">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
