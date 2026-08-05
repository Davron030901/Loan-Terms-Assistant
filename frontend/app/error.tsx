"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="flex min-h-[70dvh] items-center justify-center px-5">
      <div className="card w-full max-w-md p-8 text-center">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-blocked-500/12">
          <TriangleAlert className="h-6 w-6 text-blocked-500" aria-hidden />
        </div>
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="mt-2 text-sm text-secondary">
          The page failed to load. This is usually temporary.
        </p>
        <button
          onClick={reset}
          className="gradient-brand mt-6 inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
        >
          <RotateCcw className="h-4 w-4" aria-hidden />
          Try again
        </button>
      </div>
    </main>
  );
}
