"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useState } from "react";

export function Accordion({ items }: { items: { q: string; a: string }[] }) {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="divide-y divide-[color:var(--border-hairline)] overflow-hidden rounded-2xl border border-hairline bg-surface">
      {items.map((item, index) => {
        const expanded = open === index;
        return (
          <div key={item.q}>
            <h3>
              <button
                onClick={() => setOpen(expanded ? null : index)}
                aria-expanded={expanded}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-subtle/60 sm:px-6"
              >
                <span className="text-[0.95rem] font-medium">{item.q}</span>
                <ChevronDown
                  aria-hidden
                  className={`h-4 w-4 shrink-0 text-muted transition-transform duration-200 ${
                    expanded ? "rotate-180" : ""
                  }`}
                />
              </button>
            </h3>
            <AnimatePresence initial={false}>
              {expanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.22, ease: "easeOut" }}
                  className="overflow-hidden"
                >
                  <p className="px-5 pb-5 text-sm leading-relaxed text-secondary sm:px-6">
                    {item.a}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
