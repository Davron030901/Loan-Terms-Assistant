"use client";

import { ArrowRight, Menu, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#gates", label: "Security" },
  { href: "#documents", label: "Documents" },
  { href: "#faq", label: "FAQ" },
];

export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 transition-all duration-200",
        scrolled ? "glass border-b border-hairline" : "border-b border-transparent",
      )}
    >
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span className="gradient-brand flex h-8 w-8 items-center justify-center rounded-xl shadow-[var(--shadow-glow)]">
            <ShieldCheck className="h-4 w-4 text-white" aria-hidden />
          </span>
          <span className="text-[0.95rem]">Loan Terms Assistant</span>
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2 text-sm text-secondary transition hover:bg-subtle hover:text-primary"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden sm:block">
            <ThemeToggle />
          </div>
          <Link
            href="/chat"
            className="gradient-brand hidden items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 sm:inline-flex"
          >
            Open assistant
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-hairline md:hidden"
          >
            {open ? <X className="h-4 w-4" aria-hidden /> : <Menu className="h-4 w-4" aria-hidden />}
          </button>
        </div>
      </nav>

      {open && (
        <div className="glass border-t border-hairline px-5 py-4 md:hidden">
          <div className="flex flex-col gap-1">
            {LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm text-secondary transition hover:bg-subtle"
              >
                {link.label}
              </a>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <ThemeToggle />
            <Link
              href="/chat"
              className="gradient-brand inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-medium text-white"
            >
              Open assistant
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
