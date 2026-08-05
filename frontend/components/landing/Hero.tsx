"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, FileQuestion, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

/** A looping, self-contained demo. No API calls — this is the pitch, not the product. */
const REEL = [
  {
    question: "What happens if I miss a payment?",
    answer:
      "Accepting a late or partial payment does not reduce the Bank's rights under the Agreement (p. 5).",
    badge: "Grounded · verified",
    icon: ShieldCheck,
    accent: "text-grounded-500",
    tint: "bg-grounded-500/10 ring-grounded-500/25",
    cite: "p. 5",
  },
  {
    question: "Write me a poem about the moon.",
    answer: "I can only answer questions about this loan product's terms and conditions.",
    badge: "Out of scope · refused",
    icon: ShieldAlert,
    accent: "text-refused-500",
    tint: "bg-refused-500/10 ring-refused-500/30",
    cite: null,
  },
  {
    question: "What is the mortgage rate for a beach house?",
    answer: "Not stated in the terms.",
    badge: "Not in document",
    icon: FileQuestion,
    accent: "text-notstated-500",
    tint: "bg-notstated-500/10 ring-notstated-500/25",
    cite: null,
  },
];

function DemoCard() {
  const [index, setIndex] = useState(0);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % REEL.length), 3800);
    return () => clearInterval(timer);
  }, [reduced]);

  const item = REEL[index];
  const Icon = item.icon;

  return (
    <div className="card w-full overflow-hidden p-1.5 shadow-[var(--shadow-glow)]">
      <div className="flex items-center gap-1.5 px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-blocked-400/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-refused-400/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-grounded-400/70" />
        <span className="ml-2 font-mono text-[0.7rem] text-muted">cibc_personal_loan.pdf</span>
      </div>

      <div className="min-h-[15rem] rounded-xl bg-subtle/60 p-4 sm:min-h-[14rem]">
        <AnimatePresence mode="wait">
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35 }}
            className="flex flex-col gap-3"
          >
            <div className="self-end rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2 text-sm text-white shadow-sm">
              {item.question}
            </div>

            <div className="flex flex-col gap-2 rounded-2xl rounded-bl-md border border-hairline bg-surface px-3.5 py-3">
              <span
                className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.7rem] font-medium ring-1 ${item.tint} ${item.accent}`}
              >
                <Icon className="h-3 w-3" aria-hidden />
                {item.badge}
              </span>
              <p className="text-sm leading-relaxed text-secondary">
                {item.answer}
                {item.cite && (
                  <span className="ml-1.5 inline-flex items-center rounded-md bg-brand-500/12 px-1.5 py-0.5 font-mono text-[0.7rem] text-brand-700 dark:text-brand-300">
                    {item.cite}
                  </span>
                )}
              </p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="flex justify-center gap-1.5 py-3">
        {REEL.map((_, i) => (
          <span
            key={i}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              i === index ? "w-5 bg-brand-500" : "w-1.5 bg-brand-500/25"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

export function Hero() {
  return (
    <section className="relative mx-auto max-w-6xl px-5 pb-16 pt-14 sm:pt-20 lg:pb-24 lg:pt-24">
      <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <span className="inline-flex items-center gap-2 rounded-full border border-hairline bg-surface/70 px-3 py-1.5 text-xs font-medium text-secondary">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-brand-500" />
            Scoped · Grounded · Cited
          </span>

          <h1 className="mt-5 text-balance text-[clamp(2.4rem,6vw,4.2rem)] font-bold leading-[1.05] tracking-[-0.03em]">
            Answers straight from the <span className="gradient-text">loan contract</span>.
          </h1>

          <p className="mt-5 max-w-xl text-pretty text-[1.05rem] leading-relaxed text-secondary">
            An AI assistant with exactly one job: read the bank&apos;s Terms &amp; Conditions and
            quote them — with a page number. It refuses everything else, and it blocks its own
            answer if it can&apos;t prove it.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/chat"
              className="gradient-brand inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold text-white shadow-[var(--shadow-glow)] transition hover:opacity-90"
            >
              Ask about a loan document
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            <a
              href="#how"
              className="inline-flex items-center gap-2 rounded-xl border border-hairline px-5 py-3 text-sm font-medium text-secondary transition hover:bg-subtle hover:text-primary"
            >
              <Sparkles className="h-4 w-4" aria-hidden />
              See how it works
            </a>
          </div>

          <p className="mt-5 text-xs text-muted">
            Five real, public bank contracts · no sign-up · nothing stored
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.12 }}
        >
          <DemoCard />
        </motion.div>
      </div>
    </section>
  );
}
