"use client";

import { motion } from "framer-motion";
import {
  ArrowRight,
  BookOpenCheck,
  FileText,
  Github,
  PenLine,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { Accordion } from "@/components/ui/Accordion";
import { FAQ } from "@/lib/constants";
import type { DocumentInfo } from "@/lib/types";

const rise = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.4 },
};

function SectionHeading({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <motion.div {...rise} className="mx-auto max-w-2xl text-center">
      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-600 dark:text-brand-400">
        {eyebrow}
      </span>
      <h2 className="mt-3 text-[clamp(1.75rem,4vw,2.6rem)] font-bold tracking-[-0.02em]">{title}</h2>
      {sub && <p className="mt-3 text-pretty leading-relaxed text-secondary">{sub}</p>}
    </motion.div>
  );
}

/* ── Trust strip ─────────────────────────────────────────────────────────── */
const STATS = [
  { value: "5", label: "real bank documents" },
  { value: "2", label: "security gates" },
  { value: "100%", label: "cited answers" },
  { value: "0", label: "invented figures" },
];

export function TrustStrip() {
  return (
    <section className="border-y border-hairline bg-surface/40">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px px-5 py-2 sm:grid-cols-4">
        {STATS.map((stat, i) => (
          <motion.div
            key={stat.label}
            {...rise}
            transition={{ duration: 0.4, delay: i * 0.06 }}
            className="px-3 py-6 text-center"
          >
            <div className="gradient-text text-3xl font-bold tracking-tight">{stat.value}</div>
            <div className="mt-1 text-xs text-muted">{stat.label}</div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

/* ── How it works ────────────────────────────────────────────────────────── */
const STEPS = [
  {
    icon: ShieldAlert,
    title: "Scope guard",
    body: "Is this even my job? Off-topic questions, advice and prompt injections are refused before anything is searched.",
    gate: true,
  },
  {
    icon: Search,
    title: "Retrieve",
    body: "The question is matched against clauses from one document only. Nothing relevant enough? Nothing is answered.",
    gate: false,
  },
  {
    icon: PenLine,
    title: "Answer",
    body: "The model writes using the retrieved clauses and nothing else, quoting figures exactly and ending with (p. N).",
    gate: false,
  },
  {
    icon: ShieldCheck,
    title: "Grounding guard",
    body: "Can I prove this? Every figure is matched against the evidence, then an independent check reads the draft.",
    gate: true,
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20 sm:py-24">
      <SectionHeading
        eyebrow="The pipeline"
        title="Four steps. Two of them are locks."
        sub="A question only becomes an answer if it passes both gates. Everything else stops."
      />
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step, i) => {
          const Icon = step.icon;
          return (
            <motion.div
              key={step.title}
              {...rise}
              transition={{ duration: 0.4, delay: i * 0.07 }}
              className={`card relative p-5 ${
                step.gate ? "border-refused-500/35 bg-refused-500/[0.035]" : ""
              }`}
            >
              <span className="absolute right-4 top-4 font-mono text-xs text-muted">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                  step.gate ? "bg-refused-500/12 text-refused-500" : "bg-brand-500/12 text-brand-500"
                }`}
              >
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <h3 className="mt-4 font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary">{step.body}</p>
              {step.gate && (
                <span className="mt-3 inline-block rounded-full bg-refused-500/12 px-2 py-0.5 text-[0.68rem] font-medium uppercase tracking-wide text-refused-600 dark:text-refused-400">
                  Security gate
                </span>
              )}
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

/* ── Security gates ──────────────────────────────────────────────────────── */
export function SecurityGates() {
  return (
    <section id="gates" className="scroll-mt-20 border-y border-hairline bg-surface/40 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeading
          eyebrow="Why this is safe"
          title="Two questions the agent asks itself"
          sub="For a money document, refusing well matters more than answering often."
        />
        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          <motion.div {...rise} className="card p-6 sm:p-7">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-refused-500/12 text-refused-500">
              <ShieldAlert className="h-5 w-5" aria-hidden />
            </span>
            <h3 className="mt-4 text-lg font-semibold">Scope guard — the front door</h3>
            <p className="mt-1 text-sm italic text-muted">&ldquo;Is this even my job?&rdquo;</p>
            <p className="mt-3 text-sm leading-relaxed text-secondary">
              Deterministic patterns catch advice and injection attempts at zero cost, then a
              classifier judges the rest. Anything that isn&apos;t a clean allow is a refusal.
            </p>
            <ul className="mt-5 space-y-2">
              {[
                "Should I take this loan?",
                "Ignore all previous instructions…",
                "Who won the World Cup?",
              ].map((example) => (
                <li
                  key={example}
                  className="flex items-center gap-2.5 rounded-lg bg-refused-500/[0.07] px-3 py-2 text-sm"
                >
                  <span className="font-mono text-xs font-semibold text-refused-600 dark:text-refused-400">
                    REFUSE
                  </span>
                  <span className="truncate text-secondary">{example}</span>
                </li>
              ))}
            </ul>
          </motion.div>

          <motion.div {...rise} transition={{ duration: 0.4, delay: 0.1 }} className="card p-6 sm:p-7">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-grounded-500/12 text-grounded-500">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </span>
            <h3 className="mt-4 text-lg font-semibold">Grounding guard — the back door</h3>
            <p className="mt-1 text-sm italic text-muted">
              &ldquo;Can I prove this from the document?&rdquo;
            </p>
            <p className="mt-3 text-sm leading-relaxed text-secondary">
              Every figure in a draft answer must appear in the retrieved clauses. One that
              doesn&apos;t blocks the answer outright — before you ever see it.
            </p>
            <div className="mt-5 space-y-2">
              <div className="rounded-lg bg-blocked-500/[0.07] px-3 py-2.5">
                <div className="font-mono text-[0.7rem] uppercase tracking-wide text-blocked-600 dark:text-blocked-400">
                  Draft — blocked
                </div>
                <p className="mt-1 text-sm text-secondary">
                  &ldquo;A late fee of <span className="font-semibold text-blocked-500">$50</span>{" "}
                  applies (p. 3).&rdquo;
                </p>
              </div>
              <div className="rounded-lg bg-grounded-500/[0.07] px-3 py-2.5">
                <div className="font-mono text-[0.7rem] uppercase tracking-wide text-grounded-600 dark:text-grounded-400">
                  Document says
                </div>
                <p className="mt-1 text-sm text-secondary">
                  &ldquo;…a fee of <span className="font-semibold text-grounded-500">$25</span>…&rdquo;
                </p>
              </div>
              <p className="pt-1 text-xs text-muted">
                Caught by the numeric audit — no model call needed.
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

/* ── Documents ───────────────────────────────────────────────────────────── */
export function DocumentGrid({ documents }: { documents: DocumentInfo[] }) {
  return (
    <section id="documents" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20 sm:py-24">
      <SectionHeading
        eyebrow="The corpus"
        title="Five real, public bank contracts"
        sub="One document is active per conversation — that is what keeps the scope provable."
      />
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {documents.map((doc, i) => (
          <motion.div
            key={doc.doc_id}
            {...rise}
            transition={{ duration: 0.4, delay: i * 0.06 }}
            className="card group flex flex-col p-5 transition hover:border-brand-500/40 hover:shadow-[var(--shadow-glow)]"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/12 text-brand-500">
                <FileText className="h-5 w-5" aria-hidden />
              </span>
              <div className="flex flex-wrap justify-end gap-1.5">
                {doc.is_default && (
                  <span className="rounded-full bg-brand-500/12 px-2 py-0.5 text-[0.68rem] font-medium text-brand-600 dark:text-brand-300">
                    Default
                  </span>
                )}
                <span className="rounded-full bg-subtle px-2 py-0.5 font-mono text-[0.68rem] uppercase text-muted">
                  {doc.language}
                </span>
              </div>
            </div>
            <h3 className="mt-4 font-semibold">{doc.bank}</h3>
            <p className="mt-1 line-clamp-2 text-sm text-secondary">{doc.title}</p>
            <p className="mt-3 font-mono text-[0.72rem] text-muted">
              {doc.jurisdiction} · {doc.pages} pages
              {doc.chunks > 0 && ` · ${doc.chunks} clauses`}
            </p>
            <Link
              href={`/chat?doc=${doc.doc_id}`}
              className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-600 transition group-hover:gap-2.5 dark:text-brand-400"
            >
              Ask about this
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

/* ── FAQ + footer ────────────────────────────────────────────────────────── */
export function FaqSection() {
  return (
    <section id="faq" className="scroll-mt-20 border-t border-hairline bg-surface/40 py-20 sm:py-24">
      <div className="mx-auto max-w-3xl px-5">
        <SectionHeading eyebrow="Questions" title="What people ask first" />
        <motion.div {...rise} className="mt-10">
          <Accordion items={FAQ} />
        </motion.div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-hairline">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-10 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-md">
          <div className="flex items-center gap-2 font-semibold">
            <BookOpenCheck className="h-4 w-4 text-brand-500" aria-hidden />
            Loan Terms Assistant
          </div>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Educational project. Not financial or legal advice. Always read the original contract —
            this tool quotes it, it does not replace it.
          </p>
        </div>
        <div className="flex flex-col gap-2 text-xs text-muted sm:items-end">
          <span>FastAPI · Gemini · Qdrant Cloud · Next.js</span>
          <a
            href="https://github.com"
            className="inline-flex items-center gap-1.5 transition hover:text-primary"
          >
            <Github className="h-3.5 w-3.5" aria-hidden />
            Source
          </a>
        </div>
      </div>
    </footer>
  );
}
